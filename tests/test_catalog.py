from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from x4catalog.catalog import build_exact_duplicates, export_images, ingest, initialize_catalog, rebuild_views
from x4catalog.config import CatalogPaths
from x4catalog.db import connect, transaction
from x4catalog.service import create_app
from x4catalog.labeling import Prediction, _persist_predictions, normalize_label, reclassify_predictions


def write_bmp(path: Path, text: str = "") -> None:
    image = Image.new("L", (480, 800), 246)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 120, 440, 680), outline=20, width=12)
    if text:
        draw.text((100, 370), text, fill=20)
    image.save(path, "BMP")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configured(tmp_path: Path) -> CatalogPaths:
    source = tmp_path / "source"
    source.mkdir()
    root = tmp_path / "catalog"
    (root / "static").mkdir(parents=True)
    (root / "static" / "index.html").write_text("<main>local</main>")
    write_bmp(source / "a.bmp", "A")
    write_bmp(source / "duplicate.bmp", "A")
    write_bmp(source / "b.bmp", "B")
    return CatalogPaths(root=root, source=source)


def test_ingest_is_resumable_and_never_changes_source(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    before = {file.name: digest(file) for file in paths.source.glob("*.bmp")}
    initialize_catalog(paths)
    first = ingest(paths, limit=3, pilot=True)
    second = ingest(paths, limit=3)
    assert first.indexed == 3
    assert second.skipped == 3
    assert before == {file.name: digest(file) for file in paths.source.glob("*.bmp")}
    with connect(paths.database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 3
    assert len(list(paths.thumbnails.glob("*.webp"))) == 2
    assert (paths.runs / "pilot-500.json").is_file()


def test_interrupted_ingest_resumes_from_a_committed_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = configured(tmp_path)
    before = {file.name: digest(file) for file in paths.source.glob("*.bmp")}
    from x4catalog import catalog

    original_thumbnail = catalog.thumbnail
    calls = 0

    def interrupting_thumbnail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise KeyboardInterrupt
        return original_thumbnail(*args, **kwargs)

    monkeypatch.setattr(catalog, "thumbnail", interrupting_thumbnail)
    with pytest.raises(KeyboardInterrupt):
        ingest(paths, limit=3, checkpoint_every=1)
    with connect(paths.database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 2

    monkeypatch.setattr(catalog, "thumbnail", original_thumbnail)
    resumed = ingest(paths, limit=3, checkpoint_every=1)
    assert resumed.indexed == 1
    with connect(paths.database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 3
    assert before == {file.name: digest(file) for file in paths.source.glob("*.bmp")}


def test_duplicate_groups_and_export_hashes(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    assert build_exact_duplicates(paths) == 1
    with connect(paths.database) as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM images ORDER BY id LIMIT 2")]
    result = export_images(paths, "best", ids)
    exported = sorted((Path(result["path"])).glob("*.bmp"))
    assert len(exported) == 2
    for file in exported:
        assert digest(file) in {digest(source) for source in paths.source.glob("*.bmp")}


def test_confirmed_tags_make_relative_symlink_views(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    with transaction(paths.database) as conn:
        image_id = conn.execute("SELECT id FROM images ORDER BY id LIMIT 1").fetchone()[0]
        tag_id = conn.execute("SELECT id FROM tags WHERE name='botanical'").fetchone()[0]
        conn.execute("INSERT INTO image_tags(image_id, tag_id, source, confidence, confirmed) VALUES (?, ?, 'human', 1, 1)", (image_id, tag_id))
    assert rebuild_views(paths) == 1
    links = list(paths.views.rglob("*.bmp"))
    assert len(links) == 1
    assert links[0].is_symlink()
    assert links[0].resolve().parent == paths.source


def test_empty_confirmed_tag_set_still_builds_an_atomic_view_root(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    assert rebuild_views(paths) == 0
    assert (paths.views / ".x4catalog-view").is_file()


def test_automatic_labels_are_published_without_human_confirmation(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    with transaction(paths.database) as conn:
        image_id = conn.execute("SELECT id FROM images ORDER BY id LIMIT 1").fetchone()[0]
        tag_id = conn.execute("SELECT id FROM tags WHERE name='bold'").fetchone()[0]
        conn.execute(
            "INSERT INTO image_tags(image_id, tag_id, source, confidence, confirmed) VALUES (?, ?, 'machine', 0.82, 0)",
            (image_id, tag_id),
        )
    assert rebuild_views(paths) == 1
    link = next(paths.views.rglob("*.bmp"))
    assert link.is_symlink()
    assert link.resolve().parent == paths.source
    client = TestClient(create_app(paths))
    tagged = client.get("/api/images?tag=bold").json()
    assert len(tagged["items"]) == 1
    assert tagged["total"] == 1
    stacked = client.get("/api/images?tags=bold").json()
    assert stacked["total"] == 1
    assert client.get("/api/tags").json()["items"]


def test_search_matches_machine_tags_and_dynamic_tag_filtering(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    with transaction(paths.database) as conn:
        image_id = conn.execute("SELECT id FROM images ORDER BY id LIMIT 1").fetchone()[0]
        tag_id = conn.execute("SELECT id FROM tags WHERE name='rick-and-morty'").fetchone()[0]
        conn.execute(
            "INSERT INTO image_tags(image_id, tag_id, source, confidence, confirmed) VALUES (?, ?, 'machine', 0.9, 0)",
            (image_id, tag_id),
        )
    client = TestClient(create_app(paths))
    search = client.get("/api/images?q=Rick and Morty").json()
    assert search["items"][0]["id"] == image_id
    assert search["total"] == 1
    tag_items = client.get("/api/tags?q=rick").json()["items"]
    assert tag_items[0]["name"] == "rick-and-morty"
    with transaction(paths.database) as conn:
        bold_id = conn.execute("SELECT id FROM tags WHERE name='bold'").fetchone()[0]
        conn.execute(
            "INSERT INTO image_tags(image_id, tag_id, source, confidence, confirmed) VALUES (?, ?, 'machine', 0.8, 0)",
            (image_id, bold_id),
        )
    both = client.get("/api/images?tags=rick-and-morty,bold").json()
    assert both["total"] == 1
    missing = client.get("/api/images?tags=rick-and-morty,pokemon").json()
    assert missing["total"] == 0
    ids = client.get("/api/images/ids?q=Rick and Morty").json()
    assert ids["ids"] == [image_id]
    assert ids["total"] == 1


def test_device_page_uses_the_local_spa_entrypoint(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    client = TestClient(create_app(paths))
    response = client.get("/device")
    assert response.status_code == 200
    assert response.text == "<main>local</main>"


def test_label_normalization_preserves_bold_and_content_terms() -> None:
    assert normalize_label("rating:explicit") == "nsfw"
    assert normalize_label("high_contrast") == "high-contrast"
    assert normalize_label("bold") == "bold"
    assert normalize_label("character:Rick_Sanchez") == "rick-sanchez"
    assert normalize_label("artist:someone") is None


def test_sensitive_tag_helper_covers_nsfw_and_ignores_subject_tags() -> None:
    from x4catalog.taxonomy import image_is_sensitive

    assert image_is_sensitive([{"name": "nsfw"}]) is True
    assert image_is_sensitive(["nudity", "landscape"]) is True
    assert image_is_sensitive([{"name": "landscape"}, {"name": "high-contrast"}]) is False


def test_low_confidence_predictions_remain_evidence_only(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    with transaction(paths.database) as conn:
        image_id = conn.execute("SELECT id FROM images ORDER BY id LIMIT 1").fetchone()[0]
        run_id = conn.execute(
            "INSERT INTO label_runs(bundle, status, device, total) VALUES ('test', 'running', 'cpu', 1)"
        ).lastrowid
        _persist_predictions(conn, run_id, image_id, [
            Prediction("breasts", 0.75, "rampp"),
            Prediction("grayscale", 0.81, "wd14"),
        ])
        rows = conn.execute(
            "SELECT raw_label, published FROM label_predictions WHERE image_id=? ORDER BY raw_label",
            (image_id,),
        ).fetchall()
    assert [(row["raw_label"], row["published"]) for row in rows] == [("breasts", 0), ("grayscale", 1)]


def test_confidence_policy_reclassifies_existing_machine_tags(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    with transaction(paths.database) as conn:
        image_id = conn.execute("SELECT id FROM images ORDER BY id LIMIT 1").fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO tags(name, category) VALUES ('breasts', 'model')")
        tag_id = conn.execute("SELECT id FROM tags WHERE name='breasts'").fetchone()[0]
        conn.execute("INSERT INTO image_tags(image_id, tag_id, source, confidence, confirmed) VALUES (?, ?, 'machine', 0.75, 0)", (image_id, tag_id))
        run_id = conn.execute(
            "INSERT INTO label_runs(bundle, status, device, total) VALUES ('test', 'completed', 'cpu', 1)"
        ).lastrowid
        _persist_predictions(conn, run_id, image_id, [Prediction("breasts", 0.75, "rampp")])
    result = reclassify_predictions(paths)
    assert result["changed"] is True
    with connect(paths.database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM image_tags WHERE source='machine'").fetchone()[0] == 0


def test_init_explains_a_missing_source_directory(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    source = tmp_path / "missing-library"
    with pytest.raises(FileNotFoundError, match="X4CATALOG_SOURCE"):
        initialize_catalog(CatalogPaths(root=root, source=source))


def test_ocr_is_macos_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from x4catalog import analysis

    monkeypatch.setattr(analysis.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="macOS"):
        analysis.compile_ocr_worker(configured(tmp_path))


def test_local_api_binds_catalog_only(tmp_path: Path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    client = TestClient(create_app(paths))
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["bind"] == "127.0.0.1"
    images = client.get("/api/images")
    assert images.status_code == 200
    assert len(images.json()["items"]) == 3
    image_id = images.json()["items"][0]["id"]
    source = client.get(f"/api/images/{image_id}/source")
    assert source.status_code == 200
    assert hashlib.sha256(source.content).hexdigest() in {digest(file) for file in paths.source.glob("*.bmp")}
