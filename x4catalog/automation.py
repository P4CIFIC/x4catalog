from __future__ import annotations

from .analysis import embed, ocr
from .catalog import export_automatic, ingest, rebuild_views
from .config import CatalogPaths
from .db import connect, event, transaction
from .labeling import LABEL_MODEL_REVISIONS, auto_label, reclassify_predictions


def _missing_work(paths: CatalogPaths) -> tuple[int, int, int]:
    with connect(paths.database) as conn:
        images = int(conn.execute("SELECT COUNT(*) FROM images WHERE state='indexed'").fetchone()[0])
        missing_embeddings = int(conn.execute(
            "SELECT COUNT(*) FROM images i LEFT JOIN embeddings e ON e.image_id=i.id WHERE i.state='indexed' AND e.image_id IS NULL"
        ).fetchone()[0])
        missing_ocr = int(conn.execute(
            "SELECT COUNT(*) FROM images i LEFT JOIN ocr_results o ON o.image_id=i.id WHERE i.state='indexed' AND o.image_id IS NULL"
        ).fetchone()[0])
        revision_checks = " AND ".join(
            "EXISTS (SELECT 1 FROM label_predictions p WHERE p.image_id=i.id AND p.model=? AND p.model_revision=?)"
            for _ in LABEL_MODEL_REVISIONS
        )
        revision_params = [value for pair in LABEL_MODEL_REVISIONS.items() for value in pair]
        labeled = int(conn.execute(
            f"SELECT COUNT(*) FROM images i WHERE i.state='indexed' AND {revision_checks}",
            revision_params,
        ).fetchone()[0])
    return images, missing_embeddings + missing_ocr, labeled


def automate(
    paths: CatalogPaths,
    *,
    export_all: bool = False,
    label_limit: int | None = None,
    batch_size: int = 8,
) -> dict[str, object]:
    """Run the incremental local pipeline manually on the local machine."""
    ingest_result = ingest(paths, full=False)
    confidence_policy = reclassify_predictions(paths)
    images, missing_prework, labeled = _missing_work(paths)
    stages: dict[str, object] = {
        "ingest": ingest_result.__dict__,
        "confidence_policy": confidence_policy,
        "images": images,
    }
    if missing_prework:
        with connect(paths.database) as conn:
            missing_embeddings = int(conn.execute(
                "SELECT COUNT(*) FROM images i LEFT JOIN embeddings e ON e.image_id=i.id WHERE i.state='indexed' AND e.image_id IS NULL"
            ).fetchone()[0])
            missing_ocr = int(conn.execute(
                "SELECT COUNT(*) FROM images i LEFT JOIN ocr_results o ON o.image_id=i.id WHERE i.state='indexed' AND o.image_id IS NULL"
            ).fetchone()[0])
        if missing_embeddings:
            stages["embeddings"] = embed(paths).__dict__
        if missing_ocr:
            stages["ocr"] = {"processed": ocr(paths)}
    if labeled < images or label_limit is not None:
        stages["labels"] = auto_label(paths, limit=label_limit, batch_size=batch_size)
    stages["views"] = {"symlink_count": rebuild_views(paths)}
    if export_all:
        stages["exports"] = export_automatic(paths)
    with transaction(paths.database) as conn:
        event(conn, "automation_completed", "run", "manual", {"stages": stages})
    return stages
