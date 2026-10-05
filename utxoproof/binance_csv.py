"""Binance spot trade-history CSV parser (Sprint 8).

Best-effort column shape (UNVERIFIED against a live export):
``Date(UTC),Market,Type,Price,Amount,Total,Fee,Fee Coin`` with markets like
``BTCEUR``. EUR-quoted rows are exact; other quote currencies are recorded
with their quote and converted 1:1 only for EUR (ECB conversion pending).
"""

from __future__ import annotations

import csv
import datetime
from decimal import Decimal
from pathlib import Path

from utxoproof.exchange import ExchangeTx

EXCHANGE = "binance"

BTC_BASES = {"BTC", "XBT"}


def _parse_time(value: str) -> datetime.date:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value[:19], fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    raise ValueError(f"Unparseable Binance timestamp: {value!r}")


def _split_market(market: str) -> tuple[str, str]:
    market = market.strip().upper()
    for quote in ("EUR", "USD", "USDT", "GBP"):
        if market.endswith(quote) and len(market) > len(quote):
            return market[: -len(quote)], quote
    return market, ""


def parse_binance_csv(path: str | Path) -> list[ExchangeTx]:
    """Parse a Binance trade-history export into BTC records."""
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
    base, quote = _split_market(row.get("Market", "") or row.get("market", ""))
    if base not in BTC_BASES:
        return None
    kind_raw = (row.get("Type", "") or row.get("type", "")).strip().upper()
    if kind_raw not in ("BUY", "SELL"):
        return None
    date = _parse_time(row.get("Date(UTC)", "") or row.get("date", ""))
    btc = abs(Decimal(row.get("Amount", "") or row.get("amount", "") or "0"))
    if btc == 0:
        return None
    price = Decimal(row.get("Price", "") or row.get("price", "") or "0")
    fee = abs(Decimal(row.get("Fee", "") or row.get("fee", "") or "0"))
    fee_coin = (row.get("Fee Coin", "") or row.get("fee_coin", "")).strip().upper()
    if fee_coin in BTC_BASES:
        fee_eur = fee * price
    else:
        fee_eur = fee if quote == "EUR" else Decimal("0")
    refid = f"binance-{index}"
    return ExchangeTx(
        date,
        kind_raw,
        btc,
        price,
        fee_eur,
        refid,
        exchange=EXCHANGE,
        source_label=f"Binance {kind_raw} {btc} BTC/{quote or '?'}",
        source_evidence=f"{filename}:row:{index}",
    )
