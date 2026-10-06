"""Attachments: register, link, thumbnail, package (Sprint 11)."""

import binascii
import struct
import zlib
from pathlib import Path

import pytest

from utxoproof.db import open_memory_db
from utxoproof.evidence import (
    attach_file,
    attachments_for_txids,
    thumbnail_data_uri,
)


def sample_png(rgb: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    """Minimal valid 1x1 PNG (dummy receipt placeholder for tests)."""

    def chunk(typ: bytes, data: bytes) -> bytes:
        body = struct.pack(">I", len(data)) + typ + data
        return body + struct.pack(">I", binascii.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00" + bytes(rgb)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def test_attach_copies_hashes_records_links(tmp_path: Path) -> None:
    db = open_memory_db()
    src = tmp_path / "receipt.png"
    src.write_bytes(sample_png())
    root = tmp_path / "evidence"

    entry = attach_file(db, src, root, 2023, txid="abc", note="withdrawal mail")
    assert entry["filename"] == "2023/receipt.png"
    assert len(entry["sha256"]) == 64
    assert (root / "2023" / "receipt.png").is_file()
    # Original untouched; registry copy is what counts.
    assert src.is_file()

    rows = attachments_for_txids(db, root, ["abc"])
    assert len(rows) == 1
    assert rows[0]["note"] == "withdrawal mail"
    assert rows[0]["path"] == str(root / "2023" / "receipt.png")
    assert attachments_for_txids(db, root, ["other"]) == []

    # Re-attaching same content: new copy, manifest dedupe keeps one hash row.
    entry2 = attach_file(db, src, root, 2023, txid="abc")
    assert entry2["filename"] == "2023/receipt-1.png"
    assert entry2["sha256"] == entry["sha256"]
    count = db.execute(
        "SELECT COUNT(*) FROM source_manifest WHERE sha256=?", (entry["sha256"],)
    ).fetchone()
    assert count == (1,)


def test_attach_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        attach_file(open_memory_db(), tmp_path / "nope.pdf", tmp_path, 2023)


def test_thumbnails(tmp_path: Path) -> None:
    small = tmp_path / "small.png"
    small.write_bytes(sample_png())
    uri = thumbnail_data_uri(small)
    assert uri is not None and uri.startswith("data:image/png;base64,")

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    assert thumbnail_data_uri(pdf) is None

    big = tmp_path / "big.png"
    big.write_bytes(b"\x00" * 2_000_001)
    assert thumbnail_data_uri(big) is None


def test_provenance_page_lists_attachments(tmp_path: Path) -> None:
    import datetime
    from decimal import Decimal

    from utxoproof.kyc import create_sample_graph
    from utxoproof.reports import write_provenance_page

    db = create_sample_graph()
    root = tmp_path / "evidence"
    src = tmp_path / "confirm.png"
    src.write_bytes(sample_png())
    attach_file(db, src, root, 2023, txid="C", note="exchange mail")
    pdf = tmp_path / "statement.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    attach_file(db, pdf, root, 2023, txid="C")

    target = write_provenance_page(
        db,
        "D",
        0,
        lambda day: Decimal("30000"),
        Decimal("40000"),
        datetime.date(2024, 6, 1),
        tmp_path,
        evidence_root=root,
    )
    html = target.read_text(encoding="utf-8")
    assert "Attachments" in html
    assert "confirm.png" in html and "data:image/png;base64," in html
    assert "statement.pdf" in html
    assert "exchange mail" in html


def test_provenance_without_root_has_empty_section(tmp_path: Path) -> None:
    import datetime
    from decimal import Decimal

    from utxoproof.kyc import create_sample_graph
    from utxoproof.reports import write_provenance_page

    target = write_provenance_page(
        create_sample_graph(),
        "D",
        0,
        lambda day: Decimal("30000"),
        Decimal("40000"),
        datetime.date(2024, 6, 1),
        tmp_path,
    )
    assert "No attachments registered" in target.read_text(encoding="utf-8")


def test_cli_attach_and_zip_include_attachments(tmp_path: Path) -> None:
    import sqlite3
    import zipfile

    from utxoproof.cli import main
    from utxoproof.kyc import create_sample_graph

    db_path = tmp_path / "app.db"
    source = create_sample_graph()
    dest = sqlite3.connect(str(db_path))
    source.backup(dest)
    dest.close()

    src = tmp_path / "scan.png"
    src.write_bytes(sample_png())
    root = tmp_path / "evidence"
    assert (
        main(
            [
                "attach",
                "--file",
                str(src),
                "--db",
                str(db_path),
                "--tx",
                "C",
                "--note",
                "mail",
                "--year",
                "2023",
                "--evidence-dir",
                str(root),
            ]
        )
        == 0
    )
    assert (root / "2023" / "scan.png").is_file()

    out = tmp_path / "r2023"
    fixture = Path(__file__).parent / "fixtures" / "manual_2023.csv"
    assert (
        main(
            [
                "report",
                "--input",
                str(fixture),
                "--year",
                "2023",
                "--out",
                str(out),
                "--evidence-dir",
                str(root),
            ]
        )
        == 0
    )
    zips = list(out.glob("utxoproof_evidence_2023_*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        assert "attachments/scan.png" in zf.namelist()
