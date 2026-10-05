"""Classifier + config tests (Sec. 6 rules, Sec. 16 subset)."""

from decimal import Decimal
from pathlib import Path

from utxoproof.classifier import (
    BelgianClassificationSignals,
    BelgianClassifier,
    BelgianTaxClass,
    signals_from_csv,
)
from utxoproof.config import load_config

FIXTURE = Path(__file__).parent / "fixtures" / "manual_2023.csv"


def _signals(**overrides) -> BelgianClassificationSignals:
    base = {
        "disposal_count": 2,
        "acquisition_count": 3,
        "avg_holding_days": Decimal("200"),
        "min_holding_days": 60,
        "max_position_size_eur": Decimal("50000"),
        "btc_proceeds_eur": Decimal("10000"),
        "btc_cost_basis_eur": Decimal("8000"),
        "used_leverage": False,
        "used_derivatives": False,
        "btc_income_as_pct_total_income": Decimal("0.1"),
        "has_professional_crypto_income": False,
        "exchange_count": 1,
        "uses_dca": True,
        "uses_tax_loss_harvesting": False,
        "consecutive_active_years": 1,
    }
    base.update(overrides)
    return BelgianClassificationSignals(**base)  # type: ignore[arg-type]


def test_speculator_high_frequency_leverage() -> None:
    cls, rationale = BelgianClassifier().classify(
        _signals(
            disposal_count=25,
            avg_holding_days=Decimal("10"),
            min_holding_days=3,
            used_leverage=True,
        )
    )
    assert cls == BelgianTaxClass.SPECULATOR
    assert "leverage" in rationale and "25" in rationale


def test_passive_holder() -> None:
    cls, rationale = BelgianClassifier().classify(
        _signals(disposal_count=0, avg_holding_days=Decimal("500"))
    )
    assert cls == BelgianTaxClass.PASSIVE_HOLDER
    assert "No disposals" in rationale


def test_default_is_goede_huisvader() -> None:
    cls, _ = BelgianClassifier().classify(_signals())
    assert cls == BelgianTaxClass.GOEDE_HUISVADER


def test_custom_thresholds() -> None:
    classifier = BelgianClassifier(speculator_threshold=20)
    cls, _ = classifier.classify(_signals(disposal_count=25))
    assert cls == BelgianTaxClass.GOEDE_HUISVADER  # 3 points < 20


def test_fixture_signals_classify_goede_huisvader() -> None:
    signals = signals_from_csv(FIXTURE, 2023)
    assert signals.disposal_count == 5
    assert signals.acquisition_count == 5
    assert signals.btc_proceeds_eur > 0
    cls, rationale = BelgianClassifier().classify(signals)
    assert cls == BelgianTaxClass.GOEDE_HUISVADER
    assert "Speculator score" in rationale


def test_config_defaults_and_overrides(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.toml")
    assert config.taxpayer.communal_surcharge_rate == Decimal("0.07")
    assert config.classifier.used_leverage is False

    toml_path = tmp_path / "utxoproof.toml"
    toml_path.write_text(
        '[taxpayer]\nreference = "BE-TEST"\ncommunal_surcharge_rate = 0.0587\n'
        "[classifier]\nused_leverage = true\nspeculator_threshold = 10\n"
        "btc_income_fraction = 0.6\n",
        encoding="utf-8",
    )
    config = load_config(toml_path)
    assert config.taxpayer.reference == "BE-TEST"
    assert config.taxpayer.communal_surcharge_rate == Decimal("0.0587")
    assert config.classifier.used_leverage is True
    assert config.classifier.speculator_threshold == 10
    assert config.classifier.btc_income_fraction == Decimal("0.6")

    # Self-reported leverage + income share tip the fixture into speculator territory.
    signals = signals_from_csv(FIXTURE, 2023, config.classifier)
    cls, _ = BelgianClassifier().classify(signals)
    assert cls == BelgianTaxClass.SPECULATOR
