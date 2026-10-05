"""KYC tagging and mixing analysis (plan Sec. 12, Sprint 4).

Every UTXO carries ``kyc_status`` (kyc | non_kyc | mixed | unknown) and
``kyc_fraction`` (0.0-1.0, KYC-originated satoshi share), propagated
proportionally through the tx graph. A mixing event is any transaction with at
least one KYC and one non-KYC input.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

KYC = "kyc"
NON_KYC = "non_kyc"
MIXED = "mixed"
UNKNOWN = "unknown"

STATUSES = (KYC, NON_KYC, MIXED, UNKNOWN)

# Source annotation -> (kyc_status, kyc_fraction) per Sec. 12 tagging rules.
SOURCE_SEED: dict[str, tuple[str, Decimal]] = {
    "exchange_purchase": (KYC, Decimal("1")),
    "p2p_purchase": (NON_KYC, Decimal("0")),
    "mining": (NON_KYC, Decimal("0")),
}


def compute_output_kyc(inputs: list[tuple[int, Decimal]]) -> tuple[str, Decimal]:
    """Proportional KYC status/fraction from ``(value_sat, kyc_fraction)`` inputs."""
    total_sat = sum((Decimal(value) for value, _ in inputs), Decimal("0"))
    if total_sat == 0:
        return UNKNOWN, Decimal("0")
    kyc_sat = sum((fraction * value for value, fraction in inputs), Decimal("0"))
    fraction = kyc_sat / total_sat
    if fraction == Decimal("1"):
        return KYC, fraction
    if fraction == Decimal("0"):
        return NON_KYC, fraction
    return MIXED, fraction


def seed_source_kyc(db: sqlite3.Connection) -> int:
    """Apply source-type seed tags to outputs lacking KYC info. Returns count."""
    updated = 0
    for source_type, (status, fraction) in SOURCE_SEED.items():
        cursor = db.execute(
            "UPDATE tx_outputs SET kyc_status=?, kyc_fraction=? "
            "WHERE source_type=? AND kyc_status='unknown'",
            (status, str(fraction), source_type),
        )
        updated += cursor.rowcount
    db.commit()
    return updated


def propagate_graph(db: sqlite3.Connection) -> int:
    """Fixpoint KYC propagation over the tx graph. Returns outputs updated."""
    updated = 0
    while True:
        progressed = False
        outputs = db.execute(
            "SELECT txid, vout FROM tx_outputs WHERE kyc_status='unknown'"
        ).fetchall()
        for txid, vout in outputs:
            inputs = db.execute(
                "SELECT o.value_sat, o.kyc_fraction FROM tx_inputs i "
                "JOIN tx_outputs o ON o.txid=i.prev_txid AND o.vout=i.prev_vout "
                "WHERE i.txid=? AND o.kyc_status != 'unknown'",
                (txid,),
            ).fetchall()
            if not inputs:
                continue
            # Only propagate when ALL parents are known (else wait for fixpoint).
            parent_count = db.execute(
                "SELECT COUNT(*) FROM tx_inputs WHERE txid=?", (txid,)
            ).fetchone()[0]
            is_coinbase = db.execute(
                "SELECT is_coinbase FROM transactions WHERE txid=?", (txid,)
            ).fetchone()
            if is_coinbase and is_coinbase[0]:
                continue  # coinbases need source seeding, not propagation
            if len(inputs) < parent_count:
                continue
            status, fraction = compute_output_kyc([(row[0], Decimal(row[1])) for row in inputs])
            db.execute(
                "UPDATE tx_outputs SET kyc_status=?, kyc_fraction=? WHERE txid=? AND vout=?",
                (status, str(fraction), txid, vout),
            )
            updated += 1
            progressed = True
        db.commit()
        if not progressed:
            break
    return updated


def detect_mixing_events(db: sqlite3.Connection) -> list[dict[str, object]]:
    """Transactions combining KYC and non-KYC inputs."""
    events = []
    txids = db.execute("SELECT DISTINCT txid FROM tx_inputs").fetchall()
    for (txid,) in txids:
        inputs = db.execute(
            "SELECT o.kyc_status, o.value_sat FROM tx_inputs i "
            "JOIN tx_outputs o ON o.txid=i.prev_txid AND o.vout=i.prev_vout "
            "WHERE i.txid=?",
            (txid,),
        ).fetchall()
        if not inputs or any(status == UNKNOWN for status, _ in inputs):
            continue
        fractions = {status for status, _ in inputs}
        has_kyc = KYC in fractions or MIXED in fractions
        has_non_kyc = NON_KYC in fractions or MIXED in fractions
        kyc_inputs = sum(1 for status, _ in inputs if status in (KYC, MIXED))
        non_kyc_inputs = sum(1 for status, _ in inputs if status in (NON_KYC, MIXED))
        if has_kyc and has_non_kyc:
            events.append(
                {
                    "txid": txid,
                    "inputs": len(inputs),
                    "kyc_inputs": kyc_inputs,
                    "non_kyc_inputs": non_kyc_inputs,
                    "value_sat": sum(value for _, value in inputs),
                    # True where pure KYC and pure non-KYC lineages first
                    # combine; False where mixed coins are merely spent on.
                    "originating": KYC in fractions and NON_KYC in fractions,
                }
            )
    return events


def kyc_summary(db: sqlite3.Connection) -> dict[str, int]:
    """Unspent-output counts per KYC status."""
    rows = db.execute(
        "SELECT kyc_status, COUNT(*) FROM tx_outputs "
        "WHERE spent_by_txid IS NULL GROUP BY kyc_status"
    ).fetchall()
    summary = dict.fromkeys(STATUSES, 0)
    for status, count in rows:
        summary[status] = count
    return summary


def create_sample_graph() -> sqlite3.Connection:
    """Hand-crafted demo graph: KYC purchase + mining reward consolidated.

    A:0 (exchange, 1 BTC) + B:0 (mining, 1 BTC) -> C (1.5 + 0.5, mixed) ->
    D:0 (1.5, mixed). Shared by tests and the demo site.
    """
    from utxoproof.db import open_memory_db

    db = open_memory_db()
    for txid, day in (
        ("A", "2023-01-01"),
        ("B", "2023-01-02"),
        ("C", "2023-02-01"),
        ("D", "2023-03-01"),
    ):
        db.execute("INSERT INTO transactions (txid, block_time) VALUES (?, ?)", (txid, day))
    db.execute(
        "INSERT INTO tx_outputs (txid, vout, value_sat, source_type) "
        "VALUES ('A', 0, 100000000, 'exchange_purchase')"
    )
    db.execute(
        "INSERT INTO tx_outputs (txid, vout, value_sat, source_type) "
        "VALUES ('B', 0, 100000000, 'mining')"
    )
    db.execute("INSERT INTO tx_outputs (txid, vout, value_sat) VALUES ('C', 0, 150000000)")
    db.execute("INSERT INTO tx_outputs (txid, vout, value_sat) VALUES ('C', 1, 50000000)")
    db.execute("INSERT INTO tx_outputs (txid, vout, value_sat) VALUES ('D', 0, 150000000)")
    db.execute(
        "INSERT INTO tx_inputs (txid, input_index, prev_txid, prev_vout) VALUES "
        "('C', 0, 'A', 0), ('C', 1, 'B', 0), ('D', 0, 'C', 0)"
    )
    db.execute("UPDATE tx_outputs SET spent_by_txid='C' WHERE txid IN ('A', 'B')")
    db.execute("UPDATE tx_outputs SET spent_by_txid='D' WHERE txid='C' AND vout=0")
    db.commit()
    return db
