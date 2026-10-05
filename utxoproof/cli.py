"""utxoproof CLI.

Sprint 0: ``compute --input manual.csv --year Y`` (throwaway verification path,
grows into ``report --year`` in Sprint 2).
Sprint 1: ``import --file kraken.csv --type kraken`` converts an exchange export
to manual-CSV rows for ``compute``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

from utxoproof import __version__
from utxoproof.belgian_tax import COMMUNAL_SURCHARGE_DEFAULT, apply_belgian_tax


class DisposalDetail(TypedDict):
    date: str
    btc: Decimal
    eur_per_btc: Decimal
    proceeds_eur: Decimal
    cost_basis_eur: Decimal
    gain_eur: Decimal


class ComputeResult(TypedDict):
    disposals: list[DisposalDetail]
    gain_loss_eur: Decimal


def compute_details(csv_path: str | Path, year: int) -> ComputeResult:
    """Per-disposal moving-average detail for ``year`` plus the yearly total.

    Returns ``{"disposals": [...], "gain_loss_eur": Decimal}`` where each
    disposal has ``date, btc, eur_per_btc, proceeds_eur, cost_basis_eur,
    gain_eur``. Buy fees join the cost pool, sell fees reduce proceeds.
    """
    total_btc = Decimal("0")
    total_cost = Decimal("0")
    realised_gain = Decimal("0")
    disposals: list[DisposalDetail] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row_year = int(str(row["date"])[:4])
            side = str(row["side"]).strip().upper()
            btc = Decimal(str(row["btc"]))
            price = Decimal(str(row["eur_per_btc"]))
            fee = Decimal(str(row.get("fee_eur") or "0"))
            if side == "BUY":
                total_btc += btc
                total_cost += btc * price + fee
            elif side == "SELL":
                if total_btc <= Decimal("0"):
                    raise ValueError(f"SELL with empty inventory: {row}")
                avg_unit = total_cost / total_btc if total_btc else Decimal("0")
                cost_basis = avg_unit * btc
                proceeds = btc * price - fee
                gain = proceeds - cost_basis
                if row_year == year:
                    realised_gain += gain
                    disposals.append(
                        {
                            "date": str(row["date"]),
                            "btc": btc,
                            "eur_per_btc": price,
                            "proceeds_eur": proceeds,
                            "cost_basis_eur": cost_basis,
                            "gain_eur": gain,
                        }
                    )
                total_btc -= btc
                total_cost -= cost_basis
            else:
                raise ValueError(f"Unknown side {row['side']!r}")
    return {"disposals": disposals, "gain_loss_eur": realised_gain}


def compute_year(csv_path: str | Path, year: int) -> dict[str, Decimal]:
    """Compute realised gain/loss for ``year`` from a simple manual CSV.

    CSV columns: ``date,side,btc,eur_per_btc,fee_eur`` where ``date`` is
    ``YYYY-MM-DD`` and ``side`` is ``BUY`` or ``SELL``. Moving-average cost
    basis; buy fees join the cost pool, sell fees reduce proceeds.
    """
    return {"gain_loss_eur": compute_details(csv_path, year)["gain_loss_eur"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="utxoproof", description="utxoproof Sprint 0")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    compute = sub.add_parser("compute", help="Sprint 0 gain/loss + Belgian tax check")
    compute.add_argument("--input", required=True, help="Manual CSV path")
    compute.add_argument("--year", required=True, type=int, help="Tax year, e.g. 2023")
    compute.add_argument(
        "--communal-rate",
        default=COMMUNAL_SURCHARGE_DEFAULT,
        type=Decimal,
        help="Communal surcharge rate (default 0.07)",
    )
    impi = sub.add_parser("import", help="Convert an exchange export to manual CSV")
    impi.add_argument("--file", required=True, help="Source file to import")
    impi.add_argument(
        "--type",
        required=True,
        choices=["kraken"],
        help="Exchange type (Sprint 1: kraken only)",
    )
    impi.add_argument(
        "--kyc",
        default="kyc",
        choices=["kyc", "non_kyc", "unknown"],
        help="Override KYC status (default: exchange default)",
    )
    impi.add_argument(
        "--out",
        default=None,
        help="Output manual-CSV path (default: stdout)",
    )
    report = sub.add_parser("report", help="Generate an HTML tax report")
    report.add_argument("--input", required=True, help="Manual CSV path")
    report.add_argument("--year", required=True, type=int, help="Tax year, e.g. 2023")
    report.add_argument("--out", required=True, help="Output directory for report.html")
    report.add_argument(
        "--communal-rate",
        default=COMMUNAL_SURCHARGE_DEFAULT,
        type=Decimal,
        help="Communal surcharge rate (default 0.07)",
    )
    return parser


def _run_import(args: argparse.Namespace) -> int:
    from utxoproof.kraken_csv import parse_kraken_ledgers, to_manual_csv_rows

    if args.type == "kraken":
        txs = parse_kraken_ledgers(args.file)
        if args.kyc != "kyc":
            for tx in txs:
                tx.kyc_status = args.kyc
        rows = to_manual_csv_rows(txs)
    else:  # pragma: no cover - argparse choices guard this
        raise ValueError(f"Unsupported type {args.type!r}")

    fieldnames = ["date", "side", "btc", "eur_per_btc", "fee_eur"]
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"imported {len(rows)} transactions ({args.type})",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compute":
        result = compute_year(args.input, args.year)
        gain = result["gain_loss_eur"]
        tax = apply_belgian_tax(gain, "goede_huisvader", args.communal_rate)
        print(f"year: {args.year}")
        print(f"gain_loss_eur: {gain:.2f}")
        print(f"tax_eur: {tax['tax_eur']:.2f}")
        print(f"communal_surcharge_eur: {tax['communal_surcharge_eur']:.2f}")
        print(f"total_eur: {tax['total_eur']:.2f}")
        return 0
    if args.command == "import":
        return _run_import(args)
    if args.command == "report":
        from utxoproof.reports import write_report

        target = write_report(args.input, args.year, args.out, args.communal_rate)
        print(f"wrote {target}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
