"""utxoproof CLI.

Sprint 0: ``compute --input manual.csv --year Y`` (throwaway verification path,
grows into ``report --year`` in Sprint 2).
Sprint 1: ``import --file kraken.csv --type kraken`` converts an exchange export
to manual-CSV rows for ``compute``.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
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


def compute_status(csv_path: str | Path, price_eur: Decimal) -> dict[str, Decimal]:
    """Current holdings snapshot at ``price_eur`` (whole-file inventory).

    Returns ``btc, cost_eur, avg_cost_eur, value_eur, unrealized_eur``.
    Same moving-average pool as ``compute_details`` (fees included).
    """
    total_btc = Decimal("0")
    total_cost = Decimal("0")
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            side = str(row["side"]).strip().upper()
            btc = Decimal(str(row["btc"]))
            unit = Decimal(str(row["eur_per_btc"]))
            fee = Decimal(str(row.get("fee_eur") or "0"))
            if side == "BUY":
                total_btc += btc
                total_cost += btc * unit + fee
            elif side == "SELL":
                if total_btc <= Decimal("0"):
                    raise ValueError(f"SELL with empty inventory: {row}")
                basis = total_cost / total_btc * btc if total_btc else Decimal("0")
                total_btc -= btc
                total_cost -= basis
            else:
                raise ValueError(f"Unknown side {row['side']!r}")
    value = total_btc * price_eur
    return {
        "btc": total_btc,
        "cost_eur": total_cost,
        "avg_cost_eur": total_cost / total_btc if total_btc else Decimal("0"),
        "value_eur": value,
        "unrealized_eur": value - total_cost,
    }


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
    setup = sub.add_parser("setup", help="Create watch-only wallet, import xpubs")
    setup.add_argument("--rpc-url", default="http://127.0.0.1:8332")
    setup.add_argument("--rpc-user", default="")
    setup.add_argument("--rpc-password", default="")
    setup.add_argument("--wallet", default="utxoproof_watchonly")
    setup.add_argument("--xpub", required=True, help="Account xpub (xpub/ypub/zpub)")
    setup.add_argument("--fingerprint", required=True, help="Master fingerprint (8 hex)")
    setup.add_argument("--purpose", type=int, default=84)
    setup.add_argument("--coin", type=int, default=0)
    setup.add_argument("--account", type=int, default=0)
    sync = sub.add_parser("sync", help="Pull new on-chain transactions into SQLite")
    sync.add_argument("--rpc-url", default="http://127.0.0.1:8332")
    sync.add_argument("--rpc-user", default="")
    sync.add_argument("--rpc-password", default="")
    sync.add_argument("--wallet", default="utxoproof_watchonly")
    sync.add_argument("--db", default="~/.utxoproof/utxoproof.db")
    status = sub.add_parser("status", help="Holdings, cost basis, unrealized P&L")
    status.add_argument("--input", required=True, help="Manual CSV path")
    status.add_argument("--price", type=Decimal, default=None, help="BTC/EUR price override")
    status.add_argument("--db", default="~/.utxoproof/utxoproof.db")
    status.add_argument("--out", default=None, help="Output directory for status.html")
    return parser


def _open_db(path: str) -> sqlite3.Connection:
    from utxoproof.db import init_db

    db_path = Path(path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path))
    init_db(db)
    return db


def _run_setup(args: argparse.Namespace) -> int:
    from utxoproof.bitcoin_rpc import BitcoinRPC
    from utxoproof.descriptors import build_descriptors
    from utxoproof.onchain import BitcoinCoreOnchainImporter

    rpc = BitcoinRPC(args.rpc_url, args.rpc_user, args.rpc_password)
    importer = BitcoinCoreOnchainImporter(rpc, _open_db(":memory:"))
    importer.setup_wallet(args.wallet)
    descriptors = build_descriptors(
        args.xpub, args.fingerprint, args.purpose, args.coin, args.account
    )
    for kind, desc in descriptors.items():
        importer.import_descriptor(args.wallet, desc, "now")
        print(f"imported {kind}: {desc}")
    return 0


def _run_sync(args: argparse.Namespace) -> int:
    from utxoproof.bitcoin_rpc import BitcoinRPC
    from utxoproof.onchain import BitcoinCoreOnchainImporter

    rpc = BitcoinRPC(args.rpc_url, args.rpc_user, args.rpc_password)
    importer = BitcoinCoreOnchainImporter(rpc, _open_db(args.db))
    summary = importer.sync(args.wallet)
    print(f"sync: {summary['new_txs']} new / {summary['txs_seen']} seen")
    return 0


def _resolve_price(price: Decimal | None, db_path: str) -> tuple[Decimal, str]:
    if price is not None:
        return price, "explicit --price"
    import datetime

    from utxoproof.price_oracle import EURPriceOracle

    db = _open_db(db_path)
    day = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=1)
    oracle = EURPriceOracle(db)
    return oracle.get_btc_eur(day), f"Kraken close {day.isoformat()}"


def _run_status(args: argparse.Namespace) -> int:
    from utxoproof.reports import write_status_page

    price, note = _resolve_price(args.price, args.db)
    status = compute_status(args.input, price)
    print(f"holdings_btc: {status['btc']:.8f}")
    print(f"cost_basis_eur: {status['cost_eur']:.2f}")
    print(f"avg_cost_eur: {status['avg_cost_eur']:.2f}")
    print(f"price_eur: {price:.2f} ({note})")
    print(f"value_eur: {status['value_eur']:.2f}")
    print(f"unrealized_eur: {status['unrealized_eur']:.2f}")
    if args.out:
        target = write_status_page(args.input, price, note, args.out)
        print(f"wrote {target}")
    return 0


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
    if args.command == "setup":
        return _run_setup(args)
    if args.command == "sync":
        return _run_sync(args)
    if args.command == "status":
        return _run_status(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
