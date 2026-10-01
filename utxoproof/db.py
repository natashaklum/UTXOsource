"""SQLite helpers for Sprint 0: create the full Sec. 8 schema now."""

from __future__ import annotations

import sqlite3
from importlib import resources


def init_db(db: sqlite3.Connection) -> None:
    """Create all utxoproof tables if absent."""
    schema = resources.files("utxoproof").joinpath("schema.sql").read_text(encoding="utf-8")
    db.executescript(schema)


def open_memory_db() -> sqlite3.Connection:
    """In-memory DB with schema applied (used by tests)."""
    db = sqlite3.connect(":memory:")
    init_db(db)
    return db
