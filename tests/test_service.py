from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from x4catalog.config import CatalogPaths
from x4catalog.service import create_app
import x4catalog.service as service


def configured(tmp_path: Path) -> CatalogPaths:
    root = tmp_path / "catalog"
    (root / "static").mkdir(parents=True)
    (root / "static" / "index.html").write_text("<main>local</main>")
    return CatalogPaths(root=root, source=tmp_path / "source")


def test_crosspoint_move_forwards_destination_folder(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_request(host, path, *, method="GET", form=None):
        calls.append((host, path, method, form))
        return b"{}", "application/json"

    monkeypatch.setattr(service, "_crosspoint_request", fake_request)
    client = TestClient(create_app(configured(tmp_path)))

    response = client.post("/api/crosspoint/move", json={
        "host": "192.168.1.50",
        "path": "/Books/mybook.epub",
        "dest": "/Read",
    })

    assert response.status_code == 200
    assert calls == [("192.168.1.50", "/move", "POST", {"path": "/Books/mybook.epub", "dest": "/Read"})]


def test_crosspoint_mkdir_forwards_parent_and_visible_name(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_request(host, path, *, method="GET", form=None):
        calls.append((host, path, method, form))
        return b"{}", "application/json"

    monkeypatch.setattr(service, "_crosspoint_request", fake_request)
    client = TestClient(create_app(configured(tmp_path)))

    response = client.post("/api/crosspoint/mkdir", json={
        "host": "crosspoint.local",
        "path": "/Books",
        "name": "To Read",
    })

    assert response.status_code == 200
    assert calls == [("crosspoint.local", "/mkdir", "POST", {"path": "/Books", "name": "To Read"})]


def test_crosspoint_book_actions_reject_hidden_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(service, "_crosspoint_request", lambda *args, **kwargs: (b"{}", "application/json"))
    client = TestClient(create_app(configured(tmp_path)))

    response = client.post("/api/crosspoint/move", json={
        "host": "192.168.1.50",
        "path": "/.sleep/screen.bmp",
        "dest": "/Books",
    })

    assert response.status_code == 400
    assert "Hidden CrossPoint paths" in response.json()["detail"]


def test_spa_routes_serve_the_web_ui(tmp_path: Path) -> None:
    client = TestClient(create_app(configured(tmp_path)))
    for path in ("/", "/browse", "/docs", "/device"):
        response = client.get(path)
        assert response.status_code == 200
        assert b"<main>local</main>" in response.content


def test_crosspoint_url_normalizes_zero_port_without_allowing_a_host_path() -> None:
    assert service._crosspoint_url("192.168.1.50:0", "/api/status") == "http://192.168.1.50/api/status"
    assert service._crosspoint_url("https://crosspoint.local", "/api/status") == "http://crosspoint.local/api/status"

    try:
        service._crosspoint_url("192.168.1.50?redirect=/", "/api/status")
    except service.HTTPException as error:
        assert error.status_code == 400
    else:
        raise AssertionError("CrossPoint host query text must be rejected")
