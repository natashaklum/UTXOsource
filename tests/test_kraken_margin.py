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


USER_LEDGERS = FIXTURES / "kraken_ledgers_user_margin.csv"
USER_TRADES = FIXTURES / "kraken_trades_user.csv"


def test_user_margin_fee_only_row() -> None:
    txs = parse_kraken_ledgers(USER_LEDGERS, USER_TRADES)
    by_ref = {tx.refid: tx for tx in txs}
    fee_only = by_ref["U01"]
    assert (fee_only.kind, fee_only.btc, fee_only.fee_eur) == (
        "MARGIN",
        Decimal("0"),
        Decimal("1.1234"),
    )
    assert fee_only.wallet == "spot / main" and fee_only.subclass == "fiat"


def test_user_margin_btc_disposal_priced_by_linked_trade() -> None:
    txs = parse_kraken_ledgers(USER_LEDGERS, USER_TRADES)
    disposal = {tx.refid: tx for tx in txs}["U03"]
    assert (disposal.kind, disposal.btc, disposal.eur_per_btc, disposal.margin) == (
        "MARGIN",
        Decimal("0.05218971"),
        Decimal("100000"),
        True,
    )
    assert disposal.fee_eur == Decimal("28.34")
    assert detect_margin_activity(txs) is True


def test_user_eth_margin_skipped_with_reason() -> None:
    skipped: list[tuple[str, str]] = []
    txs = parse_kraken_ledgers(USER_LEDGERS, USER_TRADES, skipped=skipped)
    assert "U02" not in {tx.refid for tx in txs}
    assert ("U02", "margin: non-BTC leg, out of scope") in skipped


def test_unpriced_margin_disposal_names_remedy(tmp_path: Path) -> None:
    lonely = tmp_path / "lonely.csv"
    lonely.write_text(
        "txid,refid,time,type,subtype,aclass,subclass,asset,wallet,amount,fee,balance\n"
        "L1,Q1,2025-01-01 00:00:00,margin,,currency,crypto,XXBT,spot / main,-0.5,0.0,0.5\n"
    )
    with pytest.raises(ValueError, match=r"Q1.*--trades"):
        parse_kraken_ledgers(lonely)
