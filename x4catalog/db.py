from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    image_mode TEXT NOT NULL,
    dhash TEXT NOT NULL,
    thumb_path TEXT NOT NULL,
    mean_luma REAL NOT NULL,
    contrast REAL NOT NULL,
    dark_fraction REAL NOT NULL,
    bright_fraction REAL NOT NULL,
    edge_density REAL NOT NULL,
    state TEXT NOT NULL DEFAULT 'indexed' CHECK(state IN ('indexed','failed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS images_sha_idx ON images(sha256);
CREATE INDEX IF NOT EXISTS images_dhash_idx ON images(dhash);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('exact','variant')),
    signature TEXT NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(kind, signature)
);

CREATE TABLE IF NOT EXISTS duplicate_members (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    PRIMARY KEY(group_id, image_id)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS image_tags (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK(source IN ('machine','cluster','human')),
    confidence REAL,
    confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(image_id, tag_id, source)
);
CREATE INDEX IF NOT EXISTS image_tags_confirmed_idx ON image_tags(confirmed, tag_id);

CREATE TABLE IF NOT EXISTS label_runs (
    id INTEGER PRIMARY KEY,
    bundle TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
    device TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    processed INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS label_runs_status_idx ON label_runs(status, started_at);

CREATE TABLE IF NOT EXISTS label_predictions (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    raw_label TEXT NOT NULL,
    tag_id INTEGER REFERENCES tags(id) ON DELETE SET NULL,
    score REAL NOT NULL,
    confidence_band TEXT NOT NULL CHECK(confidence_band IN ('likely','possible','weak')),
    published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
    run_id INTEGER REFERENCES label_runs(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(image_id, model, model_revision, raw_label)
);
CREATE INDEX IF NOT EXISTS label_predictions_tag_idx ON label_predictions(tag_id, published, score);
CREATE INDEX IF NOT EXISTS label_predictions_model_idx ON label_predictions(model, model_revision, image_id);

CREATE TABLE IF NOT EXISTS embeddings (
    image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector BLOB NOT NULL,
    device TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ocr_results (
    image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    text_density REAL NOT NULL,
    minimum_text_height REAL,
    has_small_text INTEGER NOT NULL DEFAULT 0 CHECK(has_small_text IN (0,1)),
    engine TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(image_id UNINDEXED, text);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY,
    algorithm TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cluster_members (
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    distance REAL,
    outlier INTEGER NOT NULL DEFAULT 0 CHECK(outlier IN (0,1)),
    PRIMARY KEY(cluster_id, image_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    decision TEXT NOT NULL DEFAULT 'unreviewed' CHECK(decision IN ('unreviewed','keep','reject','favorite')),
    rating INTEGER CHECK(rating BETWEEN 0 AND 5),
    x4_suitability TEXT CHECK(x4_suitability IN ('excellent','good','acceptable','too-dark','too-busy','too-fine','small-text','needs-dithering','review')),
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preference_models (
    id INTEGER PRIMARY KEY,
    version TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    weights BLOB NOT NULL,
    bias REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preference_scores (
    image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    model_id INTEGER NOT NULL REFERENCES preference_models(id) ON DELETE CASCADE,
    score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: Path) -> sqlite3.Connection:
    # Local review requests and a background checkpoint can briefly overlap.
    # WAL plus a bounded busy wait is preferable to immediately failing a
    # checkpoint while another local writer is committing.
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def initialize(path: Path) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def transaction(path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def event(conn: sqlite3.Connection, event_type: str, entity_type: str, entity_id: str | int, payload: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO events(event_type, entity_type, entity_id, payload_json) VALUES (?, ?, ?, ?)",
        (event_type, entity_type, str(entity_id), json.dumps(payload or {}, sort_keys=True)),
    )


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return None if row is None else str(row["value"])
