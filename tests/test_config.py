from __future__ import annotations

from x4catalog.analysis import ocr_source_path
from x4catalog.config import BIND_HOST, CatalogPaths, default_root, default_source, default_static
from x4catalog.cli import parser, paths_from


def test_defaults_are_local_and_not_personal_home_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("X4CATALOG_ROOT", raising=False)
    monkeypatch.delenv("X4CATALOG_SOURCE", raising=False)
    monkeypatch.delenv("X4CATALOG_STATIC", raising=False)
    root = default_root()
    source = default_source()
    static = default_static()
    assert root == tmp_path
    assert source == tmp_path / "library"
    assert static.name == "static"
    assert static.is_dir()
    assert BIND_HOST == "127.0.0.1"


def test_environment_overrides_root_and_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("X4CATALOG_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("X4CATALOG_SOURCE", str(tmp_path / "bmps"))
    monkeypatch.setenv("X4CATALOG_STATIC", str(tmp_path / "ui"))
    assert default_root() == tmp_path / "data"
    assert default_source() == tmp_path / "bmps"
    assert default_static() == tmp_path / "ui"


def test_cli_paths_honor_flags_and_env(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("X4CATALOG_SOURCE", str(tmp_path / "from-env"))
    args = parser().parse_args(["init", "--root", str(tmp_path / "catalog")])
    paths = paths_from(args)
    assert paths.root == tmp_path / "catalog"
    assert paths.source == tmp_path / "from-env"


def test_static_prefers_an_existing_root_ui(tmp_path) -> None:
    root = tmp_path / "catalog"
    source = tmp_path / "library"
    source.mkdir()
    ui = root / "static"
    ui.mkdir(parents=True)
    (ui / "index.html").write_text("<main>local</main>")
    paths = CatalogPaths(root=root, source=source)
    assert paths.static == ui


def test_ocr_helper_ships_in_the_package() -> None:
    path = ocr_source_path()
    assert path.is_file()
    assert path.name == "vision_ocr.swift"
    assert path.parent.name == "x4catalog"
