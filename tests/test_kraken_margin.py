"""Kraken margin/trades-join tests (Sprint 13)."""

from decimal import Decimal
from pathlib import Path

import pytest

from utxoproof.exchange import to_manual_csv_rows
from utxoproof.kraken_csv import (
    detect_margin_activity,
    parse_kraken_ledgers,
    parse_kraken_trades,
)

FIXTURES = Path(__file__).parent / "fixtures"
MARGIN_LEDGERS = FIXTURES / "kraken_ledgers_margin.csv"
MARGIN_TRADES = FIXTURES / "kraken_trades_2023.csv"


def test_trades_join_marks_margin_and_overrides() -> None:
    trades = parse_kraken_trades(MARGIN_TRADES)
    assert set(trades) == {"T1", "T2"}
    txs = parse_kraken_ledgers(MARGIN_LEDGERS, MARGIN_TRADES)
    by_ref = {tx.refid: tx for tx in txs}
    assert by_ref["M10"].kind == "MARGIN" and by_ref["M10"].margin is True
    assert "[margin]" in by_ref["M10"].source_label
    assert by_ref["M10"].eur_per_btc == Decimal("20000")  # trade price wins
    assert by_ref["M11"].kind == "MARGIN"
    assert by_ref["M09"].kind == "BUY" and by_ref["M09"].margin is False
    assert detect_margin_activity(txs) is True


def test_without_trades_no_margin_flags() -> None:
    txs = parse_kraken_ledgers(MARGIN_LEDGERS)
    assert {tx.kind for tx in txs} == {"BUY", "SELL", "ROLLOVER", "DEPOSIT"}
    assert detect_margin_activity(txs) is False


def test_rollover_settled_staking_kinds() -> None:
    txs = parse_kraken_ledgers(MARGIN_LEDGERS, MARGIN_TRADES)
    by_ref = {tx.refid: tx for tx in txs}
    rollover = by_ref["M12"]
    assert (rollover.kind, rollover.btc, rollover.fee_eur) == (
        "ROLLOVER",
        Decimal("0"),
        Decimal("2.50"),
    )
    assert "M13" not in by_ref  # settled: ignorable by design
    assert by_ref["M14"].kind == "DEPOSIT"


def test_unknown_ledger_type_is_loud() -> None:
    with pytest.raises(ValueError, match="X99"):
        parse_kraken_ledgers(FIXTURES / "kraken_ledgers_bad.csv")


def test_margin_gain_and_kinds_in_manual_rows() -> None:
    txs = parse_kraken_ledgers(MARGIN_LEDGERS, MARGIN_TRADES)
    rows = to_manual_csv_rows(txs)
    assert [(r["side"], r["kind"]) for r in rows] == [
        ("BUY", "BUY"),
        ("SELL", "MARGIN"),
        ("SELL", "MARGIN"),
        ("BUY", "ROLLOVER"),
    ]
    assert _gain(rows) == Decimal("3981.25")


def _gain(rows: list[dict[str, str]]) -> Decimal:
    total_btc = Decimal("0")
    total_cost = Decimal("0")
    realised = Decimal("0")
    for row in rows:
        btc = Decimal(row["btc"])
        price = Decimal(row["eur_per_btc"])
        fee = Decimal(row["fee_eur"])
        if row["side"] == "BUY":
            total_btc += btc
            total_cost += btc * price + fee
        else:
            avg = total_cost / total_btc
            realised += (btc * price - fee) - avg * btc
            total_btc -= btc
            total_cost -= avg * btc
    return realised
