from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Iterable

import numpy as np
from PIL import Image, ImageFilter

from .config import CatalogPaths
from .db import connect, event, get_setting, initialize, set_setting, transaction
from .taxonomy import TAXONOMY


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class IngestResult:
    indexed: int = 0
    skipped: int = 0
    failed: int = 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dhash(image: Image.Image) -> str:
    pixels = np.asarray(image.convert("L").resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
    bits = (pixels[:, 1:] > pixels[:, :-1]).reshape(-1)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def image_metrics(image: Image.Image) -> dict[str, float]:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    edges = np.asarray(image.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    return {
        "mean_luma": float(gray.mean()),
        "contrast": float(gray.std()),
        "dark_fraction": float((gray < 64).mean()),
        "bright_fraction": float((gray > 192).mean()),
        "edge_density": float((edges > 32).mean()),
    }


def thumbnail(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    scratch = destination.with_suffix(".tmp.webp")
    image.convert("L").resize((192, 320), Image.Resampling.LANCZOS).save(scratch, "WEBP", quality=74, method=6)
    scratch.replace(destination)


def initialize_catalog(paths: CatalogPaths) -> dict[str, str | int]:
    paths.ensure()
    if not paths.source.is_dir():
        raise FileNotFoundError(
            f"Source directory does not exist: {paths.source}\n"
            "Pass --source /path/to/your/480x800-bmps or set X4CATALOG_SOURCE."
        )
    initialize(paths.database)
    with transaction(paths.database) as conn:
        set_setting(conn, "source_path", str(paths.source.resolve()))
        set_setting(conn, "created_at", get_setting(conn, "created_at") or utc_now())
        set_setting(conn, "network_policy", "local-only; one-time package/model downloads allowed")
        set_setting(conn, "source_write_policy", "never modify or create sidecars")
        for category, names in TAXONOMY.items():
            for name in names:
                conn.execute("INSERT OR IGNORE INTO tags(name, category) VALUES (?, ?)", (name, category))
        event(conn, "initialized", "catalog", "root", {"source": str(paths.source)})
    return {"source": str(paths.source), "database": str(paths.database), "free_gib": round(paths.available_bytes() / 1024**3, 2)}


def iter_sources(source: Path, limit: int | None = None) -> Iterable[Path]:
    count = 0
    for path in sorted(source.glob("*.bmp")):
        if path.is_file():
            yield path
            count += 1
            if limit is not None and count >= limit:
                return


def ingest(
    paths: CatalogPaths,
    *,
    limit: int | None = None,
    full: bool = False,
    pilot: bool = False,
    checkpoint_every: int = 100,
) -> IngestResult:
    """Index a source library, committing small checkpoints for safe resumption.

    Thumbnails can be safely recreated and source rows are unique by path.  A
    committed checkpoint therefore makes a Ctrl-C or power loss resume from the
    next unindexed image rather than losing an entire long-running library run.
    """
    if full:
        paths.assert_full_capacity()
    initialize_catalog(paths)
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every must be at least 1")
    result = IngestResult()
    indexed = skipped = failed = 0
    processed_since_checkpoint = 0
    conn = connect(paths.database)
    try:
        for source in iter_sources(paths.source, limit):
            try:
                stat = source.stat()
                existing = conn.execute(
                    "SELECT id, byte_size, mtime_ns FROM images WHERE source_path=?", (str(source),)
                ).fetchone()
                if existing and existing["byte_size"] == stat.st_size and existing["mtime_ns"] == stat.st_mtime_ns:
                    skipped += 1
                    continue
                with Image.open(source) as image:
                    image.load()
                    if image.size != (480, 800):
                        raise ValueError(f"expected 480x800, got {image.size[0]}x{image.size[1]}")
                    digest = sha256_file(source)
                    thumb_path = paths.thumbnails / f"{digest}.webp"
                    thumbnail(image, thumb_path)
                    metrics = image_metrics(image)
                    record = (
                        str(source), source.name, digest, stat.st_size, stat.st_mtime_ns,
                        image.size[0], image.size[1], image.mode, dhash(image), str(thumb_path),
                        metrics["mean_luma"], metrics["contrast"], metrics["dark_fraction"],
                        metrics["bright_fraction"], metrics["edge_density"],
                    )
                conn.execute(
                    """INSERT INTO images(
                        source_path, filename, sha256, byte_size, mtime_ns, width, height, image_mode,
                        dhash, thumb_path, mean_luma, contrast, dark_fraction, bright_fraction, edge_density
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_path) DO UPDATE SET
                      filename=excluded.filename, sha256=excluded.sha256, byte_size=excluded.byte_size,
                      mtime_ns=excluded.mtime_ns, width=excluded.width, height=excluded.height,
                      image_mode=excluded.image_mode, dhash=excluded.dhash, thumb_path=excluded.thumb_path,
                      mean_luma=excluded.mean_luma, contrast=excluded.contrast,
                      dark_fraction=excluded.dark_fraction, bright_fraction=excluded.bright_fraction,
                      edge_density=excluded.edge_density, state='indexed', updated_at=CURRENT_TIMESTAMP
                    """,
                    record,
                )
                indexed += 1
            except Exception as exc:  # cataloguing must continue past a bad file
                failed += 1
                event(conn, "ingest_failed", "source", str(source), {"error": str(exc)})
            processed_since_checkpoint += 1
            if processed_since_checkpoint >= checkpoint_every:
                conn.commit()
                processed_since_checkpoint = 0
        event(conn, "ingested", "run", utc_now(), {"indexed": indexed, "skipped": skipped, "failed": failed, "full": full, "pilot": pilot})
        if pilot:
            rows = conn.execute(
                "SELECT id, source_path, sha256 FROM images ORDER BY source_path LIMIT ?", (limit,)
            ).fetchall()
            manifest = {
                "created_at": utc_now(), "source": str(paths.source), "count": len(rows),
                "images": [dict(row) for row in rows],
            }
            (paths.runs / "pilot-500.json").write_text(json.dumps(manifest, indent=2))
        conn.commit()
    except BaseException:
        # Preserve the current valid checkpoint on cancellation. Any thumbnail
        # written after that checkpoint is harmless and will be re-indexed.
        conn.commit()
        raise
    finally:
        conn.close()
    return IngestResult(indexed=indexed, skipped=skipped, failed=failed)


def build_exact_duplicates(paths: CatalogPaths) -> int:
    initialize_catalog(paths)
    groups = 0
    with transaction(paths.database) as conn:
        conn.execute("DELETE FROM duplicate_members WHERE group_id IN (SELECT id FROM duplicate_groups WHERE kind='exact')")
        conn.execute("DELETE FROM duplicate_groups WHERE kind='exact'")
        rows = conn.execute(
            "SELECT sha256 FROM images GROUP BY sha256 HAVING COUNT(*) > 1"
        ).fetchall()
        for row in rows:
            cursor = conn.execute(
                "INSERT INTO duplicate_groups(kind, signature, confidence) VALUES ('exact', ?, 1.0)",
                (row["sha256"],),
            )
            group_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO duplicate_members(group_id, image_id) SELECT ?, id FROM images WHERE sha256=?",
                (group_id, row["sha256"]),
            )
            groups += 1
        event(conn, "duplicate_groups_rebuilt", "catalog", "root", {"exact_group_count": groups})
    return groups


def hamming_hex(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def build_variant_candidates(paths: CatalogPaths, max_distance: int = 6) -> int:
    """Conservative dHash candidates, partitioned by the first 16 hash bits."""
    initialize_catalog(paths)
    candidates: list[tuple[int, int, int]] = []
    with transaction(paths.database) as conn:
        buckets: dict[str, list[sqlite3.Row]] = {}
        for row in conn.execute("SELECT id, dhash FROM images ORDER BY id"):
            buckets.setdefault(row["dhash"][:4], []).append(row)
        for values in buckets.values():
            for index, left in enumerate(values):
                for right in values[index + 1:]:
                    distance = hamming_hex(left["dhash"], right["dhash"])
                    if distance <= max_distance:
                        candidates.append((left["id"], right["id"], distance))
        event(conn, "variant_candidates_built", "catalog", "root", {"candidates": len(candidates), "max_dhash_distance": max_distance})
    run_path = paths.runs / "variant-candidates.json"
    run_path.write_text(json.dumps([{"left": a, "right": b, "dhash_distance": d} for a, b, d in candidates], indent=2))
    return len(candidates)


def _safe_component(value: str) -> str:
    clean = re.sub(r"[^a-z0-9._-]+", "-", value.casefold()).strip(".-")
    return clean or "untagged"


def rebuild_views(paths: CatalogPaths) -> int:
    """Build published automatic and human-tag views atomically."""
    initialize_catalog(paths)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    staging = paths.root / f".views-{stamp}"
    staging.mkdir(parents=True, exist_ok=False)
    count = 0
    with transaction(paths.database) as conn:
        rows = conn.execute(
            """SELECT i.source_path, i.filename, t.category, t.name
               FROM image_tags it
               JOIN images i ON i.id=it.image_id
               JOIN tags t ON t.id=it.tag_id
               LEFT JOIN reviews r ON r.image_id=i.id
               WHERE (it.source IN ('machine','cluster') OR (it.source='human' AND it.confirmed=1))
                 AND COALESCE(r.decision, 'unreviewed') != 'reject'
               ORDER BY t.category, t.name, i.filename"""
        ).fetchall()
        for row in rows:
            destination_dir = staging / f"by-{_safe_component(row['category'])}" / _safe_component(row["name"])
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / row["filename"]
            source = Path(row["source_path"])
            if not destination.exists():
                destination.symlink_to(os.path.relpath(source, destination_dir))
                count += 1
        event(conn, "views_rebuilt", "catalog", "root", {"symlink_count": count, "staging": str(staging)})
    marker = staging / ".x4catalog-view"
    marker.write_text("Generated by x4catalog. Safe to regenerate; source BMPs live elsewhere.\n")
    if paths.views.exists():
        archive = paths.root / f"views-previous-{stamp}"
        paths.views.replace(archive)
    staging.replace(paths.views)
    return count


def export_automatic(paths: CatalogPaths) -> dict[str, object]:
    """Refresh a byte-identical export of every non-rejected indexed image."""
    initialize_catalog(paths)
    destination = paths.exports / "automatic"
    destination.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str | int]] = []
    copied = 0
    with transaction(paths.database) as conn:
        rows = conn.execute(
            """SELECT i.id, i.source_path, i.filename, i.sha256
               FROM images i LEFT JOIN reviews r ON r.image_id=i.id
               WHERE i.state='indexed' AND COALESCE(r.decision, 'unreviewed') != 'reject'
               ORDER BY i.filename"""
        ).fetchall()
        for row in rows:
            target = destination / row["filename"]
            if not target.is_file() or sha256_file(target) != row["sha256"]:
                temporary = target.with_suffix(target.suffix + ".tmp")
                shutil.copy2(row["source_path"], temporary)
                if sha256_file(temporary) != row["sha256"]:
                    temporary.unlink(missing_ok=True)
                    raise RuntimeError(f"Automatic export checksum mismatch for {row['filename']}")
                temporary.replace(target)
                copied += 1
            manifest.append({"image_id": row["id"], "filename": row["filename"], "sha256": row["sha256"]})
        manifest_path = destination / "manifest.json"
        temporary_manifest = manifest_path.with_suffix(".json.tmp")
        temporary_manifest.write_text(json.dumps({"created_at": utc_now(), "images": manifest}, indent=2) + "\n")
        temporary_manifest.replace(manifest_path)
        event(conn, "automatic_export_refreshed", "export", "automatic", {"count": len(manifest), "copied": copied})
    return {"path": str(destination), "count": len(manifest), "copied": copied}


def export_images(paths: CatalogPaths, name: str, image_ids: list[int]) -> dict[str, object]:
    if not image_ids:
        raise ValueError("Select at least one image to export")
    safe_name = _safe_component(name)
    destination = paths.exports / safe_name
    if destination.exists():
        raise FileExistsError(f"Export already exists: {destination}")
    destination.mkdir(parents=True)
    manifest: list[dict[str, str | int]] = []
    with transaction(paths.database) as conn:
        placeholders = ",".join("?" for _ in image_ids)
        rows = conn.execute(
            f"SELECT id, source_path, filename, sha256 FROM images WHERE id IN ({placeholders}) ORDER BY filename",
            image_ids,
        ).fetchall()
        if len(rows) != len(set(image_ids)):
            raise ValueError("One or more selected images are not catalogued")
        for row in rows:
            target = destination / row["filename"]
            shutil.copy2(row["source_path"], target)
            actual = sha256_file(target)
            if actual != row["sha256"]:
                raise RuntimeError(f"Export checksum mismatch for {row['filename']}")
            manifest.append({"image_id": row["id"], "filename": row["filename"], "sha256": actual})
        (destination / "manifest.json").write_text(json.dumps({"created_at": utc_now(), "images": manifest}, indent=2))
        event(conn, "export_created", "export", safe_name, {"count": len(manifest), "path": str(destination)})
    return {"name": safe_name, "path": str(destination), "count": len(manifest)}
