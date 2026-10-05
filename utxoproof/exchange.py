"""Shared exchange-trade record (Sprint 8).

All exchange CSV parsers yield ``ExchangeTx`` (DaLI-plugin-shaped for later);
``to_manual_csv_rows`` feeds ``compute``. Amounts are exact Decimals; non-EUR
fiat legs are recorded but converted 1:1 only for EUR (ECB conversion pending).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ExchangeTx:
    date: datetime.date
    kind: str  # BUY | SELL | WITHDRAWAL | DEPOSIT
    btc: Decimal
    eur_per_btc: Decimal
    fee_eur: Decimal
    refid: str
    exchange: str = ""
    kyc_status: str = "kyc"
    source_type: str = "exchange_purchase"
    source_label: str = ""
    source_evidence: str = ""

    @property
    def fiat_amount(self) -> Decimal:
        """Absolute fiat leg implied by price (fees excluded)."""
        return abs(self.btc * self.eur_per_btc)


def to_manual_csv_rows(txs: list[ExchangeTx]) -> list[dict[str, str]]:
    """Convert BUY/SELL records to manual-CSV rows consumable by ``compute``."""
    rows = []
    for tx in txs:
        if tx.kind not in ("BUY", "SELL"):
            continue
        rows.append(
            {
                "date": tx.date.isoformat(),
                "side": tx.kind,
                "btc": str(tx.btc),
                "eur_per_btc": str(tx.eur_per_btc),
                "fee_eur": str(tx.fee_eur),
            }
        )
    return rows
