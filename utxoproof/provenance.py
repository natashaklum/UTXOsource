"""UTXO provenance: chain-of-custody graph traversal (plan Sec. 14, Sprint 6).

Walks `tx_inputs -> tx_outputs` backwards from a selected UTXO, following the
largest parent input at each step, with cycle guard and depth cap. Callers
supply `price_at(date)` so tests stay offline; the CLI wires the oracle.
"""

from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

SAT_PER_BTC = 100_000_000


@dataclass
class ProvenanceStep:
    step_number: int
    txid: str
    vout: int
    block_height: int | None
    block_time: datetime.datetime
    amount_sat: int
    amount_btc: Decimal
    eur_price: Decimal
    eur_value: Decimal
    kyc_status: str
    kyc_fraction: Decimal
    source_type: str
    source_label: str
    source_evidence: str
    event_description: str
    mixing_event: bool
    parent_utxos: list[tuple[str, int]] = field(default_factory=list)
    sibling_utxos: list[tuple[str, int]] = field(default_factory=list)


def db_get_output(db: sqlite3.Connection, txid: str, vout: int) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT txid, vout, address, value_sat, kyc_status, kyc_fraction, "
        "source_type, source_label, source_evidence, block_height, block_time "
        "FROM tx_outputs JOIN transactions USING (txid) "
        "WHERE tx_outputs.txid=? AND vout=?",
        (txid, vout),
    ).fetchone()
    if row is None:
        return None
    keys = (
        "txid",
        "vout",
        "address",
        "value_sat",
        "kyc_status",
        "kyc_fraction",
        "source_type",
        "source_label",
        "source_evidence",
        "block_height",
        "block_time",
    )
    return dict(zip(keys, row, strict=True))


def db_get_inputs_for_tx(db: sqlite3.Connection, txid: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT prev_txid, prev_vout FROM tx_inputs WHERE txid=? ORDER BY input_index",
        (txid,),
    ).fetchall()
    return [{"prev_txid": r[0], "prev_vout": r[1]} for r in rows]


def db_get_outputs_for_tx(db: sqlite3.Connection, txid: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT txid, vout FROM tx_outputs WHERE txid=? ORDER BY vout", (txid,)
    ).fetchall()
    return [{"txid": r[0], "vout": r[1]} for r in rows]


def classify_event(
    source_type: str | None,
    source_label: str | None,
    n_inputs: int,
    n_outputs: int,
) -> str:
    """Human-readable on-chain event description (spec Sec. 14)."""
    if source_type == "exchange_purchase":
        return f"Exchange purchase ({source_label or ''})".rstrip()
    if source_type == "p2p_purchase":
        return f"P2P purchase ({source_label or ''})".rstrip()
    if n_inputs == 0:
        return "Coinbase reward (mining)"
    if n_inputs == 1 and n_outputs == 1:
        return "Self-transfer (simple move between wallets)"
    if n_inputs > 1 and n_outputs <= 2:
        return f"Consolidation ({n_inputs} inputs merged)"
    if n_inputs == 1 and n_outputs > 2:
        return f"Fan-out ({n_outputs} outputs created)"
    if n_outputs == 2:
        return "Spend (payment + change)"
    return f"On-chain transaction ({n_inputs} inputs, {n_outputs} outputs)"


def build_provenance_chain(
    txid: str,
    vout: int,
    db: sqlite3.Connection,
    price_at: Callable[[datetime.date], Decimal],
    max_depth: int = 100,
) -> list[ProvenanceStep]:
    """Walk back from ``txid:vout`` to origin. Returns steps oldest-first."""
    steps: list[ProvenanceStep] = []
    visited: set[tuple[str, int]] = set()
    current: tuple[str, int] | None = (txid, vout)

    def _value_sat(ref: tuple[str, int]) -> int:
        row = db_get_output(db, ref[0], ref[1])
        return row["value_sat"] if row else 0

    while current and len(steps) < max_depth:
        if current in visited:
            break
        visited.add(current)
        output = db_get_output(db, current[0], current[1])
        if output is None:
            break

        block_time = datetime.datetime.fromisoformat(output["block_time"])
        if block_time.tzinfo is None:
            block_time = block_time.replace(tzinfo=datetime.UTC)
        eur_price = price_at(block_time.date())
        amount_btc = Decimal(output["value_sat"]) / Decimal(SAT_PER_BTC)

        inputs = db_get_inputs_for_tx(db, output["txid"])
        parent_utxos = [(i["prev_txid"], i["prev_vout"]) for i in inputs]
        all_outputs = db_get_outputs_for_tx(db, output["txid"])
        sibling_utxos = [(o["txid"], o["vout"]) for o in all_outputs if o["vout"] != output["vout"]]
        parent_statuses = {
            (db_get_output(db, p[0], p[1]) or {}).get("kyc_status") for p in parent_utxos
        } - {None}

        steps.append(
            ProvenanceStep(
                step_number=0,  # renumbered after reversal
                txid=output["txid"],
                vout=output["vout"],
                block_height=output["block_height"],
                block_time=block_time,
                amount_sat=output["value_sat"],
                amount_btc=amount_btc,
                eur_price=eur_price,
                eur_value=amount_btc * eur_price,
                kyc_status=output["kyc_status"],
                kyc_fraction=Decimal(output["kyc_fraction"]),
                source_type=output["source_type"] or "unknown",
                source_label=output["source_label"] or "",
                source_evidence=output["source_evidence"] or "",
                event_description=classify_event(
                    output["source_type"],
                    output["source_label"],
                    len(inputs),
                    len(all_outputs),
                ),
                mixing_event=len(parent_statuses) > 1,
                parent_utxos=parent_utxos,
                sibling_utxos=sibling_utxos,
            )
        )
        # Walk back along the largest parent input (deterministic on ties:
        # lowest input_index wins via max stability).
        current = max(parent_utxos, key=_value_sat) if parent_utxos else None

    steps.reverse()
    for i, step in enumerate(steps, 1):
        step.step_number = i
    return steps
