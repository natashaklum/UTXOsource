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


def test_user_2017_deposit_shape() -> None:
    from utxoproof.kraken_csv import parse_kraken_ledgers

    txs = parse_kraken_ledgers(Path(__file__).parent / "fixtures" / "kraken_deposit_2017.csv")
    assert len(txs) == 1
    deposit = txs[0]
    assert (deposit.kind, deposit.btc, deposit.wallet, deposit.subclass) == (
        "DEPOSIT",
        Decimal("0.01384720"),
        "spot / main",
        "crypto",
    )
    assert deposit.source_type == "exchange_purchase"


def test_unpriced_deposit_without_source_is_loud() -> None:
    import pytest

    from utxoproof.cli import _deposit_unit_price

    with pytest.raises(ValueError, match="--price-history"):
        _deposit_unit_price("2023-02-01", Decimal("0"), None)


def test_diagnose_names_shortfall_and_cover() -> None:
    from utxoproof.cli import diagnose

    result = diagnose(Path(__file__).parent / "fixtures" / "margin_short.csv")
    assert result["shortfalls"] == 1
    row = result["disposals"][0]
    assert row["shortfall_btc"] == Decimal("0.0612837123")
    assert row["buys_btc"] == Decimal("0") and row["deposits_btc"] == Decimal("0")


def test_deposit_covers_later_disposal(tmp_path: Path) -> None:
    """User story: coins deposited (not bought) fund a later margin close."""
    import csv

    from utxoproof.cli import compute_details, diagnose
    from utxoproof.kraken_csv import parse_kraken_ledgers

    txs = parse_kraken_ledgers(Path(__file__).parent / "fixtures" / "kraken_deposit_2017.csv")
    assert txs[0].kind == "DEPOSIT"
    rows = [
        {
            "date": "2017-10-12",
            "side": "DEPOSIT",
            "kind": "DEPOSIT",
            "btc": "0.01384720",
            "eur_per_btc": "0",
            "fee_eur": "0",
        },
        {
            "date": "2023-03-20",
            "side": "SELL",
            "kind": "MARGIN",
            "btc": "0.01000000",
            "eur_per_btc": "25000",
            "fee_eur": "5",
        },
    ]
    csv_path = tmp_path / "dep.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "side", "kind", "trade_refs", "btc", "eur_per_btc", "fee_eur"]
        )
        writer.writeheader()
        writer.writerows(rows)

    def price_at(_day: object) -> Decimal:
        return Decimal("5000")

    result = compute_details(csv_path, 2023, price_at)
    # cost 0.01*5000=50 of 0.0138472*5000=69.24 pool; proceeds 250-5=245
    assert result["gain_loss_eur"] == Decimal("195")
    diagnosis = diagnose(csv_path, price_at)
    assert diagnosis["shortfalls"] == 0


def test_cli_check_and_price_history_flag(tmp_path: Path, capsys) -> None:
    from utxoproof.cli import main

    fixture = Path(__file__).parent / "fixtures" / "margin_short.csv"
    assert main(["check", "--input", str(fixture)]) == 0
    out = capsys.readouterr().out
    assert "SHORTFALL 0.0612837123" in out and "shortfalls: 1" in out

    prices = tmp_path / "prices.csv"
    prices.write_text("date,close_eur\n2023-02-01,21000\n", encoding="utf-8")
    marvel = tmp_path / "m.csv"
    marvel.write_text(
        "date,side,kind,btc,eur_per_btc,fee_eur\n"
        "2023-02-01,DEPOSIT,DEPOSIT,0.5,0,0\n"
        "2023-03-01,SELL,SELL,0.25,24000,0\n",
        encoding="utf-8",
    )
    # No flag: bundled vendored history covers 2023-02-01 transparently.
    assert main(["compute", "--input", str(marvel), "--year", "2023"]) == 0
    assert (
        main(
            [
                "compute",
                "--input",
                str(marvel),
                "--year",
                "2023",
                "--price-history",
                str(prices),
            ]
        )
        == 0
    )


def test_diagnose_certain_double_count(tmp_path: Path) -> None:
    from utxoproof.cli import diagnose

    csv_path = tmp_path / "dbl.csv"
    csv_path.write_text(
        "date,side,kind,trade_refs,btc,eur_per_btc,fee_eur\n"
        "2023-01-05,BUY,BUY,,2.0,19000,0\n"
        "2023-03-20,SELL,SELL,T9,0.5,25000,0\n"
        "2023-03-20,SELL,MARGIN,T9,0.5,25000,0\n",
        encoding="utf-8",
    )
    result = diagnose(csv_path)
    assert len(result["doubles"]) == 1
    assert result["doubles"][0]["kind"] == "CERTAIN"
    assert result["doubles"][0]["ref"] == "T9"


def test_diagnose_probable_pair_and_order_verdict(tmp_path: Path) -> None:
    from utxoproof.cli import diagnose

    csv_path = tmp_path / "prob.csv"
    csv_path.write_text(
        "date,side,kind,trade_refs,btc,eur_per_btc,fee_eur\n"
        "2023-03-20,SELL,MARGIN,,0.6,25000,0\n"
        "2023-03-20,BUY,BUY,,1.5,20000,0\n"
        "2023-03-20,SELL,SELL,,0.6,25000,0\n",
        encoding="utf-8",
    )
    result = diagnose(csv_path)
    assert result["shortfalls"] == 1  # first 0.6 exceeds empty pool
    assert result["disposals"][0]["verdict"] == "ORDER"  # day nets +0.3 overall
    assert len(result["probable"]) == 1
    assert result["probable"][0]["kind"] == "PROBABLE"


def test_diagnose_structural_verdict(tmp_path: Path) -> None:
    from utxoproof.cli import diagnose

    csv_path = tmp_path / "struct.csv"
    csv_path.write_text(
        "date,side,kind,trade_refs,btc,eur_per_btc,fee_eur\n2023-03-20,SELL,MARGIN,,0.5,25000,0\n",
        encoding="utf-8",
    )
    result = diagnose(csv_path)
    assert result["disposals"][0]["verdict"] == "STRUCTURAL"


def test_diagnose_print_is_dust_free(tmp_path: Path, capsys) -> None:
    from utxoproof.cli import diagnose, print_diagnosis

    csv_path = tmp_path / "dust.csv"
    csv_path.write_text(
        "date,side,kind,trade_refs,btc,eur_per_btc,fee_eur\n"
        "2023-01-05,BUY,BUY,,0.1,20000,0\n"
        "2023-03-20,SELL,SELL,,0.1,25000,0\n",
        encoding="utf-8",
    )
    assert print_diagnosis(diagnose(csv_path)) == 0
    out = capsys.readouterr().out
    assert "0E-10" not in out and "0.1000000000" not in out
