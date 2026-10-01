"""Sprint 0: Belgian tax math (33% flat + communal surcharge)."""

from decimal import Decimal

from utxoproof.belgian_tax import (
    COMMUNAL_SURCHARGE_DEFAULT,
    apply_belgian_tax,
    split_fee_proportionally,
)


def test_goede_huisvader_flat_33_plus_surcharge() -> None:
    result = apply_belgian_tax(Decimal("1000"))
    assert result["tax_eur"] == Decimal("330")
    assert result["communal_surcharge_eur"] == Decimal("330") * COMMUNAL_SURCHARGE_DEFAULT
    assert result["total_eur"] == result["tax_eur"] + result["communal_surcharge_eur"]


def test_loss_yields_zero_tax() -> None:
    for gain in (Decimal("-100"), Decimal("0")):
        result = apply_belgian_tax(gain)
        assert result == {
            "tax_eur": Decimal("0"),
            "communal_surcharge_eur": Decimal("0"),
            "total_eur": Decimal("0"),
        }


def test_speculator_uses_marginal_rate() -> None:
    result = apply_belgian_tax(Decimal("1000"), "speculator", Decimal("0.07"), Decimal("0.50"))
    assert result["tax_eur"] == Decimal("500")
    assert result["total_eur"] == Decimal("500") * Decimal("1.07")


def test_speculator_falls_back_to_flat_without_rate() -> None:
    result = apply_belgian_tax(Decimal("1000"), "speculator")
    assert result["tax_eur"] == Decimal("330")


def test_fee_split_proportional() -> None:
    lots = {"a": Decimal("100"), "b": Decimal("300")}
    split = split_fee_proportionally(lots, Decimal("40"))
    assert split == {"a": Decimal("10"), "b": Decimal("30")}
    assert sum(split.values()) == Decimal("40")


def test_fee_split_zero_value_falls_back_even() -> None:
    lots = {"a": Decimal("0"), "b": Decimal("0")}
    assert split_fee_proportionally(lots, Decimal("10")) == {
        "a": Decimal("5"),
        "b": Decimal("5"),
    }


def test_fee_split_empty() -> None:
    assert split_fee_proportionally({}, Decimal("10")) == {}
