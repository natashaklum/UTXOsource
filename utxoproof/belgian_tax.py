"""Belgian tax computation (WIB/CIR Art. 90 S1 divers inkomen, Art. 37 beroepsinkomen).

This is the utxoproof-side tax helper. It mirrors the ``apply_tax`` sketch from
plan Sec. 5 but lives here (plain ``Decimal``) rather than inside the rp2
country plugin, because rp2's ``AbstractCountry`` API has no ``apply_tax`` hook:
country plugins only declare accounting methods / report generators. The rp2
``BE`` plugin (in the ``natashaklum/rp2`` fork) wires Belgium into rp2's engine;
this module turns rp2's gain/loss output into a Belgian tax figure.
"""

from decimal import Decimal
from typing import TypedDict

DIVERS_INKOMEN_RATE = Decimal("0.33")
COMMUNAL_SURCHARGE_DEFAULT = Decimal("0.07")


class BelgianTaxResult(TypedDict):
    tax_eur: Decimal
    communal_surcharge_eur: Decimal
    total_eur: Decimal


def apply_belgian_tax(
    gain_loss_eur: Decimal,
    classification: str = "goede_huisvader",
    communal_surcharge: Decimal = COMMUNAL_SURCHARGE_DEFAULT,
    marginal_rate_eur: Decimal | None = None,
) -> BelgianTaxResult:
    """Apply Belgian tax to a realised gain.

    - Non-positive gains yield zero tax (divers inkomen losses are recorded
      but not deductible under current SPF Finances guidance).
    - ``goede_huisvader`` (default): 33% flat on the gain.
    - ``speculator``: progressive marginal rate supplied by the classifier
      via ``marginal_rate_eur``; falls back to 33% when absent.
    - Communal surcharge applies on top of the base tax.
    """
    if gain_loss_eur <= Decimal("0"):
        return {
            "tax_eur": Decimal("0"),
            "communal_surcharge_eur": Decimal("0"),
            "total_eur": Decimal("0"),
        }
    if classification == "speculator":
        rate = marginal_rate_eur if marginal_rate_eur is not None else DIVERS_INKOMEN_RATE
    else:
        rate = DIVERS_INKOMEN_RATE

    tax = gain_loss_eur * rate
    communal = tax * communal_surcharge
    return {
        "tax_eur": tax,
        "communal_surcharge_eur": communal,
        "total_eur": tax + communal,
    }


def split_fee_proportionally(
    lot_values_eur: dict[str, Decimal],
    total_fee_eur: Decimal,
) -> dict[str, Decimal]:
    """Split a fee across lots proportionally to lot value.

    Local patch per plan Sec. 4: when the total lot value is zero (or empty),
    fall back to an even split so no lot silently absorbs the whole fee.
    """
    if not lot_values_eur:
        return {}
    total_value = sum(lot_values_eur.values(), Decimal("0"))
    if total_value == Decimal("0"):
        per_lot = total_fee_eur / len(lot_values_eur)
        return dict.fromkeys(lot_values_eur, per_lot)
    return {
        lot_id: (total_fee_eur * value / total_value) for lot_id, value in lot_values_eur.items()
    }
