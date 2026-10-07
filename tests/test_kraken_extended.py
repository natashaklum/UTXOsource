"""Extended Kraken shapes: 12-col header, margin split, spend/receive, etc."""

from decimal import Decimal
from pathlib import Path

from utxoproof.kraken_csv import parse_kraken_ledgers

FIXTURES = Path(__file__).parent / "fixtures"
LEDGERS = FIXTURES / "kraken_ledgers_extended.csv"
TRADES = FIXTURES / "kraken_trades_extended.csv"


def test_new_columns_captured() -> None:
    txs = parse_kraken_ledgers(LEDGERS, TRADES)
    by_ref = {tx.refid: tx for tx in txs}
    assert by_ref["E01"].wallet == "spot / main"
    assert by_ref["E01"].subclass == "fiat"


def test_margin_fee_only_is_cost_not_disposal() -> None:
    txs = parse_kraken_ledgers(LEDGERS, TRADES)
    by_ref = {tx.refid: tx for tx in txs}
    fee_only = by_ref["E01"]
    assert (fee_only.kind, fee_only.btc, fee_only.fee_eur, fee_only.margin) == (
        "MARGIN",
        Decimal("0"),
        Decimal("1.50"),
        True,
    )


def test_margin_pnl_uses_trade_price() -> None:
    txs = parse_kraken_ledgers(LEDGERS, TRADES)
    pnl = {tx.refid: tx for tx in txs}["E02"]
    assert (pnl.kind, pnl.btc, pnl.eur_per_btc, pnl.margin) == (
        "MARGIN",
        Decimal("0.1"),
        Decimal("24000"),
        True,
    )


def test_non_btc_margin_skipped_with_reason() -> None:
    skipped: list[tuple[str, str]] = []
    txs = parse_kraken_ledgers(LEDGERS, TRADES, skipped=skipped)
    assert "E03" not in {tx.refid for tx in txs}
    assert ("E03", "margin: non-BTC leg, out of scope") in skipped


def test_spend_receive_pair_and_lone_legs() -> None:
    txs = parse_kraken_ledgers(LEDGERS, TRADES)
    by_ref = {tx.refid: tx for tx in txs}
    instant = by_ref["E04"]
    assert (instant.kind, instant.btc, instant.eur_per_btc) == (
        "BUY",
        Decimal("0.2"),
        Decimal("25000"),
    )
    assert by_ref["E05"].kind == "WITHDRAWAL"


def test_earn_reward_income_vs_internal_moves() -> None:
    skipped: list[tuple[str, str]] = []
    txs = parse_kraken_ledgers(LEDGERS, TRADES, skipped=skipped)
    by_ref = {tx.refid: tx for tx in txs}
    assert by_ref["E06"].kind == "DEPOSIT"
    assert "E07" not in by_ref  # spottostaking allocation: internal
    assert by_ref["E08"].kind == "DEPOSIT"  # invite bonus
    assert "E09" not in by_ref  # transfer/spottostaking: internal
    reasons = dict(skipped)
    assert "internal" in reasons["E07"] and "internal" in reasons["E09"]


def test_adjustment_priced_by_fiat_leg() -> None:
    txs = parse_kraken_ledgers(LEDGERS, TRADES)
    adj = {tx.refid: tx for tx in txs}["E10"]
    assert (adj.kind, adj.btc, adj.eur_per_btc) == ("ADJUSTMENT", Decimal("0.2"), Decimal("24000"))


def test_extended_manual_rows() -> None:
    from utxoproof.exchange import to_manual_csv_rows

    rows = to_manual_csv_rows(parse_kraken_ledgers(LEDGERS, TRADES))
    kinds = [(r["side"], r["kind"]) for r in rows]
    assert ("SELL", "MARGIN") in kinds
    assert ("BUY", "ROLLOVER") not in kinds  # no rollover in this fixture
    assert ("BUY", "BUY") in kinds  # instant buy
    assert ("SELL", "ADJUSTMENT") in kinds
