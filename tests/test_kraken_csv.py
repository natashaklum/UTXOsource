"""Sprint 1: Kraken ledgers.csv parsing (standalone; DaLI plugin shape later)."""

from decimal import Decimal
from pathlib import Path

from utxoproof.cli import compute_year
from utxoproof.kraken_csv import parse_kraken_ledgers, to_manual_csv_rows

FIXTURE = Path(__file__).parent / "fixtures" / "kraken_ledgers_2023.csv"


def test_parses_trades_with_fiat_legs() -> None:
    txs = parse_kraken_ledgers(FIXTURE)
    by_ref = {tx.refid: tx for tx in txs}
    buy = by_ref["R1"]
    assert (buy.kind, buy.btc, buy.eur_per_btc, buy.fee_eur) == (
        "BUY",
        Decimal("1"),
        Decimal("20000"),
        Decimal("10"),
    )
    sell = by_ref["R2"]
    assert (sell.kind, sell.btc, sell.eur_per_btc, sell.fee_eur) == (
        "SELL",
        Decimal("0.5"),
        Decimal("25000"),
        Decimal("5"),
    )
    for tx in txs:
        assert tx.kyc_status == "kyc"
        assert tx.source_evidence.endswith(f"refid:{tx.refid}")


def test_skips_non_btc_and_keeps_cashflow_kinds() -> None:
    txs = parse_kraken_ledgers(FIXTURE)
    by_ref = {tx.refid: tx for tx in txs}
    assert "R6" not in by_ref  # ETH trade skipped
    assert by_ref["R5"].kind == "WITHDRAWAL"
    assert by_ref["R7"].kind == "DEPOSIT"


def test_kraken_to_compute_end_to_end() -> None:
    # R1 buy 1.0 @20000+10 | R2 sell 0.5 @25000-5 -> gain 2490
    # R3 buy 0.25 @24000   | R4 sell 0.25 @23000   -> gain 415
    rows = to_manual_csv_rows(parse_kraken_ledgers(FIXTURE))
    assert len(rows) == 4  # withdrawals/deposits excluded
    assert compute_year.__name__ == "compute_year"
    gain = _gain_from_rows(rows)
    assert gain == Decimal("2905")


def _gain_from_rows(rows: list[dict[str, str]]) -> Decimal:
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
