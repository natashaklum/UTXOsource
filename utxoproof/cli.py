"""utxoproof CLI.

Sprint 0: ``compute --input manual.csv --year Y`` (throwaway verification path,
grows into ``report --year`` in Sprint 2).
Sprint 1: ``import --file kraken.csv --type kraken`` converts an exchange export
to manual-CSV rows for ``compute``.
Sprint 2+: ``report``, ``status``, ``setup``/``sync`` (on-chain skeleton),
``privacy`` (KYC), ``advise`` (per-UTXO advisory).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import sqlite3
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

from utxoproof import __version__
from utxoproof.belgian_tax import COMMUNAL_SURCHARGE_DEFAULT, apply_belgian_tax
from utxoproof.config import Config
from utxoproof.paths import add_data_dir_arg, db_path, evidence_root


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


class YearlyGain(TypedDict):
    year: int
    gain_eur: Decimal
    disposals: int


class Inventory(TypedDict):
    btc: Decimal
    cost_eur: Decimal


class AlltimeResult(TypedDict):
    per_year: list[YearlyGain]
    inventory: Inventory


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


def compute_inventory(csv_path: str | Path) -> Inventory:
    """Whole-file moving-average inventory (BTC + cost basis, no valuation)."""
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
    return {"btc": total_btc, "cost_eur": total_cost}


def compute_status(csv_path: str | Path, price_eur: Decimal) -> dict[str, Decimal]:
    """Current holdings snapshot at ``price_eur`` (whole-file inventory).

    Returns ``btc, cost_eur, avg_cost_eur, value_eur, unrealized_eur``.
    Same moving-average pool as ``compute_details`` (fees included).
    """
    inventory = compute_inventory(csv_path)
    total_btc = inventory["btc"]
    total_cost = inventory["cost_eur"]
    value = total_btc * price_eur
    return {
        "btc": total_btc,
        "cost_eur": total_cost,
        "avg_cost_eur": total_cost / total_btc if total_btc else Decimal("0"),
        "value_eur": value,
        "unrealized_eur": value - total_cost,
    }


def compute_alltime(csv_path: str | Path) -> AlltimeResult:
    """Per-year gains plus remaining inventory across the whole file."""
    years: set[int] = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            years.add(int(str(row["date"])[:4]))
    per_year: list[YearlyGain] = []
    for year in sorted(years):
        details = compute_details(csv_path, year)
        gain = details["gain_loss_eur"]
        per_year.append({"year": year, "gain_eur": gain, "disposals": len(details["disposals"])})
    inventory = compute_inventory(csv_path)
    return {"per_year": per_year, "inventory": inventory}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="utxoproof", description="Bitcoin wealth + tax tool")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    add_data_dir_arg(parser)
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
        choices=[
            "kraken",
            "coinbase",
            "binance",
            "bisq",
            "ing",
            "kbc",
            "bnp",
            "belfius",
            "argenta",
        ],
        help="Source type (exchanges -> manual CSV; banks -> bank rows CSV)",
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
    report.add_argument("--year", type=int, default=None, help="Tax year, e.g. 2023")
    report.add_argument("--alltime", action="store_true", help="All-time summary instead")
    report.add_argument("--out", required=True, help="Output directory")
    report.add_argument("--config", default=None, help="utxoproof.toml path")
    report.add_argument("--db", default=None, help="SQLite DB (full report + oracle)")
    report.add_argument("--evidence-dir", default=None, help="Evidence root")
    report.add_argument("--full", action="store_true", help="Compose fullreport.html too")
    report.add_argument(
        "--utxo",
        action="append",
        default=[],
        help="txid:vout for provenance (repeatable; default: all unspent, max 25)",
    )
    report.add_argument(
        "--price", type=Decimal, default=None, help="BTC/EUR price (full report only)"
    )
    report.add_argument("--as-of", default=None, help="As-of date YYYY-MM-DD")
    report.add_argument(
        "--source", action="append", default=[], help="Raw source file (repeatable)"
    )
    report.add_argument("--no-zip", action="store_true", help="Skip evidence ZIP")
    report.add_argument(
        "--communal-rate",
        default=None,
        type=Decimal,
        help="Communal surcharge rate (default: config [taxpayer])",
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
    sync.add_argument("--db", default=None, help="SQLite DB (default: <data-dir>/utxoproof.db)")
    status = sub.add_parser("status", help="Holdings, cost basis, unrealized P&L")
    status.add_argument("--input", required=True, help="Manual CSV path")
    status.add_argument("--price", type=Decimal, default=None, help="BTC/EUR price override")
    status.add_argument("--db", default=None, help="SQLite DB (default: <data-dir>/utxoproof.db)")
    status.add_argument("--out", default=None, help="Output directory for status.html")
    privacy = sub.add_parser("privacy", help="KYC analysis and mixing events")
    privacy.add_argument("--db", default=None, help="SQLite DB (default: <data-dir>/utxoproof.db)")
    privacy.add_argument("--out", default=None, help="Output directory for privacy.html")
    advise = sub.add_parser("advise", help="Per-UTXO advisory table")
    advise.add_argument("--db", default=None, help="SQLite DB (default: <data-dir>/utxoproof.db)")
    advise.add_argument("--price", type=Decimal, default=None, help="BTC/EUR price override")
    advise.add_argument("--as-of", default=None, help="As-of date YYYY-MM-DD (default: today)")
    advise.add_argument("--out", default=None, help="Output directory for advisory.html")
    advise.add_argument(
        "--min-value", type=Decimal, default=Decimal("0"), help="Min EUR value to show"
    )
    prov = sub.add_parser("provenance", help="Chain-of-custody report for a UTXO")
    prov.add_argument("utxo", help="txid:vout")
    prov.add_argument("--db", default=None, help="SQLite DB (default: <data-dir>/utxoproof.db)")
    prov.add_argument("--price", type=Decimal, default=None, help="Current BTC/EUR price")
    prov.add_argument("--as-of", default=None, help="As-of date YYYY-MM-DD (default: today)")
    prov.add_argument("--depth", type=int, default=100, help="Max chain depth")
    prov.add_argument("--out", default=None, help="Output directory")
    prov.add_argument("--evidence-dir", default=None, help="Evidence root")
    attach = sub.add_parser("attach", help="Register a supporting file (scan, PDF, screenshot)")
    attach.add_argument("--file", required=True, help="File to register (copied in)")
    attach.add_argument("--db", default=None, help="SQLite DB (default: <data-dir>/utxoproof.db)")
    attach.add_argument("--tx", default=None, help="Transaction it supports")
    attach.add_argument("--note", default="", help="What this file proves")
    attach.add_argument("--year", type=int, default=None, help="Evidence year")
    attach.add_argument("--evidence-dir", default=None, help="Evidence root")
    return parser


def _open_db(path: str) -> sqlite3.Connection:
    from utxoproof.db import init_db

    db_path = Path(path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path))
    init_db(db)
    return db


def _write_full_from_args(args: argparse.Namespace, communal: Decimal, config: Config) -> Path:
    """Compose fullreport.html from report args (db + oracle/constant curve)."""
    from utxoproof.reports import write_full_report

    db = _open_db(str(db_path(args)))
    price, note = _resolve_price(args.price, args)
    as_of = (
        datetime.date.fromisoformat(args.as_of)
        if args.as_of
        else datetime.datetime.now(datetime.UTC).date()
    )

    def curve(day: datetime.date) -> Decimal:
        return price

    targets = _parse_utxo_targets(args, db)
    return write_full_report(
        db=db,
        csv_path=args.input,
        year=args.year,
        out_dir=args.out,
        price_at=curve,
        current_price_eur=price,
        price_note=note,
        as_of=as_of,
        communal_rate=communal,
        classifier_cfg=config.classifier,
        provenance_targets=targets,
    )


def _parse_utxo_targets(args: argparse.Namespace, db: sqlite3.Connection) -> list[tuple[str, int]]:
    """Explicit --utxo list, else all unspent (capped)."""
    if args.utxo:
        targets = []
        for item in args.utxo:
            txid, vout = item.rsplit(":", 1)
            targets.append((txid, int(vout)))
        return targets
    rows = db.execute(
        "SELECT txid, vout FROM tx_outputs WHERE spent_by_txid IS NULL LIMIT 26"
    ).fetchall()
    if len(rows) > 25:
        print("note: provenance limited to 25 UTXOs")
    return [(r[0], r[1]) for r in rows[:25]]


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
    importer = BitcoinCoreOnchainImporter(rpc, _open_db(str(db_path(args))))
    summary = importer.sync(args.wallet)
    print(f"sync: {summary['new_txs']} new / {summary['txs_seen']} seen")
    return 0


def _resolve_price(price: Decimal | None, args: argparse.Namespace) -> tuple[Decimal, str]:
    if price is not None:
        return price, "explicit --price"
    import datetime

    from utxoproof.paths import db_path
    from utxoproof.price_oracle import EURPriceOracle

    db = _open_db(str(db_path(args)))
    day = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=1)
    oracle = EURPriceOracle(db)
    return oracle.get_btc_eur(day), f"Kraken close {day.isoformat()}"


def _run_status(args: argparse.Namespace) -> int:
    from utxoproof.reports import write_status_page

    price, note = _resolve_price(args.price, args)
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


def _run_advise(args: argparse.Namespace) -> int:
    from utxoproof.advisory import analyze_wallet, portfolio_summary
    from utxoproof.kyc import propagate_graph, seed_source_kyc
    from utxoproof.reports import write_advisory_page

    db = _open_db(str(db_path(args)))
    seed_source_kyc(db)
    propagate_graph(db)
    as_of = (
        datetime.date.fromisoformat(args.as_of)
        if args.as_of
        else datetime.datetime.now(datetime.UTC).date()
    )
    price: Decimal
    curve: Callable[[datetime.date], Decimal]
    if args.price is not None:
        price = Decimal(args.price)
        note = "explicit --price"

        def curve(_day: datetime.date) -> Decimal:
            return price

    else:
        from utxoproof.price_oracle import EURPriceOracle

        oracle = EURPriceOracle(db)
        curve = oracle.get_btc_eur
        note = "daily close per acquisition date"
        price = oracle.get_btc_eur(as_of)
    advisories = [
        a for a in analyze_wallet(db, curve, price, as_of) if a.current_value_eur >= args.min_value
    ]
    for a in advisories:
        flags = ",".join(sorted(f.value for f in a.flags))
        print(f"{a.txid}:{a.vout} {a.amount_btc:.8f}BTC tax={a.tax_if_sold_eur:.2f} [{flags}]")
    summary = portfolio_summary(advisories)
    print(f"liquidate_tax_eur: {summary['total_tax_eur']:.2f}")
    if args.out:
        target = write_advisory_page(advisories, price, note, as_of.isoformat(), args.out)
        print(f"wrote {target}")
    return 0


def _run_privacy(args: argparse.Namespace) -> int:
    from utxoproof.kyc import detect_mixing_events, kyc_summary, propagate_graph, seed_source_kyc
    from utxoproof.reports import write_privacy_page

    db = _open_db(str(db_path(args)))
    seed_source_kyc(db)
    propagate_graph(db)
    summary = kyc_summary(db)
    print("kyc_summary: " + ", ".join(f"{k}={v}" for k, v in summary.items()))
    events = detect_mixing_events(db)
    print(f"mixing_events: {len(events)}")
    if args.out:
        target = write_privacy_page(db, args.out)
        print(f"wrote {target}")
    return 0


def _run_provenance(args: argparse.Namespace) -> int:
    from utxoproof.provenance import build_provenance_chain
    from utxoproof.reports import write_provenance_page

    try:
        txid, vout_str = args.utxo.rsplit(":", 1)
        vout = int(vout_str)
    except ValueError:
        raise ValueError(f"UTXO must look like txid:vout, got {args.utxo!r}") from None
    db = _open_db(str(db_path(args)))
    as_of = (
        datetime.date.fromisoformat(args.as_of)
        if args.as_of
        else datetime.datetime.now(datetime.UTC).date()
    )
    price: Decimal
    curve: Callable[[datetime.date], Decimal]
    if args.price is not None:
        price = Decimal(args.price)
        note = "explicit --price"

        def curve(_day: datetime.date) -> Decimal:
            return price

    else:
        from utxoproof.price_oracle import EURPriceOracle

        oracle = EURPriceOracle(db)
        curve = oracle.get_btc_eur
        note = "daily close per step date"
        price = oracle.get_btc_eur(as_of)
    steps = build_provenance_chain(txid, vout, db, curve, args.depth)
    print(
        f"chain: {len(steps)} steps back to {steps[0].txid}:{steps[0].vout}" if steps else "empty"
    )
    print(f"price_note: {note}")
    if args.out:
        target = write_provenance_page(
            db,
            txid,
            vout,
            curve,
            price,
            as_of,
            args.out,
            args.depth,
            evidence_root=evidence_root(args),
        )
        print(f"wrote {target}")
    return 0


def _run_attach(args: argparse.Namespace) -> int:
    import datetime

    from utxoproof.evidence import attach_file

    db = _open_db(str(db_path(args)))
    year = args.year or datetime.datetime.now(datetime.UTC).date().year
    entry = attach_file(db, args.file, evidence_root(args), year, args.tx, args.note)
    print(f"registered {entry['filename']} sha256={entry['sha256'][:16]}…")
    if entry["txid"]:
        print(f"linked to {entry['txid']}")
    return 0


def _run_import(args: argparse.Namespace) -> int:
    from utxoproof.banks import BANK_PROFILES, parse_bank_csv
    from utxoproof.binance_csv import parse_binance_csv
    from utxoproof.bisq_csv import parse_bisq_csv
    from utxoproof.coinbase_csv import parse_coinbase_csv
    from utxoproof.exchange import to_manual_csv_rows
    from utxoproof.kraken_csv import parse_kraken_ledgers

    if args.type in ("kraken", "coinbase", "binance", "bisq"):
        parser = {
            "kraken": parse_kraken_ledgers,
            "coinbase": parse_coinbase_csv,
            "binance": parse_binance_csv,
            "bisq": parse_bisq_csv,
        }[args.type]
        txs = parser(args.file)
        if args.kyc != "kyc":
            for tx in txs:
                tx.kyc_status = args.kyc
        rows = to_manual_csv_rows(txs)
    elif args.type in BANK_PROFILES:
        bank_rows = parse_bank_csv(args.file, args.type)
        rows = [
            {
                "date": r.date.isoformat(),
                "side": "",
                "btc": "",
                "eur_per_btc": "",
                "fee_eur": "",
                "description": r.description,
                "amount_eur": str(r.amount_eur),
            }
            for r in bank_rows
        ]
    else:  # pragma: no cover - argparse choices guard this
        raise ValueError(f"Unsupported type {args.type!r}")

    fieldnames = list(rows[0].keys()) if rows else ["date"]
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
        from utxoproof.config import load_config
        from utxoproof.evidence import build_manifest_db, produce_evidence_zip, record_source
        from utxoproof.reports import write_alltime_page, write_report

        config = load_config(args.config)
        communal = (
            Decimal(args.communal_rate)
            if args.communal_rate is not None
            else config.taxpayer.communal_surcharge_rate
        )
        if args.alltime:
            target = write_alltime_page(args.input, args.out)
            print(f"wrote {target}")
            return 0
        if args.year is None:
            raise ValueError("report needs --year Y or --alltime")
        target = write_report(args.input, args.year, args.out, communal, config.classifier)
        print(f"wrote {target}")
        if args.full:
            full = _write_full_from_args(args, communal, config)
            print(f"wrote {full}")
        if not args.no_zip:
            manifest_db_path = Path(args.out) / "evidence-manifest.db"
            manifest_db = build_manifest_db(manifest_db_path)
            for source in [args.input, *args.source]:
                record_source(manifest_db, source, "source")
            year_dir = evidence_root(args) / str(args.year)
            attached = sorted(year_dir.glob("*")) if year_dir.is_dir() else []
            for file in attached:
                if file.is_file():
                    record_source(manifest_db, file, "attachment", name=f"{args.year}/{file.name}")
            manifest_db.close()
            zip_path = produce_evidence_zip(
                args.year,
                manifest_db_path,
                target,
                [Path(s) for s in args.source],
                [Path(args.input)],
                args.out,
                attachments=attached,
            )
            print(f"wrote {zip_path}")
        return 0
    if args.command == "setup":
        return _run_setup(args)
    if args.command == "sync":
        return _run_sync(args)
    if args.command == "status":
        return _run_status(args)
    if args.command == "privacy":
        return _run_privacy(args)
    if args.command == "advise":
        return _run_advise(args)
    if args.command == "provenance":
        return _run_provenance(args)
    if args.command == "attach":
        return _run_attach(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
