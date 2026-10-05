"""Build the Pages demo site: HTML reports from fixture data + index.

Usage: ``python scripts/build_demo.py --out site``. Reads only files under
``tests/fixtures``; writes self-contained HTML (no external assets).
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from utxoproof.kraken_csv import parse_kraken_ledgers, to_manual_csv_rows
from utxoproof.reports import write_descriptors_page, write_report, write_status_page

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Demo:
    slug: str
    title: str
    csv_path: Path | None
    year: int


DEMOS: list[Demo] = [
    Demo(
        slug="manual-2023",
        title="Manual CSV — tax year 2023",
        csv_path=ROOT / "tests" / "fixtures" / "manual_2023.csv",
        year=2023,
    ),
    Demo(
        slug="kraken-2023",
        title="Kraken ledgers.csv import — tax year 2023",
        csv_path=None,  # converted from kraken_ledgers_2023.csv below
        year=2023,
    ),
]

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>utxoproof demo reports</title></head>
<body>
<h1>utxoproof demo reports</h1>
<p>Generated from synthetic fixture data (not real transactions).</p>
<ul>
{links}
</ul>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output site directory")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    links: list[str] = []

    for demo in DEMOS:
        slug = demo.slug
        year = demo.year
        if demo.csv_path is None:
            txs = parse_kraken_ledgers(ROOT / "tests" / "fixtures" / "kraken_ledgers_2023.csv")
            rows = to_manual_csv_rows(txs)
            csv_path = out / f"{slug}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["date", "side", "btc", "eur_per_btc", "fee_eur"]
                )
                writer.writeheader()
                writer.writerows(rows)
        else:
            csv_path = demo.csv_path
        target = write_report(str(csv_path), year, out / slug)
        rel = target.relative_to(out)
        links.append(f'<li><a href="{rel}">{demo.title}</a></li>')

    write_descriptors_page(out / "descriptors")
    links.append(
        '<li><a href="descriptors/descriptors.html">Descriptor check (BIP84 vectors)</a></li>'
    )

    # Holdings status at a fixed, labeled demo price (deterministic output).
    from decimal import Decimal

    demo_price = Decimal("40000")
    price_note = "fixed demo price 40000 EUR/BTC"
    for slug, csv_path in (
        ("manual-2023", ROOT / "tests" / "fixtures" / "manual_2023.csv"),
        ("kraken-2023", out / "kraken-2023.csv"),
    ):
        write_status_page(csv_path, demo_price, price_note, out / slug)
        links.append(f'<li><a href="{slug}/status.html">Holdings status — {slug}</a></li>')

    (out / "index.html").write_text(INDEX_TEMPLATE.format(links="\n".join(links)), encoding="utf-8")
    print(f"demo site: {out} ({len(links)} reports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
