from __future__ import annotations

import json

from x4catalog.catalog import ingest
from x4catalog.publish import build_snapshot, publish

from test_catalog import configured


def test_snapshot_omits_local_filesystem_paths(tmp_path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    snapshot = build_snapshot(paths)
    assert snapshot["mode"] == "hosted"
    assert snapshot["image_count"] == 3
    assert snapshot["images"]
    from x4catalog.publish import _public_image

    for item in snapshot["images"]:
        published = _public_image(item, has_thumb=True, has_source=False)
        assert "source_path" not in published
        assert "local_source" not in published
        assert "thumbnail_path" not in published
        assert published["thumbnail_url"].startswith("/thumbs/")
        assert published["source_url"] is None
        assert "sensitive" in published


def test_public_image_uses_cdn_base_and_marks_sensitive() -> None:
    from x4catalog.publish import _public_image

    item = {
        "id": 9,
        "filename": "study_x4.bmp",
        "sha256": "abc123",
        "byte_size": 480000,
        "mean_luma": 40,
        "contrast": 0.2,
        "edge_density": 0.1,
        "decision": "keep",
        "rating": None,
        "x4_suitability": "good",
        "ocr_text": "",
        "ocr_processed": False,
        "tags": [{"name": "nsfw", "source": "machine", "confidence": 0.9}],
        "cluster_ids": [],
    }
    published = _public_image(
        item,
        has_thumb=True,
        has_source=True,
        public_base="https://cdn.example.com",
    )
    assert published["sensitive"] is True
    assert published["thumbnail_url"] == "https://cdn.example.com/thumbs/abc123.webp"
    assert published["source_url"] == "https://cdn.example.com/sources/abc123.bmp"


def test_publish_cache_busts_cdn_catalog_url(tmp_path) -> None:
    paths = configured(tmp_path)
    ingest(paths, limit=3)
    result = publish(paths, public_base="https://cdn.example.com")
    assert result["catalog_url"].startswith("https://cdn.example.com/catalog.json?v=")
    pointer = json.loads((paths.static / "catalog-url.json").read_text())
    assert pointer["url"] == result["catalog_url"]
    local = publish(paths)
    assert local["catalog_url"] == "/catalog.json"
