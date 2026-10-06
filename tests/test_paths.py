"""Single data directory: flag > env > ~/.utxoproof (Sprint 12)."""

import argparse
from pathlib import Path

from utxoproof.paths import add_data_dir_arg, data_dir, db_path, evidence_root


def _args(**overrides):
    parser = argparse.ArgumentParser()
    add_data_dir_arg(parser)
    parser.add_argument("--db", default=None)
    parser.add_argument("--evidence-dir", default=None)
    args = parser.parse_args([])
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def test_defaults_point_home(monkeypatch) -> None:
    monkeypatch.delenv("UTXOPROOF_DATA_DIR", raising=False)
    args = _args()
    assert data_dir(args.data_dir) == Path("~/.utxoproof").expanduser()
    assert db_path(args) == Path("~/.utxoproof/utxoproof.db").expanduser()
    assert evidence_root(args) == Path("~/.utxoproof/evidence").expanduser()


def test_env_redirects_everything(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UTXOPROOF_DATA_DIR", str(tmp_path / "mydata"))
    args = _args()
    assert db_path(args) == tmp_path / "mydata" / "utxoproof.db"
    assert evidence_root(args) == tmp_path / "mydata" / "evidence"


def test_explicit_flags_win(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UTXOPROOF_DATA_DIR", str(tmp_path / "envdata"))
    args = _args(db=str(tmp_path / "custom.db"), evidence_dir=str(tmp_path / "ev"))
    assert db_path(args) == tmp_path / "custom.db"
    assert evidence_root(args) == tmp_path / "ev"
    flag_dir = _args()
    flag_dir.data_dir = str(tmp_path / "flagdata")
    assert db_path(flag_dir) == tmp_path / "flagdata" / "utxoproof.db"


def test_attach_lives_entirely_in_data_dir(monkeypatch, tmp_path: Path) -> None:
    import zipfile

    from utxoproof.cli import main

    data = tmp_path / "canon"
    monkeypatch.setenv("UTXOPROOF_DATA_DIR", str(data))
    src = tmp_path / "receipt.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert main(["attach", "--file", str(src), "--year", "2023"]) == 0
    assert (data / "utxoproof.db").is_file()
    assert (data / "evidence" / "2023" / "receipt.png").is_file()

    # The report flow picks the same evidence dir up without extra flags.
    fixture = Path(__file__).parent / "fixtures" / "manual_2023.csv"
    out = tmp_path / "report"
    assert main(["report", "--input", str(fixture), "--year", "2023", "--out", str(out)]) == 0
    zips = list(out.glob("utxoproof_evidence_2023_*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        assert "attachments/receipt.png" in zf.namelist()
