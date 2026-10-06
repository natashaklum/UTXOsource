"""Portfolio dashboard tests (synthetic entities, hand-computed)."""

from decimal import Decimal
from pathlib import Path

from utxoproof.portfolio import (
    Entity,
    FiatHolding,
    Portfolio,
    UtxoHolding,
    svg_bars,
    svg_donut,
)

PRICE = Decimal("40000")


def _portfolio() -> Portfolio:
    return Portfolio(
        entities=[
            Entity("cold", "wallet", "Cold storage", ""),
            Entity("bank", "bank", "ING savings", ""),
        ],
        utxos=[
            UtxoHolding("cold", "A", 0, Decimal("2"), Decimal("80000"), "kyc"),
            UtxoHolding("cold", "C", 1, Decimal("0.5"), Decimal("20000"), "mixed"),
        ],
        fiat=[FiatHolding("bank", Decimal("12500"), "buffer")],
        current_price_eur=PRICE,
    )


def test_totals_and_allocation() -> None:
    portfolio = _portfolio()
    assert portfolio.btc_total == Decimal("2.5")
    assert portfolio.btc_value_eur == Decimal("100000")
    assert portfolio.fiat_total_eur == Decimal("12500")
    assert portfolio.net_worth_eur == Decimal("112500")
    allocation = portfolio.allocation()
    assert [row[0] for row in allocation] == ["cold", "bank"]
    assert allocation[0][2] == Decimal("100000")
    assert sum(row[3] for row in allocation) == Decimal("100")


def test_kyc_split() -> None:
    assert _portfolio().kyc_split() == [
        ("kyc", Decimal("80000")),
        ("mixed", Decimal("20000")),
    ]


def test_charts_contain_labels_and_links() -> None:
    bars = svg_bars(
        [("Cold", Decimal("100000"), "../entities/cold.html"), ("Bank", Decimal("12500"), "")]
    )
    assert "<svg" in bars and "Cold" in bars and "../entities/cold.html" in bars
    assert "100,000.00" in bars
    donut = svg_donut([("kyc", Decimal("80000")), ("mixed", Decimal("20000"))])
    assert "<svg" in donut and "kyc" in donut and "100,000" in donut


def test_overview_and_entity_pages(tmp_path: Path) -> None:
    from utxoproof.reports import write_entity_pages, write_overview_page

    portfolio = _portfolio()
    target = write_overview_page(portfolio, "2024-06-01", "test price", tmp_path)
    html = target.read_text(encoding="utf-8")
    assert "112,500.00" in html  # net worth
    assert "../entities/cold.html" in html
    assert "Cold storage" in html
    assert "<svg" in html and "&lt;svg" not in html  # charts not escaped

    pages = write_entity_pages(portfolio, "../provenance", tmp_path / "entities")
    assert len(pages) == 2
    cold = (tmp_path / "entities" / "cold.html").read_text(encoding="utf-8")
    assert "../provenance/provenance_A_0.html" in cold
    assert "mixed" in cold
    bank = (tmp_path / "entities" / "bank.html").read_text(encoding="utf-8")
    assert "12,500.00" in bank
    assert "provenance_" not in bank  # no UTXOs, no provenance links
