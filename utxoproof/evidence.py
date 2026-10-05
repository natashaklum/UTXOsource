"""Evidence packaging (plan Sec. 15, Sprint 9).

Assembles the reproducible evidence bundle for a tax year: raw sources,
intermediate inputs, the HTML report, a manifest SQLite DB copy, and a
SHA-256 manifest. Duplicate source imports are rejected on content hash.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

from utxoproof import __version__
from utxoproof.db import init_db


def sha256_file(path: str | Path) -> str:
    """SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_source(db: sqlite3.Connection, path: str | Path, role: str) -> bool:
    """Record a source file in the manifest. False when its hash exists."""
    file = Path(path)
    digest = sha256_file(file)
    try:
        db.execute(
            "INSERT INTO source_manifest (filename, sha256, size_bytes, role, imported_at)"
            " VALUES (?,?,?,?,?)",
            (
                file.name,
                digest,
                file.stat().st_size,
                role,
                datetime.datetime.now(datetime.UTC).isoformat(),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return False  # duplicate content already recorded
    return True


def produce_evidence_zip(
    year: int,
    manifest_db_path: str | Path,
    report_html_path: str | Path,
    sources: list[Path],
    intermediate: list[Path],
    output_dir: str | Path,
    timestamp: str | None = None,
) -> Path:
    """Build ``utxoproof_evidence_<year>_<timestamp>.zip``. Returns its path."""
    stamp = timestamp or datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / f"utxoproof_evidence_{year}_{stamp}.zip"

    manifest_files: list[dict[str, object]] = []
    manifest: dict[str, object] = {
        "generated_at": stamp,
        "tax_year": year,
        "utxoproof_version": __version__,
        "files": manifest_files,
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for role, arc_dir, paths in (
            ("source", "sources", sources),
            ("intermediate", "intermediate", intermediate),
        ):
            for file in paths:
                arcname = f"{arc_dir}/{Path(file).name}"
                zf.write(file, arcname=arcname)
                manifest_files.append({"path": arcname, "sha256": sha256_file(file), "role": role})
        zf.write(report_html_path, arcname="report.html")
        manifest_files.append(
            {
                "path": "report.html",
                "sha256": sha256_file(report_html_path),
                "role": "report",
            }
        )
        zf.write(manifest_db_path, arcname="evidence.db")
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return zip_path


def build_manifest_db(path: str | Path) -> sqlite3.Connection:
    """Create a manifest-only evidence DB at ``path``."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path))
    init_db(db)
    return db
