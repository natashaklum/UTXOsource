"""Coinbase retail transaction-history CSV parser (Sprint 8).

Best-effort column shape (UNVERIFIED against a live export; designed for easy
correction — see _ALIASES):
``Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,
Spot Price at Transaction,Subtotal,Total (inclusive of fees),Fees,Notes``.
Buy/Sell rows for BTC become trades; Send/Receive become cashflow records;
everything else (rewards, conversions involving no BTC) is skipped.
"""

from __future__ import annotations

import csv
import datetime
from decimal import Decimal
from pathlib import Path

from utxoproof.exchange import ExchangeTx

EXCHANGE = "coinbase"

_ALIASES = {
    "time": ["Timestamp", "timestamp", "Time", "Date"],
    "type": ["Transaction Type", "Type", "type"],
    "asset": ["Asset", "asset", "Currency"],
    "quantity": ["Quantity Transacted", "Quantity", "Amount", "quantity"],
    "currency": ["Spot Price Currency", "Currency"],
    "price": ["Spot Price at Transaction", "Price", "Spot Price"],
    "fees": ["Fees", "Fees and/or Spread", "Fee", "fees"],
    "notes": ["Notes", "notes", "Details"],
}

BTC_ASSETS = {"BTC", "XBT"}
BUY_TYPES = {"buy"}
SELL_TYPES = {"sell"}
WITHDRAWAL_TYPES = {"send"}
DEPOSIT_TYPES = {"receive"}


def _pick(row: dict[str, str], names: list[str]) -> str:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return str(row[name])
    return ""


def _parse_time(value: str) -> datetime.date:
    value = value.strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value[:19], fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    raise ValueError(f"Unparseable Coinbase timestamp: {value!r}")


def parse_coinbase_csv(path: str | Path) -> list[ExchangeTx]:
    """Parse a Coinbase transaction-history export into BTC records."""
    path = Path(path)
    txs: list[ExchangeTx] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for index, row in enumerate(csv.DictReader(f)):
            tx = _parse_row(index, row, str(path))
            if tx is not None:
                txs.append(tx)
    txs.sort(key=lambda tx: (tx.date.isoformat(), tx.refid))
    return txs


def _parse_row(index: int, row: dict[str, str], filename: str) -> ExchangeTx | None:
    if _pick(row, _ALIASES["asset"]).strip().upper() not in BTC_ASSETS:
        return None
    kind_raw = _pick(row, _ALIASES["type"]).strip().lower()
    if kind_raw in BUY_TYPES:
        kind = "BUY"
    elif kind_raw in SELL_TYPES:
        kind = "SELL"
    elif kind_raw in WITHDRAWAL_TYPES:
        kind = "WITHDRAWAL"
    elif kind_raw in DEPOSIT_TYPES:
        kind = "DEPOSIT"
    else:
        return None
    date = _parse_time(_pick(row, _ALIASES["time"]))
    btc = abs(Decimal(_pick(row, _ALIASES["quantity"]) or "0"))
    if btc == 0:
        return None
    price = Decimal(_pick(row, _ALIASES["price"]) or "0")
    fee = abs(Decimal(_pick(row, _ALIASES["fees"]) or "0"))
    refid = f"coinbase-{index}"
    return ExchangeTx(
        date,
        kind,
        btc,
        price,
        fee,
        refid,
        exchange=EXCHANGE,
        source_label=f"Coinbase {kind_raw} {btc} BTC",
        source_evidence=f"{filename}:row:{index}",
    )
