from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil


MIN_FULL_FREE_BYTES = 50 * 1024**3
BIND_HOST = "127.0.0.1"


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def default_root() -> Path:
    return _env_path("X4CATALOG_ROOT") or Path.cwd()


def default_source() -> Path:
    return _env_path("X4CATALOG_SOURCE") or Path.cwd() / "library"


def default_static() -> Path:
    return _env_path("X4CATALOG_STATIC") or package_root() / "static"


@dataclass(frozen=True)
class CatalogPaths:
    root: Path
    source: Path
    static_dir: Path | None = None

    @property
    def database(self) -> Path:
        return self.root / "x4-catalog.sqlite"

    @property
    def thumbnails(self) -> Path:
        return self.root / "thumbnails"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def views(self) -> Path:
        return self.root / "views"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def static(self) -> Path:
        if self.static_dir is not None:
            return self.static_dir
        local = self.root / "static"
        if (local / "index.html").is_file():
            return local
        return default_static()

    def ensure(self) -> None:
        for path in (self.root, self.thumbnails, self.models, self.runs, self.views, self.exports):
            path.mkdir(parents=True, exist_ok=True)

    def available_bytes(self) -> int:
        return shutil.disk_usage(self.root).free

    def assert_full_capacity(self) -> None:
        free = self.available_bytes()
        if free < MIN_FULL_FREE_BYTES:
            gib = free / 1024**3
            raise RuntimeError(
                f"Full-library processing is blocked: {gib:.1f} GiB free; "
                "50 GiB minimum required. Use --pilot for a bounded validation run."
            )
