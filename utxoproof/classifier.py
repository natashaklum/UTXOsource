"""Belgian tax classification (plan Sec. 6, Sprint 7).

Heuristic aid only: goede huisvader (Art. 90 S1) vs speculator (Art. 37) vs
passive holder, from observable signals plus self-reported config flags. The
final classification always rests with SPF Finances.
"""

from __future__ import annotations

import csv
import datetime
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from utxoproof.config import ClassifierConfig


@dataclass
class BelgianClassificationSignals:
    # Trading behaviour
    disposal_count: int
    acquisition_count: int
    avg_holding_days: Decimal
    min_holding_days: int
    max_position_size_eur: Decimal
    btc_proceeds_eur: Decimal
    btc_cost_basis_eur: Decimal
    # Leverage / derivatives (self-reported; chain data cannot show these)
    used_leverage: bool
    used_derivatives: bool
    # Income context
    btc_income_as_pct_total_income: Decimal
    has_professional_crypto_income: bool
    # Behavioural patterns
    exchange_count: int
    uses_dca: bool
    uses_tax_loss_harvesting: bool
    # History
    consecutive_active_years: int


class BelgianTaxClass(Enum):
    GOEDE_HUISVADER = "goede_huisvader"
    SPECULATOR = "speculator"
    PASSIVE_HOLDER = "passive_holder"


class BelgianClassifier:
    """Score-based classifier with configurable thresholds."""

    def __init__(self, speculator_threshold: int = 8, passive_threshold: int = 5) -> None:
        self.speculator_threshold = speculator_threshold
        self.passive_threshold = passive_threshold

    def classify(self, signals: BelgianClassificationSignals) -> tuple[BelgianTaxClass, str]:
        rationale: list[str] = []
        speculator_score = 0
        passive_score = 0

        if signals.disposal_count > 20:
            speculator_score += 3
            rationale.append(f"High disposal count ({signals.disposal_count}).")
        if signals.avg_holding_days < 30:
            speculator_score += 3
            rationale.append(f"Short average holding period ({signals.avg_holding_days:.0f} days).")
        if signals.min_holding_days < 7:
            speculator_score += 2
            rationale.append("Some lots held fewer than 7 days.")
        if signals.used_leverage:
            speculator_score += 4
            rationale.append("Use of leverage.")
        if signals.used_derivatives:
            speculator_score += 4
            rationale.append("Use of derivatives.")
        if signals.btc_income_as_pct_total_income > Decimal("0.50"):
            speculator_score += 3
            rationale.append(
                "BTC gains are "
                f"{signals.btc_income_as_pct_total_income * 100:.0f}% "
                "of total declared income."
            )
        if signals.consecutive_active_years >= 3:
            speculator_score += 2
            rationale.append(f"{signals.consecutive_active_years} consecutive active years.")
        if signals.uses_tax_loss_harvesting:
            speculator_score += 2
            rationale.append("Systematic tax-loss harvesting pattern.")

        if signals.disposal_count == 0:
            passive_score += 5
            rationale.append("No disposals in tax year.")
        if signals.avg_holding_days > 365 and signals.disposal_count <= 3:
            passive_score += 3
            rationale.append("Long holding period, very few disposals.")
        if signals.uses_dca and not signals.used_leverage:
            passive_score += 2
            rationale.append("Dollar-cost averaging without leverage.")

        if speculator_score >= self.speculator_threshold:
            cls = BelgianTaxClass.SPECULATOR
        elif passive_score >= self.passive_threshold and speculator_score == 0:
            cls = BelgianTaxClass.PASSIVE_HOLDER
        else:
            cls = BelgianTaxClass.GOEDE_HUISVADER

        rationale_text = (
            f"Classification: {cls.value}\n"
            f"Speculator score: {speculator_score} | Passive score: {passive_score}\n"
            + "\n".join(f"  - {r}" for r in rationale)
            + "\n\nThis is a heuristic aid. Consult a Belgian tax adviser before filing."
        )
        return cls, rationale_text


@dataclass
class _FifoLot:
    remaining_btc: Decimal
    date: datetime.date


