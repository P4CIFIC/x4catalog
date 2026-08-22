from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .catalog import export_images, rebuild_views
from .config import BIND_HOST, CatalogPaths
from .db import connect, event, transaction
from .labeling import LABEL_MODEL_REVISIONS


class ReviewUpdate(BaseModel):
    decision: Literal["unreviewed", "keep", "reject", "favorite"] = "unreviewed"
    rating: int | None = Field(default=None, ge=0, le=5)
    x4_suitability: Literal["excellent", "good", "acceptable", "too-dark", "too-busy", "too-fine", "small-text", "needs-dithering", "review"] | None = None
    note: str = Field(default="", max_length=4000)


class TagUpdate(BaseModel):
    tags: list[str] = Field(min_length=1, max_length=30)
    confirmed: bool = True


class ExportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    image_ids: list[int] = Field(min_length=1, max_length=5000)


class CrossPointAction(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1, max_length=1024)
    name: str | None = Field(default=None, max_length=255)
    dest: str | None = Field(default=None, max_length=1024)


def _rows(conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _search_pattern(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    return "%" + "%".join(tokens or [value.casefold().strip()]) + "%"


def _tag_names(tag: str | None, tags: str | None) -> list[str]:
    names: list[str] = []
    if tag and tag.strip():
        names.append(tag.strip())
    if tags:
        names.extend(part.strip() for part in tags.split(",") if part.strip())
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def _image_filter_parts(
    *,
    q: str | None = None,
    tag: str | None = None,
    tags: str | None = None,
    decision: str | None = None,
    cluster_id: int | None = None,
) -> tuple[list[str], list[object], list[str]]:
    clauses = ["1=1"]
    params: list[object] = []
    joins = ["LEFT JOIN reviews r ON r.image_id=i.id"]
    if q:
        joins.append("LEFT JOIN ocr_results oq ON oq.image_id=i.id")
        pattern = _search_pattern(q)
        clauses.append("""(
            lower(i.filename) LIKE ? OR lower(COALESCE(oq.text, '')) LIKE ?
            OR EXISTS (
                SELECT 1 FROM image_tags sit JOIN tags st ON st.id=sit.tag_id
                WHERE sit.image_id=i.id AND lower(st.name) LIKE ?
            )
            OR EXISTS (
                SELECT 1 FROM label_predictions sp
                WHERE sp.image_id=i.id AND sp.published=1 AND lower(sp.raw_label) LIKE ?
            )
        )""")
        params.extend([pattern] * 4)
    for name in _tag_names(tag, tags):
        clauses.append("""EXISTS (
            SELECT 1 FROM image_tags it JOIN tags t ON t.id=it.tag_id
            WHERE it.image_id=i.id AND t.name = ?
        )""")
        params.append(name)
    if decision:
        clauses.append("COALESCE(r.decision, 'unreviewed') = ?")
        params.append(decision)
    if cluster_id is not None:
        joins.append("JOIN cluster_members cm ON cm.image_id=i.id")
        clauses.append("cm.cluster_id = ?")
        params.append(cluster_id)
    return clauses, params, joins


def _crosspoint_url(host: str, path: str) -> str:
    value = host.strip()
    if value.startswith(("http://", "https://")):
        parsed = urlsplit(value)
        if parsed.path or parsed.query or parsed.fragment:
            raise HTTPException(400, "CrossPoint host must be an IP address or hostname.")
        value = parsed.netloc
    value = value.strip().strip("/")
    value = re.sub(r":0$", "", value)
    parsed = urlsplit(f"//{value}")
    try:
        parsed.port
    except ValueError as error:
        raise HTTPException(400, "CrossPoint host must be an IP address or hostname.") from error
    if not value or parsed.hostname is None or parsed.username or parsed.password or any(char in value for char in "/\\?#") or any(char.isspace() for char in value):
        raise HTTPException(400, "CrossPoint host must be an IP address or hostname.")
    return f"http://{value}{path}"


def _crosspoint_request(host: str, path: str, *, method: str = "GET", form: dict[str, str] | None = None) -> tuple[bytes, str]:
    data = None if form is None else urlencode(form).encode("utf-8")
    headers = {"Accept": "application/json, text/plain, image/*"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(_crosspoint_url(host, path), data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=12) as response:
            return response.read(), response.headers.get_content_type()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise HTTPException(error.code, detail or "CrossPoint rejected the request.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise HTTPException(502, f"Could not reach CrossPoint at {host}.") from error


def _crosspoint_json(host: str, path: str) -> object:
    body, content_type = _crosspoint_request(host, path)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(502, f"CrossPoint returned an invalid response ({content_type}).") from error


def _crosspoint_path(value: str, *, allow_sleep: bool = True) -> str:
    raw = str(value or "").strip()
    if not raw or "\x00" in raw or "\\" in raw:
        raise HTTPException(400, "CrossPoint paths must be absolute POSIX paths.")
    normalized = "/" + "/".join(part for part in raw.split("/") if part)
    segments = normalized.split("/")[1:]
    navigation = any(segment in {".", ".."} for segment in segments)
    hidden = [segment for segment in segments if segment.startswith(".")]
    sleep_path = normalized == "/.sleep" or normalized.startswith("/.sleep/")
    if navigation or (hidden and not (allow_sleep and sleep_path and hidden == [".sleep"])):
        raise HTTPException(400, "Hidden CrossPoint paths are not available through this app.")
    return normalized if normalized != "" else "/"


def _crosspoint_filename(value: str) -> str:
    name = str(value or "").strip()
    if not name or name in {".", ".."} or name.startswith(".") or "/" in name or "\\" in name or "\x00" in name:
        raise HTTPException(400, "Use a visible filename only.")
    return name


def create_app(paths: CatalogPaths) -> FastAPI:
    paths.ensure()
    app = FastAPI(title="X4 Catalog", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=paths.static), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(paths.static / "index.html")

    @app.get("/browse", include_in_schema=False)
    @app.get("/docs", include_in_schema=False)
    @app.get("/device", include_in_schema=False)
    def spa_page() -> FileResponse:
        return FileResponse(paths.static / "index.html")

    @app.get("/api/crosspoint/status")
    def crosspoint_status(host: str = Query(min_length=1, max_length=255)) -> object:
        return _crosspoint_json(host, "/api/status")

    @app.get("/api/crosspoint/files")
    def crosspoint_files(host: str = Query(min_length=1, max_length=255), path: str = Query(min_length=1, max_length=1024)) -> object:
        safe_path = _crosspoint_path(path)
        return _crosspoint_json(host, f"/api/files?{urlencode({'path': safe_path})}")

    @app.get("/api/crosspoint/download")
    def crosspoint_download(host: str = Query(min_length=1, max_length=255), path: str = Query(min_length=1, max_length=1024)) -> Response:
        safe_path = _crosspoint_path(path)
        body, content_type = _crosspoint_request(host, f"/download?{urlencode({'path': safe_path})}")
        return Response(content=body, media_type=content_type or "application/octet-stream")

    @app.post("/api/crosspoint/rename")
    def crosspoint_rename(action: CrossPointAction) -> dict[str, object]:
        if not action.name:
            raise HTTPException(400, "A new filename is required.")
        path = _crosspoint_path(action.path)
        name = _crosspoint_filename(action.name)
        _crosspoint_request(action.host, "/rename", method="POST", form={"path": path, "name": name})
        return {"ok": True}

    @app.post("/api/crosspoint/delete")
    def crosspoint_delete(action: CrossPointAction) -> dict[str, object]:
        _crosspoint_request(action.host, "/delete", method="POST", form={"path": _crosspoint_path(action.path)})
        return {"ok": True}

    @app.post("/api/crosspoint/mkdir")
    def crosspoint_mkdir(action: CrossPointAction) -> dict[str, object]:
        if not action.name:
            raise HTTPException(400, "A folder name is required.")
        path = _crosspoint_path(action.path, allow_sleep=False)
        name = _crosspoint_filename(action.name)
        _crosspoint_request(action.host, "/mkdir", method="POST", form={"path": path, "name": name})
        return {"ok": True}

    @app.post("/api/crosspoint/move")
    def crosspoint_move(action: CrossPointAction) -> dict[str, object]:
        if not action.dest:
            raise HTTPException(400, "A destination folder is required.")
        path = _crosspoint_path(action.path, allow_sleep=False)
        destination = _crosspoint_path(action.dest, allow_sleep=False)
        _crosspoint_request(action.host, "/move", method="POST", form={"path": path, "dest": destination})
        return {"ok": True}

    @app.get("/api/health")
    def health() -> dict[str, object]:
        with connect(paths.database) as conn:
            count = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
            reviewed = conn.execute("SELECT COUNT(*) FROM reviews WHERE decision != 'unreviewed'").fetchone()[0]
            labeled = conn.execute("SELECT COUNT(DISTINCT image_id) FROM label_predictions WHERE published=1").fetchone()[0]
            run = conn.execute(
                "SELECT id, status, processed, total, error FROM label_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return {
            "bind": BIND_HOST,
            "image_count": count,
            "reviewed_count": reviewed,
            "labeled_count": labeled,
            "free_gib": round(paths.available_bytes() / 1024**3, 2),
            "last_label_run": None if run is None else dict(run),
        }

    @app.get("/api/images")
    def images(
        q: str | None = None,
        tag: str | None = None,
        tags: str | None = None,
        decision: str | None = None,
        cluster_id: int | None = None,
        limit: int = Query(default=80, ge=1, le=240),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        clauses, params, joins = _image_filter_parts(q=q, tag=tag, tags=tags, decision=decision, cluster_id=cluster_id)
        where = " AND ".join(clauses)
        query = f"""
            SELECT DISTINCT i.id, i.filename, i.mean_luma, i.contrast, i.edge_density,
                COALESCE(r.decision, 'unreviewed') AS decision, r.rating, r.x4_suitability,
                ps.score AS preference_score
            FROM images i {' '.join(joins)}
            LEFT JOIN preference_scores ps ON ps.image_id=i.id
            WHERE {where}
            ORDER BY CASE COALESCE(r.decision, 'unreviewed') WHEN 'unreviewed' THEN 0 ELSE 1 END,
                ps.score DESC, i.id
            LIMIT ? OFFSET ?
        """
        count_query = f"SELECT COUNT(DISTINCT i.id) AS total FROM images i {' '.join(joins)} WHERE {where}"
        query_params = [*params, limit, offset]
        with connect(paths.database) as conn:
            total = int(conn.execute(count_query, tuple(params)).fetchone()["total"])
            results = _rows(conn, query, tuple(query_params))
        return {"items": results, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/images/ids")
    def image_ids(
        q: str | None = None,
        tag: str | None = None,
        tags: str | None = None,
        decision: str | None = None,
        cluster_id: int | None = None,
    ) -> dict[str, object]:
        """Return concrete IDs for a current result set without loading thumbnails."""
        clauses, params, joins = _image_filter_parts(q=q, tag=tag, tags=tags, decision=decision, cluster_id=cluster_id)
        where = " AND ".join(clauses)
        count_query = f"SELECT COUNT(DISTINCT i.id) AS total FROM images i {' '.join(joins)} WHERE {where}"
        query = f"""
            SELECT DISTINCT i.id
            FROM images i {' '.join(joins)}
            LEFT JOIN preference_scores ps ON ps.image_id=i.id
            WHERE {where}
            ORDER BY CASE COALESCE(r.decision, 'unreviewed') WHEN 'unreviewed' THEN 0 ELSE 1 END,
                ps.score DESC, i.id
        """
        with connect(paths.database) as conn:
            total = int(conn.execute(count_query, tuple(params)).fetchone()["total"])
            ids = [int(row["id"]) for row in conn.execute(query, tuple(params)).fetchall()]
        return {"ids": ids, "total": total}

    @app.get("/api/tags")
    def tags(
        limit: int = Query(default=120, ge=1, le=500),
        q: str | None = None,
        category: str | None = None,
    ) -> dict[str, object]:
        clauses = ["1=1"]
        params: list[object] = []
        if q:
            clauses.append("lower(t.name) LIKE ?")
            params.append(_search_pattern(q))
        if category:
            clauses.append("t.category = ?")
            params.append(category)
        with connect(paths.database) as conn:
            rows = _rows(conn, """SELECT t.name, t.category,
                    COUNT(DISTINCT CASE WHEN it.source='machine' THEN it.image_id END) AS automatic_count,
                    COUNT(DISTINCT CASE WHEN it.source='human' AND it.confirmed=1 THEN it.image_id END) AS human_count
                FROM tags t LEFT JOIN image_tags it ON it.tag_id=t.id
                WHERE """ + " AND ".join(clauses) + """
                GROUP BY t.id ORDER BY automatic_count DESC, t.category, t.name LIMIT ?""", (*params, limit))
        return {"items": rows}

    @app.get("/api/labeling")
    def labeling() -> dict[str, object]:
        with connect(paths.database) as conn:
            rows = _rows(conn, "SELECT * FROM label_runs ORDER BY id DESC LIMIT 10")
            counts = _rows(conn, """SELECT model, confidence_band, COUNT(*) AS count
                FROM label_predictions WHERE published=1 GROUP BY model, confidence_band
                ORDER BY model, confidence_band""")
        return {"runs": rows, "counts": counts}

    @app.get("/api/images/{image_id}")
    def image_detail(image_id: int) -> dict[str, object]:
        with connect(paths.database) as conn:
            row = conn.execute(
                """SELECT i.*, COALESCE(r.decision,'unreviewed') decision, r.rating, r.x4_suitability, r.note,
                   o.text AS ocr_text, o.text_density, o.has_small_text, o.engine AS ocr_engine, ps.score AS preference_score
                   FROM images i LEFT JOIN reviews r ON r.image_id=i.id
                   LEFT JOIN ocr_results o ON o.image_id=i.id
                   LEFT JOIN preference_scores ps ON ps.image_id=i.id WHERE i.id=?""",
                (image_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Unknown image")
            tags = _rows(conn, """SELECT t.name, t.category, it.source, it.confidence, it.confirmed,
                                         NULL AS model, NULL AS confidence_band
                                  FROM image_tags it JOIN tags t ON t.id=it.tag_id WHERE it.image_id=?
                                  ORDER BY it.confirmed DESC, it.confidence DESC""", (image_id,))
            evidence_clauses = " OR ".join(
                "(p.model=? AND p.model_revision=?)" for _ in LABEL_MODEL_REVISIONS
            )
            evidence_params: list[object] = [image_id]
            evidence_params.extend(value for pair in LABEL_MODEL_REVISIONS.items() for value in pair)
            evidence_query = (
                """SELECT p.model, p.model_revision, p.raw_label, p.score,
                          p.confidence_band, p.published AS accepted, t.name AS normalized_tag
                   FROM label_predictions p LEFT JOIN tags t ON t.id=p.tag_id
                   WHERE p.image_id=? AND ("""
                + evidence_clauses
                + ") ORDER BY p.published DESC, p.score DESC, p.model, p.raw_label"
            )
            evidence = _rows(conn, evidence_query, tuple(evidence_params))
            groups = _rows(conn, """SELECT g.id, g.kind, g.confidence FROM duplicate_members dm
                                    JOIN duplicate_groups g ON g.id=dm.group_id WHERE dm.image_id=?""", (image_id,))
        payload = dict(row)
        payload["ocr_processed"] = payload["ocr_engine"] is not None
        payload["tags"] = tags
        payload["label_evidence"] = evidence
        payload["duplicate_groups"] = groups
        return payload

    @app.get("/api/images/{image_id}/thumbnail", include_in_schema=False)
    def image_thumbnail(image_id: int) -> FileResponse:
        with connect(paths.database) as conn:
            row = conn.execute("SELECT thumb_path FROM images WHERE id=?", (image_id,)).fetchone()
        if row is None or not Path(row["thumb_path"]).is_file():
            raise HTTPException(404, "Thumbnail unavailable")
        return FileResponse(row["thumb_path"], media_type="image/webp")

    @app.get("/api/images/{image_id}/source", include_in_schema=False)
    def image_source(image_id: int) -> FileResponse:
        with connect(paths.database) as conn:
            row = conn.execute("SELECT source_path, filename FROM images WHERE id=?", (image_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Unknown image")
        source_root = paths.source.resolve()
        source_path = Path(row["source_path"]).resolve()
        if source_path != source_root and source_root not in source_path.parents:
            raise HTTPException(403, "Source path is outside the configured image library")
        if not source_path.is_file():
            raise HTTPException(404, "Source image unavailable")
        return FileResponse(source_path, media_type="image/bmp", filename=row["filename"])

    @app.get("/api/clusters")
    def clusters(limit: int = Query(default=80, ge=1, le=240)) -> dict[str, object]:
        with connect(paths.database) as conn:
            rows = _rows(conn, """SELECT c.id, c.algorithm, c.label, COUNT(cm.image_id) AS image_count,
                SUM(cm.outlier) AS outlier_count FROM clusters c JOIN cluster_members cm ON cm.cluster_id=c.id
                GROUP BY c.id ORDER BY image_count DESC LIMIT ?""", (limit,))
        return {"items": rows}

    @app.post("/api/images/{image_id}/review")
    def set_review(image_id: int, update: ReviewUpdate) -> dict[str, object]:
        with transaction(paths.database) as conn:
            if conn.execute("SELECT 1 FROM images WHERE id=?", (image_id,)).fetchone() is None:
                raise HTTPException(404, "Unknown image")
            conn.execute(
                """INSERT INTO reviews(image_id, decision, rating, x4_suitability, note)
                   VALUES (?, ?, ?, ?, ?) ON CONFLICT(image_id) DO UPDATE SET decision=excluded.decision,
                   rating=excluded.rating, x4_suitability=excluded.x4_suitability, note=excluded.note,
                   updated_at=CURRENT_TIMESTAMP""",
                (image_id, update.decision, update.rating, update.x4_suitability, update.note),
            )
            event(conn, "review_updated", "image", image_id, update.model_dump())
        return {"ok": True}

    @app.post("/api/images/{image_id}/tags")
    def set_tags(image_id: int, update: TagUpdate) -> dict[str, object]:
        with transaction(paths.database) as conn:
            if conn.execute("SELECT 1 FROM images WHERE id=?", (image_id,)).fetchone() is None:
                raise HTTPException(404, "Unknown image")
            for name in update.tags:
                tag = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
                if tag is None:
                    raise HTTPException(422, f"Unknown controlled-vocabulary tag: {name}")
                conn.execute(
                    "INSERT OR REPLACE INTO image_tags(image_id, tag_id, source, confidence, confirmed) VALUES (?, ?, 'human', 1.0, ?)",
                    (image_id, tag["id"], int(update.confirmed)),
                )
            event(conn, "human_tags_updated", "image", image_id, update.model_dump())
        return {"ok": True}

    @app.post("/api/views/rebuild")
    def rebuild() -> dict[str, object]:
        return {"symlink_count": rebuild_views(paths)}

    @app.post("/api/exports")
    def export(request: ExportRequest) -> dict[str, object]:
        return export_images(paths, request.name, request.image_ids)

    return app
