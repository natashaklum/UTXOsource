"""Sprint 1: Kraken ledgers.csv parsing (standalone; DaLI plugin shape later)."""

from decimal import Decimal
from pathlib import Path

from utxoproof.cli import compute_details
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


def test_kraken_to_compute_end_to_end(tmp_path: Path) -> None:
    # R1 buy 1.0 @20000+10 | R2 sell 0.5 @25000-5 -> gain 2490
    # R3 buy 0.25 @24000   | R4 sell 0.25 @23000   -> gain 415
    # R7 deposit 0.05 (valued at receipt via price_at, no sale after)
    import csv

    rows = to_manual_csv_rows(parse_kraken_ledgers(FIXTURE))
    assert len(rows) == 6  # + R5 withdrawal (basis travels, no gain) + R7 deposit
    assert rows[-1]["side"] == "DEPOSIT"
    csv_path = tmp_path / "kraken.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "side", "kind", "trade_refs", "btc", "eur_per_btc", "fee_eur"]
        )
        writer.writeheader()
        writer.writerows(rows)
    result = compute_details(csv_path, 2023, lambda _day: Decimal("30000"))
    assert result["gain_loss_eur"] == Decimal("2905")