def signals_from_csv(
    csv_path: str | Path,
    year: int,
    classifier: ClassifierConfig | None = None,
    price_at: Callable[[datetime.date], Decimal] | None = None,
) -> BelgianClassificationSignals:
    """Derive classification signals from a manual CSV for ``year``.

    Chain-observable signals are computed (FIFO lot ages for holdings, yearly
    counts/proceeds, DCA and loss-harvesting heuristics); self-reported flags
    come from config. Approximations are documented, not hidden.
    """
    cfg = classifier or ClassifierConfig()
    disposals = 0
    acquisitions = 0
    proceeds = Decimal("0")
    cost_basis = Decimal("0")
    lots: list[_FifoLot] = []
    holding_days: list[int] = []
    buy_dates: list[datetime.date] = []
    december_loss_sale = False
    inventory_value_peak = Decimal("0")
    running_btc = Decimal("0")
    running_cost = Decimal("0")
    active_years: set[int] = set()

    with open(Path(csv_path), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            day = datetime.date.fromisoformat(str(row["date"])[:10])
            active_years.add(day.year)
            side = str(row["side"]).strip().upper()
            btc = Decimal(str(row["btc"]))
            price = Decimal(str(row["eur_per_btc"]))
            fee = Decimal(str(row.get("fee_eur") or "0"))
            if side == "BUY":
                running_btc += btc
                running_cost += btc * price + fee
                lots.append(_FifoLot(btc, day))
                if day.year == year:
                    acquisitions += 1
                    buy_dates.append(day)
            elif side == "DEPOSIT":
                from utxoproof.cli import _deposit_unit_price

                unit = _deposit_unit_price(str(row["date"]), price, price_at)
                running_btc += btc
                running_cost += btc * unit + fee
                lots.append(_FifoLot(btc, day))
            elif side == "WITHDRAWAL":
                from utxoproof.cli import _apply_withdrawal

                running_btc, running_cost = _apply_withdrawal(running_btc, running_cost, btc, row)
                need = btc
                while need > 0 and lots:
                    take = min(lots[0].remaining_btc, need)
                    lots[0].remaining_btc -= take
                    if lots[0].remaining_btc <= 0:
                        lots.pop(0)
                    need -= take
                avg = running_cost / running_btc if running_btc else Decimal("0")
                running_btc -= btc
                running_cost -= avg * btc
            elif side == "SELL":
                need = btc
                while need > 0 and lots:
                    take = min(lots[0].remaining_btc, need)
                    if day.year == year:
                        holding_days.append((day - lots[0].date).days)
                    lots[0].remaining_btc -= take
                    if lots[0].remaining_btc <= 0:
                        lots.pop(0)
                    need -= take
                avg = running_cost / running_btc if running_btc else Decimal("0")
                basis = avg * btc
                gain = (btc * price - fee) - basis
                running_btc -= btc
                running_cost -= basis
                if day.year == year:
                    disposals += 1
                    proceeds += btc * price - fee
                    cost_basis += basis
                    if gain < 0 and day.month == 12:
                        december_loss_sale = True
            inventory_value = running_btc * price
            if inventory_value > inventory_value_peak:
                inventory_value_peak = inventory_value

    avg_holding = (
        sum((Decimal(d) for d in holding_days), Decimal("0")) / len(holding_days)
        if holding_days
        else Decimal("0")
    )
    distinct_buy_days = {d.isoformat() for d in buy_dates}
    uses_dca = len(distinct_buy_days) >= 3 and (max(buy_dates) - min(buy_dates)).days >= 90
    return BelgianClassificationSignals(
        disposal_count=disposals,
        acquisition_count=acquisitions,
        avg_holding_days=avg_holding,
        min_holding_days=min(holding_days) if holding_days else 0,
        max_position_size_eur=inventory_value_peak,
        btc_proceeds_eur=proceeds,
        btc_cost_basis_eur=cost_basis,
        used_leverage=cfg.used_leverage,
        used_derivatives=cfg.used_derivatives,
        btc_income_as_pct_total_income=cfg.btc_income_fraction,
        has_professional_crypto_income=cfg.has_professional_crypto_income,
        exchange_count=1,  # single-CSV skeleton; multi-source counting arrives later
        uses_dca=uses_dca,
        uses_tax_loss_harvesting=december_loss_sale,
        consecutive_active_years=len(active_years),  # proxy: distinct active years
    )
