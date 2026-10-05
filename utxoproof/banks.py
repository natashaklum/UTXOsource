"""Belgian bank statement parsers (plan Sec. 11, Sprint 8).

One engine, per-bank profiles. ALL headers below are best-effort
(UNVERIFIED against live exports): columns are matched by alias lists so a
renamed header only needs an alias entry, not a code change. All banks use
`;` delimiters; files open as UTF-8-SIG so a BOM is harmless.
"""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass
class BankRow:
    date: datetime.date
    description: str
    amount_eur: Decimal
    counterparty_iban: str | None
    reference: str | None
    source_file: str = ""


@dataclass
class BankProfile:
    date_cols: tuple[str, ...]
    date_fmt: str
    amount_cols: tuple[str, ...]
    decimal_sep: str  # "," (Belgian) or "." (plain)
    description_cols: tuple[str, ...]
    iban_cols: tuple[str, ...]
    reference_cols: tuple[str, ...]


BANK_PROFILES: dict[str, BankProfile] = {
    # UNVERIFIED headers; alias lists absorb renames.
    "ing": BankProfile(
        date_cols=("Datum", "Date", "Boekdatum"),
        date_fmt="%d/%m/%Y",
        amount_cols=("Bedrag", "Amount"),
        decimal_sep=",",
        description_cols=("Omschrijving", "Description", "Mededeling"),
        iban_cols=("Rekening tegenpartij", "Tegenrekening", "Counterparty"),
        reference_cols=("Referentie", "Reference", "Gestructureerde mededeling"),
    ),
    "kbc": BankProfile(
        date_cols=("Datum", "Date"),
        date_fmt="%d/%m/%Y",
        amount_cols=("Bedrag", "Amount"),
        decimal_sep=",",
        description_cols=("Omschrijving", "Description"),
        iban_cols=("Tegenpartijrekening", "Tegenrekening", "Counterparty"),
        reference_cols=("Referentie", "Reference", "Mededeling"),
    ),
    "bnp": BankProfile(
        date_cols=("Datum", "Date", "Transaction date"),
        date_fmt="%d/%m/%Y",
        amount_cols=("Bedrag", "Amount", "Montant"),
        decimal_sep=",",
        description_cols=("Omschrijving", "Description", "Libellé"),
        iban_cols=("Tegenpartij", "Contrepartie", "Counterparty"),
        reference_cols=("Referentie", "Référence", "Communication"),
    ),
    "belfius": BankProfile(
        date_cols=("Datum", "Date"),
        date_fmt="%d/%m/%Y",
        amount_cols=("Bedrag", "Amount"),
        decimal_sep=",",
        description_cols=("Omschrijving", "Description"),
        iban_cols=("Tegenrekening", "Counterparty"),
        reference_cols=("Mededeling", "Reference"),
    ),
    "argenta": BankProfile(
        date_cols=("Datum", "Date"),
        date_fmt="%d/%m/%Y",
        amount_cols=("Bedrag", "Amount"),
        decimal_sep=",",
        description_cols=("Omschrijving", "Description"),
        iban_cols=("Tegenrekening", "Counterparty"),
        reference_cols=("Mededeling", "Reference"),
    ),
}


def _pick(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return str(row[name]).strip()
    return ""


def parse_amount(raw: str, decimal_sep: str) -> Decimal:
    """Parse Belgian `1.234,56` or plain `1234.56` amounts."""
    text = raw.strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return Decimal("0")
    if decimal_sep == ",":
        text = text.replace(".", "").replace(",", ".")
    return Decimal(text)


def parse_bank_csv(path: str | Path, bank: str) -> list[BankRow]:
    """Parse one bank statement file with the bank's profile."""
    if bank not in BANK_PROFILES:
        raise ValueError(f"Unknown bank {bank!r}; expected one of {sorted(BANK_PROFILES)}")
    profile = BANK_PROFILES[bank]
    path = Path(path)
    rows: list[BankRow] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            date_raw = _pick(row, profile.date_cols)
            if not date_raw:
                continue
            rows.append(
                BankRow(
                    date=datetime.datetime.strptime(date_raw[:10], profile.date_fmt).date(),  # noqa: DTZ007
                    description=_pick(row, profile.description_cols),
                    amount_eur=parse_amount(_pick(row, profile.amount_cols), profile.decimal_sep),
                    counterparty_iban=_pick(row, profile.iban_cols) or None,
                    reference=_pick(row, profile.reference_cols) or None,
                    source_file=str(path),
                )
            )
    rows.sort(key=lambda r: r.date.isoformat())
    return rows
