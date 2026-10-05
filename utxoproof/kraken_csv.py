"""Kraken ledgers.csv parser (plan Sec. 10, Sprint 1).

Standalone parser: reads a Kraken ``ledgers.csv`` export and yields normalized
transactions. Shaped like a DaLI plugin's output (In/Out-style records with KYC
metadata) so it can back a real DaLI plugin later; Sprint 1 consumes it directly
because DaLI is not installable here yet (needs a C toolchain).

Expected columns (Kraken export header):
``txid,refid,time,type,subtype,aclass,asset,amount,fee,balance`` with asset
codes like ``XXBT``/``ZEUR``. A trade is a refid group with an XBT leg and a
fiat leg; deposits/withdrawals are single-leg XBT rows. Non-BTC groups are
skipped.
"""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

KYC_STATUS = "kyc"
SOURCE_TYPE = "exchange_purchase"

BTC_ASSETS = {"XBT", "XXBT", "BTC"}
FIAT_ASSETS = {
    "ZEUR": "EUR",
    "EUR": "EUR",
    "ZUSD": "USD",
    "USD": "USD",
    "ZGBP": "GBP",
    "GBP": "GBP",
    "ZCHF": "CHF",
    "CHF": "CHF",
}


@dataclass
class KrakenTx:
    date: datetime.date
    kind: str  # BUY | SELL | WITHDRAWAL | DEPOSIT
    btc: Decimal
    eur_per_btc: Decimal
    fee_eur: Decimal
    refid: str
    kyc_status: str = KYC_STATUS
    source_type: str = SOURCE_TYPE
    source_label: str = ""
    source_evidence: str = ""


def _parse_time(value: str) -> datetime.date:
    # Kraken exports naive local timestamps; treat as UTC (day-level use only).
    return datetime.datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").date()  # noqa: DTZ007


def parse_kraken_ledgers(path: str | Path) -> list[KrakenTx]:
    """Parse a Kraken ledgers.csv export into normalized BTC transactions."""
    path = Path(path)
    groups: dict[str, list[dict[str, str]]] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            refid = (row.get("refid") or "").strip()
            if refid:
                groups.setdefault(refid, []).append(row)

    result: list[KrakenTx] = []
    for refid, rows in groups.items():
        tx = _parse_group(refid, rows, str(path))
        if tx is not None:
            result.append(tx)
    result.sort(key=lambda tx: (tx.date.isoformat(), tx.refid))
    return result


def _parse_group(refid: str, rows: list[dict[str, str]], filename: str) -> KrakenTx | None:
    btc_rows = [r for r in rows if (r.get("asset") or "").strip() in BTC_ASSETS]
    if not btc_rows:
        return None  # non-BTC group (e.g. ETH trade)
    first = rows[0]
    date = _parse_time(first.get("time", ""))
    evidence = f"{filename}:refid:{refid}"
    entry_type = (first.get("type") or "").strip().lower()

    if entry_type == "trade":
        return _parse_trade(refid, rows, btc_rows, date, evidence)
    if entry_type == "withdrawal":
        btc = abs(Decimal(btc_rows[0].get("amount") or "0"))
        return KrakenTx(
            date,
            "WITHDRAWAL",
            btc,
            Decimal("0"),
            Decimal("0"),
            refid,
            source_label=f"Kraken withdrawal {refid}",
            source_evidence=evidence,
        )
    if entry_type == "deposit":
        btc = abs(Decimal(btc_rows[0].get("amount") or "0"))
        return KrakenTx(
            date,
            "DEPOSIT",
            btc,
            Decimal("0"),
            Decimal("0"),
            refid,
            source_label=f"Kraken deposit {refid}",
            source_evidence=evidence,
        )
    return None


def _parse_trade(
    refid: str,
    rows: list[dict[str, str]],
    btc_rows: list[dict[str, str]],
    date: datetime.date,
    evidence: str,
) -> KrakenTx | None:
    fiat_rows = [r for r in rows if (r.get("asset") or "").strip() in FIAT_ASSETS]
    if not fiat_rows:
        return None
    btc_amount = sum((Decimal(r.get("amount") or "0") for r in btc_rows), Decimal("0"))
    fiat_amount = sum((Decimal(r.get("amount") or "0") for r in fiat_rows), Decimal("0"))
    if btc_amount == 0 or fiat_amount == 0:
        return None
    fiat_ccy = FIAT_ASSETS[fiat_rows[0].get("asset", "").strip()]

    btc = abs(btc_amount)
    kind = "BUY" if btc_amount > 0 else "SELL"
    # Kraken quotes fiat legs in their own currency; Sprint 1 handles EUR legs
    # exactly and converts other currencies at 1:1 only when explicitly paired
    # downstream (full ECB conversion arrives with the fiat-leg matcher).
    fiat_abs = abs(fiat_amount)
    eur_per_btc = fiat_abs / btc

    btc_fee = sum((Decimal(r.get("fee") or "0") for r in btc_rows), Decimal("0"))
    fiat_fee = sum((Decimal(r.get("fee") or "0") for r in fiat_rows), Decimal("0"))
    fee_eur = abs(fiat_fee) + abs(btc_fee) * eur_per_btc

    side = "buy" if kind == "BUY" else "sell"
    label = f"Kraken trade {refid} ({side} {btc} BTC @ {eur_per_btc:.2f} {fiat_ccy})"
    return KrakenTx(
        date, kind, btc, eur_per_btc, fee_eur, refid, source_label=label, source_evidence=evidence
    )


def to_manual_csv_rows(txs: list[KrakenTx]) -> list[dict[str, str]]:
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
