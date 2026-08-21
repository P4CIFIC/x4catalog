from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
import json
import shutil

from .catalog import utc_now
from .config import CatalogPaths
from .db import connect
from .taxonomy import image_is_sensitive


def _json_ready(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_snapshot(paths: CatalogPaths) -> dict[str, object]:
    with connect(paths.database) as conn:
        image_count = int(conn.execute("SELECT COUNT(*) FROM images").fetchone()[0])
        reviewed_count = int(conn.execute("SELECT COUNT(*) FROM reviews WHERE decision != 'unreviewed'").fetchone()[0])
        labeled_count = int(conn.execute("SELECT COUNT(DISTINCT image_id) FROM label_predictions WHERE published=1").fetchone()[0])
        tag_rows = conn.execute(
            """SELECT t.name, t.category,
                    COUNT(DISTINCT CASE WHEN it.source='machine' THEN it.image_id END) AS automatic_count,
                    COUNT(DISTINCT CASE WHEN it.source='human' AND it.confirmed=1 THEN it.image_id END) AS human_count
               FROM tags t LEFT JOIN image_tags it ON it.tag_id=t.id
               GROUP BY t.id ORDER BY automatic_count DESC, t.category, t.name"""
        ).fetchall()
        cluster_rows = conn.execute(
            """SELECT c.id, c.algorithm, c.label, COUNT(cm.image_id) AS image_count,
                      SUM(cm.outlier) AS outlier_count
               FROM clusters c JOIN cluster_members cm ON cm.cluster_id=c.id
               GROUP BY c.id ORDER BY image_count DESC"""
        ).fetchall()
        membership_rows = conn.execute("SELECT cluster_id, image_id FROM cluster_members").fetchall()
        images = conn.execute(
            """SELECT i.id, i.filename, i.sha256, i.byte_size, i.mean_luma, i.contrast, i.edge_density,
                      i.thumb_path, i.source_path, COALESCE(r.decision, 'unreviewed') AS decision, r.rating,
                      r.x4_suitability, r.note, o.text AS ocr_text, o.engine AS ocr_engine,
                      ps.score AS preference_score
               FROM images i
               LEFT JOIN reviews r ON r.image_id=i.id
               LEFT JOIN ocr_results o ON o.image_id=i.id
               LEFT JOIN preference_scores ps ON ps.image_id=i.id
               ORDER BY i.id"""
        ).fetchall()
        tag_map: dict[int, list[dict[str, object]]] = {}
        for row in conn.execute(
            """SELECT it.image_id, t.name, t.category, it.source, it.confidence, it.confirmed
               FROM image_tags it JOIN tags t ON t.id=it.tag_id
               ORDER BY it.confirmed DESC, it.confidence DESC"""
        ):
            tag_map.setdefault(int(row["image_id"]), []).append(
                {
                    "name": row["name"],
                    "category": row["category"],
                    "source": row["source"],
                    "confidence": row["confidence"],
                    "confirmed": bool(row["confirmed"]),
                }
            )
    cluster_ids: dict[int, list[int]] = {}
    for row in membership_rows:
        cluster_ids.setdefault(int(row["image_id"]), []).append(int(row["cluster_id"]))
    snapshot_images = []
    for row in images:
        image_id = int(row["id"])
        digest = str(row["sha256"])
        snapshot_images.append(
            {
                "id": image_id,
                "filename": row["filename"],
                "sha256": digest,
                "byte_size": int(row["byte_size"]),
                "mean_luma": row["mean_luma"],
                "contrast": row["contrast"],
                "edge_density": row["edge_density"],
                "decision": row["decision"],
                "rating": row["rating"],
                "x4_suitability": row["x4_suitability"],
                "note": row["note"] or "",
                "ocr_text": row["ocr_text"] or "",
                "ocr_processed": row["ocr_engine"] is not None,
                "preference_score": row["preference_score"],
                "tags": tag_map.get(image_id, []),
                "cluster_ids": cluster_ids.get(image_id, []),
                "thumbnail_path": row["thumb_path"],
                "local_source": row["source_path"],
                "thumbnail_key": f"thumbnails/{digest}.webp",
                "source_key": f"sources/{digest}.bmp",
            }
        )
    return {
        "exported_at": utc_now(),
        "mode": "hosted",
        "image_count": image_count,
        "reviewed_count": reviewed_count,
        "labeled_count": labeled_count,
        "images": snapshot_images,
        "tags": [
            {
                "name": row["name"],
                "category": row["category"],
                "automatic_count": int(row["automatic_count"] or 0),
                "human_count": int(row["human_count"] or 0),
            }
            for row in tag_rows
        ],
        "clusters": [
            {
                "id": int(row["id"]),
                "algorithm": row["algorithm"],
                "label": row["label"],
                "image_count": int(row["image_count"] or 0),
                "outlier_count": int(row["outlier_count"] or 0),
            }
            for row in cluster_rows
        ],
    }


def _join_public(base: str, path: str) -> str:
    if not base:
        return path
    return f"{base.rstrip('/')}{path if path.startswith('/') else f'/{path}'}"


def _public_image(
    item: dict[str, object],
    *,
    has_thumb: bool,
    has_source: bool,
    public_base: str = "",
) -> dict[str, object]:
    digest = str(item["sha256"])
    tags = []
    for tag in item.get("tags") or []:
        if isinstance(tag, dict) and tag.get("name"):
            tags.append({"name": tag["name"], "source": tag.get("source"), "confidence": tag.get("confidence")})
    ocr = str(item.get("ocr_text") or "")
    return {
        "id": item["id"],
        "filename": item["filename"],
        "sha256": digest,
        "byte_size": item["byte_size"],
        "mean_luma": item["mean_luma"],
        "contrast": item["contrast"],
        "edge_density": item["edge_density"],
        "decision": item["decision"],
        "rating": item["rating"],
        "x4_suitability": item["x4_suitability"],
        "ocr_text": ocr[:400],
        "ocr_processed": item["ocr_processed"],
        "tags": tags,
        "cluster_ids": item.get("cluster_ids") or [],
        "sensitive": image_is_sensitive(item.get("tags") or []),
        "thumbnail_url": _join_public(public_base, f"/thumbs/{digest}.webp") if has_thumb else None,
        "source_url": _join_public(public_base, f"/sources/{digest}.bmp") if has_source else None,
    }


def _copy_one(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size == source.stat().st_size:
        return "skipped"
    shutil.copy2(source, destination)
    return "uploaded"


def publish(
    paths: CatalogPaths,
    *,
    include_sources: bool = True,
    concurrency: int = 8,
    public_base: str = "",
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Copy derived images into static/ and write a path-free catalog.json snapshot."""
    snapshot = build_snapshot(paths)
    report = {"uploaded": 0, "skipped": 0, "failed": 0}
    thumbs_dir = paths.static / "thumbs"
    sources_dir = paths.static / "sources"
    jobs: list[tuple[Path, Path]] = []
    has_thumb: dict[int, bool] = {}
    has_source: dict[int, bool] = {}
    for item in snapshot["images"]:
        digest = str(item["sha256"])
        image_id = int(item["id"])
        thumb_candidates = [Path(str(item["thumbnail_path"])), paths.thumbnails / f"{digest}.webp"]
        thumb = next((candidate for candidate in thumb_candidates if candidate.is_file()), None)
        has_thumb[image_id] = thumb is not None
        if thumb is not None:
            jobs.append((thumb, thumbs_dir / f"{digest}.webp"))
        if include_sources:
            source_candidates = [Path(str(item["local_source"])), paths.source / str(item["filename"])]
            source = next((candidate for candidate in source_candidates if candidate.is_file()), None)
            has_source[image_id] = source is not None
            if source is not None:
                jobs.append((source, sources_dir / f"{digest}.bmp"))
        else:
            has_source[image_id] = False
    if progress:
        progress(f"Copying {len(jobs)} files into static/")
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_copy_one, source, destination) for source, destination in jobs]
        for future in as_completed(futures):
            try:
                report[future.result()] += 1
            except Exception:
                report["failed"] += 1
    catalog = {
        "exported_at": snapshot["exported_at"],
        "mode": "hosted",
        "image_count": snapshot["image_count"],
        "reviewed_count": snapshot["reviewed_count"],
        "labeled_count": snapshot["labeled_count"],
        "images": [
            _public_image(
                item,
                has_thumb=has_thumb.get(int(item["id"]), False),
                has_source=has_source.get(int(item["id"]), False),
                public_base=public_base,
            )
            for item in snapshot["images"]
        ],
        "tags": snapshot["tags"],
        "clusters": snapshot["clusters"],
    }
    destination = paths.static / "catalog.json"
    destination.write_text(json.dumps(catalog, separators=(",", ":")) + "\n")
    catalog_url = _join_public(public_base, "/catalog.json") if public_base else "/catalog.json"
    (paths.static / "catalog-url.json").write_text(json.dumps({"url": catalog_url}) + "\n")
    return {
        "catalog": str(destination),
        "catalog_url": catalog_url,
        "images": snapshot["image_count"],
        **report,
    }
