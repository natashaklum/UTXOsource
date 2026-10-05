"""Bisq trade-history CSV parser (Sprint 8, non-KYC).

Best-effort column shape (UNVERIFIED against a live export; header aliases
accepted, see _ALIASES): trade id, date, market, direction, price, amount.
Direction is REQUIRED when present-ambiguous: a missing/unknown direction
raises instead of silently misclassifying a buy as a sell.
"""

from __future__ import annotations

import csv
import datetime
from decimal import Decimal
from pathlib import Path

from utxoproof.exchange import ExchangeTx

EXCHANGE = "bisq"
KYC_STATUS = "non_kyc"
SOURCE_TYPE = "p2p_purchase"

_ALIASES = {
    "id": ["Trade ID", "tradeId", "ID", "id", "Trade Id"],
    "date": ["Date", "date", "Creation Date"],
    "market": ["Market", "market", "Pair"],
    "direction": ["Direction", "direction", "Type", "type", "Offer Type", "Trade Type"],
    "price": ["Price", "price"],
    "amount": ["Amount", "amount", "BTC Amount", "Volume"],
}

BUY_VALUES = {"buy", "bid", "taker buy", "maker buy"}
SELL_VALUES = {"sell", "ask", "taker sell", "maker sell"}


def _pick(row: dict[str, str], names: list[str]) -> str:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return str(row[name])
    return ""


def _parse_time(value: str) -> datetime.date:
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(value[:19], fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    raise ValueError(f"Unparseable Bisq timestamp: {value!r}")


def parse_bisq_csv(path: str | Path) -> list[ExchangeTx]:
    """Parse a Bisq trade-history export into BTC records (non-KYC)."""
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
    market = _pick(row, _ALIASES["market"]).upper()
    if "BTC" not in market and "XBT" not in market:
        return None
    direction = _pick(row, _ALIASES["direction"]).strip().lower()
    if direction in BUY_VALUES:
        kind = "BUY"
    elif direction in SELL_VALUES:
        kind = "SELL"
    else:
        raise ValueError(f"Bisq row {index}: unknown direction {direction!r}")
    date = _parse_time(_pick(row, _ALIASES["date"]))
    btc = abs(Decimal(_pick(row, _ALIASES["amount"]) or "0"))
    if btc == 0:
        return None
    price = Decimal(_pick(row, _ALIASES["price"]) or "0")
    refid = _pick(row, _ALIASES["id"]) or f"bisq-{index}"
    return ExchangeTx(
        date,
        kind,
        btc,
        price,
        Decimal("0"),
        refid,
        exchange=EXCHANGE,
        kyc_status=KYC_STATUS,
        source_type=SOURCE_TYPE,
        source_label=f"Bisq {direction} {btc} BTC ({market})",
        source_evidence=f"{filename}:row:{index}",
    )
