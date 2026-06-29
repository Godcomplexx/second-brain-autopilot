"""SQLite database and forward-only migrations for generated tracking systems."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "systems.db"
_LATEST_VERSION = 1

_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS systems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_prompt TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL REFERENCES systems(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE(system_id, name)
);

CREATE TABLE IF NOT EXISTS fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    field_key TEXT NOT NULL,
    field_type TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 0,
    options_json TEXT NOT NULL DEFAULT '[]',
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE(entity_id, name),
    UNIQUE(entity_id, field_key)
);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS record_values (
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    value_json TEXT NOT NULL,
    PRIMARY KEY(record_id, field_id)
);

CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL REFERENCES systems(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE(system_id, name)
);

CREATE TABLE IF NOT EXISTS habit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    log_date TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 1,
    UNIQUE(habit_id, log_date)
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL REFERENCES systems(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE(system_id, name)
);

CREATE INDEX IF NOT EXISTS idx_entities_system ON entities(system_id);
CREATE INDEX IF NOT EXISTS idx_records_entity ON records(entity_id);
CREATE INDEX IF NOT EXISTS idx_habits_system ON habits(system_id);
CREATE INDEX IF NOT EXISTS idx_metrics_system ON metrics(system_id);
"""


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Bring *connection* to the latest schema version."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER NOT NULL)"
    )
    row = connection.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()
    version = int(row["version"]) if row else 0
    if version < 1:
        connection.executescript(_MIGRATION_1)
        connection.execute("DELETE FROM schema_version")
        connection.execute("INSERT INTO schema_version(version) VALUES (1)")
    if version > _LATEST_VERSION:
        raise RuntimeError(
            f"Database version {version} is newer than supported {_LATEST_VERSION}"
        )


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Yield an initialized connection and commit or roll back atomically."""
    db = _connect()
    try:
        migrate(db)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize() -> None:
    with connection():
        pass
