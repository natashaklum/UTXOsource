"""Filesystem layout: one code checkout, one data directory (Sprint 12).

Everything utxoproof writes — the SQLite DB, evidence files, price cache —
lives under a single *data directory* so real financial data never mixes
with the code checkout and never sprays across home. Resolution order:

1. explicit CLI flags (``--data-dir``, ``--db``, ``--evidence-dir``),
2. ``UTXOPROOF_DATA_DIR`` environment variable,
3. ``~/.utxoproof`` default.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

DEFAULT_DATA_DIR = "~/.utxoproof"


def add_data_dir_arg(parser: argparse.ArgumentParser) -> None:
    """Global ``--data-dir`` flag, available on every subcommand."""
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Data directory for DB + evidence (default: $UTXOPROOF_DATA_DIR or ~/.utxoproof)",
    )


def data_dir(explicit: str | None = None) -> Path:
    """Resolve the data directory from flag, env, or default (in that order)."""
    raw = explicit or os.environ.get("UTXOPROOF_DATA_DIR") or DEFAULT_DATA_DIR
    return Path(raw).expanduser()


def db_path(args: argparse.Namespace) -> Path:
    """``--db`` wins; otherwise ``<data-dir>/utxoproof.db``."""
    if getattr(args, "db", None):
        return Path(args.db).expanduser()
    return data_dir(getattr(args, "data_dir", None)) / "utxoproof.db"


def evidence_root(args: argparse.Namespace) -> Path:
    """``--evidence-dir`` wins; otherwise ``<data-dir>/evidence``."""
    if getattr(args, "evidence_dir", None):
        return Path(args.evidence_dir).expanduser()
    return data_dir(getattr(args, "data_dir", None)) / "evidence"
