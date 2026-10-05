"""utxoproof.toml configuration (plan Sec. 16 subset, Sprint 7).

Covers [taxpayer], [classifier] and [accounting]; bitcoin/price/output sections
arrive with their sprints. Missing file -> defaults; unknown keys ignored.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass
class TaxpayerConfig:
    reference: str = "BE-LOCAL"
    communal_surcharge_rate: Decimal = Decimal("0.07")


@dataclass
class ClassifierConfig:
    speculator_threshold: int = 8
    passive_threshold: int = 5
    used_leverage: bool = False
    used_derivatives: bool = False
    has_professional_crypto_income: bool = False
    btc_income_fraction: Decimal = Decimal("0")


@dataclass
class AccountingConfig:
    method: str = "moving_average"


@dataclass
class Config:
    taxpayer: TaxpayerConfig = field(default_factory=TaxpayerConfig)
    classifier: ClassifierConfig = field(default_factory=ClassifierConfig)
    accounting: AccountingConfig = field(default_factory=AccountingConfig)


def _decimal(value: object, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return default


def load_config(path: str | Path | None = None) -> Config:
    """Load utxoproof.toml; fall back to defaults when absent."""
    candidates = (
        [Path(path).expanduser()]
        if path
        else [Path("utxoproof.toml"), Path("~/.utxoproof/utxoproof.toml").expanduser()]
    )
    data: dict[str, Any] = {}
    for candidate in candidates:
        if candidate.is_file():
            with open(candidate, "rb") as f:
                loaded = tomllib.load(f)
            if isinstance(loaded, dict):
                data = loaded
            break

    taxpayer = data.get("taxpayer", {})
    classifier = data.get("classifier", {})
    accounting = data.get("accounting", {})
    return Config(
        taxpayer=TaxpayerConfig(
            reference=str(taxpayer.get("reference", "BE-LOCAL")),
            communal_surcharge_rate=_decimal(
                taxpayer.get("communal_surcharge_rate", "0.07"), Decimal("0.07")
            ),
        ),
        classifier=ClassifierConfig(
            speculator_threshold=int(classifier.get("speculator_threshold", 8)),
            passive_threshold=int(classifier.get("passive_threshold", 5)),
            used_leverage=bool(classifier.get("used_leverage", False)),
            used_derivatives=bool(classifier.get("used_derivatives", False)),
            has_professional_crypto_income=bool(
                classifier.get("has_professional_crypto_income", False)
            ),
            btc_income_fraction=_decimal(classifier.get("btc_income_fraction", "0"), Decimal("0")),
        ),
        accounting=AccountingConfig(method=str(accounting.get("method", "moving_average"))),
    )
