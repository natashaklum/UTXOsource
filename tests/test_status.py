"""Holdings status (Sprint 2 remainder): snapshot at a given price."""

from decimal import Decimal
from pathlib import Path

import pytest

from utxoproof.cli import compute_status, main

FIXTURE = Path(__file__).parent / "fixtures" / "manual_2023.csv"

# Hand-verified by independent recomputation: 0.9 BTC at avg 21720.67.
EXPECTED = {
    "btc": Decimal("0.90000000"),
    "cost_eur": Decimal("19548.60389610389610389610389"),
    "avg_cost_eur": Decimal("21720.67099567099567099567099"),
    "value_eur": Decimal("36000.00000000"),
    "unrealized_eur": Decimal("16451.39610389610389610389611"),
}


def test_compute_status() -> None:
    assert compute_status(FIXTURE, Decimal("40000")) == EXPECTED


def test_status_page_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status", "--input", str(FIXTURE), "--price", "40000"]) == 0
    out = capsys.readouterr().out
    assert "holdings_btc: 0.90000000" in out
    assert "unrealized_eur: 16451.40" in out

    from utxoproof.reports import write_status_page

    target = write_status_page(FIXTURE, Decimal("40000"), "test price", tmp_path)
    html = target.read_text(encoding="utf-8")
    assert "36000.00" in html and "16451.40" in html
