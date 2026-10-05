"""First HTML tax report (demo data)."""

from decimal import Decimal
from pathlib import Path

from utxoproof.reports import build_report, render_report, write_report

FIXTURE = Path(__file__).parent / "fixtures" / "manual_2023.csv"
KRAKEN = Path(__file__).parent / "fixtures" / "kraken_ledgers_2023.csv"


def test_report_totals_match_compute() -> None:
    report = build_report(FIXTURE, 2023)
    assert report.gain_eur == Decimal("4337.670995670995670995670995")
    assert report.tax_eur == report.gain_eur * Decimal("0.33")
    assert report.total_eur == report.tax_eur + report.communal_eur
    assert len(report.disposals) == 5
    assert sum((d.gain_eur for d in report.disposals), Decimal("0")) == report.gain_eur


def test_report_html_contains_figures(tmp_path: Path) -> None:
    target = write_report(FIXTURE, 2023, tmp_path)
    html = target.read_text(encoding="utf-8")
    assert "utxoproof tax report 2023" in html
    assert "4337.67" in html  # gain
    assert "1431.43" in html  # tax
    assert "goede huisvader" in html
    assert "fiscaal adviseur" in html


def test_kraken_report_end_to_end(tmp_path: Path) -> None:
    import csv

    from utxoproof.kraken_csv import parse_kraken_ledgers, to_manual_csv_rows

    rows = to_manual_csv_rows(parse_kraken_ledgers(KRAKEN))
    csv_path = tmp_path / "kraken.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "side", "btc", "eur_per_btc", "fee_eur"])
        writer.writeheader()
        writer.writerows(rows)
    report = build_report(csv_path, 2023)
    assert report.gain_eur == Decimal("2905")
    html = render_report(report)
    assert "2905.00" in html and "958.65" in html


def test_descriptors_page_shows_vector_addresses(tmp_path: Path) -> None:
    from utxoproof.reports import write_descriptors_page

    target = write_descriptors_page(tmp_path)
    html = target.read_text(encoding="utf-8")
    assert "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu" in html
    assert "bc1qnjg0jd8228aq7egyzacy8cys3knf9xvrerkf9g" in html
    assert "bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el" in html
    assert "73c5da0a" in html
