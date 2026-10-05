"""Fuzzy fiat-leg matching: bank rows <-> exchange trades (plan Sec. 11).

Match rule (skeleton): calendar-date proximity (+/- ``window_days``) AND exact
absolute EUR amount equality. Weekend/business-day nuance and reference-string
heuristics arrive with the full matcher; unmatched bank rows are returned for
manual review (and shown in the tax report later).
"""

from __future__ import annotations

from utxoproof.banks import BankRow
from utxoproof.exchange import ExchangeTx


def match_fiat_legs(
    exchange_txs: list[ExchangeTx],
    bank_rows: list[BankRow],
    window_days: int = 2,
) -> tuple[list[tuple[ExchangeTx, BankRow]], list[BankRow]]:
    """Greedy one-to-one matching. Returns (matches, unmatched_bank_rows)."""
    matches: list[tuple[ExchangeTx, BankRow]] = []
    used_bank: set[int] = set()
    for tx in exchange_txs:
        if tx.kind not in ("BUY", "SELL"):
            continue
        for i, bank in enumerate(bank_rows):
            if i in used_bank:
                continue
            if abs((bank.date - tx.date).days) > window_days:
                continue
            if abs(bank.amount_eur) != tx.fiat_amount:
                continue
            matches.append((tx, bank))
            used_bank.add(i)
            break
    unmatched = [bank for i, bank in enumerate(bank_rows) if i not in used_bank]
    return matches, unmatched
