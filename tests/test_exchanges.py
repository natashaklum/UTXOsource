"""Exchange parser tests (Sprint 8; shapes UNVERIFIED vs live exports)."""

from decimal import Decimal
from pathlib import Path

import pytest

from utxoproof.binance_csv import parse_binance_csv
from utxoproof.bisq_csv import parse_bisq_csv
from utxoproof.coinbase_csv import parse_coinbase_csv
from utxoproof.exchange import to_manual_csv_rows

FIXTURES = Path(__file__).parent / "fixtures"


def test_coinbase_trades_and_cashflows() -> None:
    txs = parse_coinbase_csv(FIXTURES / "coinbase_2023.csv")
    by_ref = {tx.refid: tx for tx in txs}
    assert len(txs) == 3  # ETH row skipped
    buy = by_ref["coinbase-0"]
    assert (buy.kind, buy.btc, buy.eur_per_btc, buy.fee_eur) == (
        "BUY",
        Decimal("1"),
        Decimal("20000"),
        Decimal("10"),
    )
    assert by_ref["coinbase-1"].kind == "SELL"
    assert by_ref["coinbase-3"].kind == "WITHDRAWAL"
    assert all(tx.kyc_status == "kyc" and tx.exchange == "coinbase" for tx in txs)


def test_binance_fees_and_skip() -> None:
    txs = parse_binance_csv(FIXTURES / "binance_2023.csv")
    assert len(txs) == 2  # ETH row skipped
    assert txs[0].fee_eur == Decimal("0.0005") * Decimal("22000")  # BTC-denominated
    assert txs[1].fee_eur == Decimal("6")  # EUR-denominated
    assert all(tx.exchange == "binance" for tx in txs)


def test_bisq_is_non_kyc_and_requires_direction(tmp_path: Path) -> None:
    txs = parse_bisq_csv(FIXTURES / "bisq_2023.csv")
    assert [(tx.kind, tx.kyc_status) for tx in txs] == [("BUY", "non_kyc"), ("SELL", "non_kyc")]
    assert txs[0].source_type == "p2p_purchase"

    bad = tmp_path / "bisq_bad.csv"
    bad.write_text("Trade ID,Date,Market,Direction,Price,Amount\nX,2023-01-01,BTC/EUR,,28000,0.1\n")
    with pytest.raises(ValueError, match="direction"):
        parse_bisq_csv(bad)


def test_coinbase_end_to_end_gain(tmp_path: Path) -> None:
    import csv

    from utxoproof.cli import compute_details

    rows = to_manual_csv_rows(parse_coinbase_csv(FIXTURES / "coinbase_2023.csv"))
    assert len(rows) == 3  # buy, sell, withdrawal (cashflow carried, no gain)
    assert rows[-1]["side"] == "WITHDRAWAL"
    csv_path = tmp_path / "coinbase.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "side", "kind", "trade_refs", "btc", "eur_per_btc", "fee_eur"],
        )
        writer.writeheader()
        writer.writerows(rows)
    result = compute_details(csv_path, 2023)
    assert result["gain_loss_eur"] == Decimal("2490")  # 12495 - (20010 / 2)
