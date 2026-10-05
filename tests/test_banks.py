"""Bank parser + fiat-leg matching tests (Sprint 8)."""

from decimal import Decimal
from pathlib import Path

import pytest

from utxoproof.banks import BANK_PROFILES, parse_amount, parse_bank_csv
from utxoproof.kraken_csv import parse_kraken_ledgers
from utxoproof.matching import match_fiat_legs

FIXTURES = Path(__file__).parent / "fixtures"


def test_all_bank_profiles_parse() -> None:
    expected = {
        "ing": (Decimal("20000"), "BE68539007547034"),
        "kbc": (Decimal("11000"), "BE12345678901234"),
        "bnp": (Decimal("2800"), "BE99999999999999"),
        "belfius": (Decimal("-85.40"), None),
        "argenta": (Decimal("-120.50"), None),
    }
    assert set(BANK_PROFILES) == {"ing", "kbc", "bnp", "belfius", "argenta"}
    for bank, (amount, iban) in expected.items():
        rows = parse_bank_csv(FIXTURES / f"{bank}_2023.csv", bank)
        assert len(rows) >= 1
        assert rows[0].amount_eur == amount
        assert rows[0].counterparty_iban == iban
        assert rows[0].source_file.endswith(f"{bank}_2023.csv")


def test_parse_amount_formats() -> None:
    assert parse_amount("1.234,56", ",") == Decimal("1234.56")
    assert parse_amount("1234.56", ".") == Decimal("1234.56")
    assert parse_amount("", ",") == Decimal("0")


def test_unknown_bank_raises() -> None:
    with pytest.raises(ValueError, match="Unknown bank"):
        parse_bank_csv(FIXTURES / "ing_2023.csv", "revolut")


def test_fiat_leg_matching() -> None:
    txs = parse_kraken_ledgers(FIXTURES / "kraken_ledgers_2023.csv")
    bank_rows = parse_bank_csv(FIXTURES / "ing_matching.csv", "ing")
    matches, unmatched = match_fiat_legs(txs, bank_rows)
    assert len(matches) == 2
    assert matches[0][0].refid == "R1"  # same-day exact amount
    assert matches[1][0].refid == "R2"  # 1 day off, exact amount
    assert len(unmatched) == 1
    assert unmatched[0].reference == "NOMATCH"
