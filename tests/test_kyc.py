"""KYC propagation + mixing detection (hand-crafted graph, Sec. 12)."""

import sqlite3
from decimal import Decimal

from utxoproof.kyc import (
    compute_output_kyc,
    create_sample_graph,
    detect_mixing_events,
    kyc_summary,
    propagate_graph,
    seed_source_kyc,
)


def _graph_db() -> sqlite3.Connection:
    return create_sample_graph()


def test_compute_output_kyc_pure() -> None:
    assert compute_output_kyc([(100, Decimal("1")), (100, Decimal("1"))]) == (
        "kyc",
        Decimal("1"),
    )
    assert compute_output_kyc([(100, Decimal("0"))]) == ("non_kyc", Decimal("0"))
    status, fraction = compute_output_kyc([(100000000, Decimal("1")), (100000000, Decimal("0"))])
    assert status == "mixed" and fraction == Decimal("0.5")
    assert compute_output_kyc([]) == ("unknown", Decimal("0"))
    assert compute_output_kyc([(0, Decimal("1"))]) == ("unknown", Decimal("0"))


def test_seed_and_propagate() -> None:
    db = _graph_db()
    assert seed_source_kyc(db) == 2
    assert propagate_graph(db) == 3  # C:0, C:1, D:0
    rows = dict(db.execute("SELECT txid || ':' || vout, kyc_status FROM tx_outputs").fetchall())
    assert rows == {
        "A:0": "kyc",
        "B:0": "non_kyc",
        "C:0": "mixed",
        "C:1": "mixed",
        "D:0": "mixed",
    }
    assert db.execute(
        "SELECT kyc_fraction FROM tx_outputs WHERE txid='C' AND vout=0"
    ).fetchone() == ("0.5",)


def test_mixing_detection_and_summary() -> None:
    db = _graph_db()
    seed_source_kyc(db)
    propagate_graph(db)
    events = detect_mixing_events(db)
    # C originates the mix (pure kyc + pure non-kyc); D merely spends it on.
    assert [(e["txid"], e["originating"]) for e in events] == [("C", True), ("D", False)]
    assert events[0]["kyc_inputs"] == 1 and events[0]["non_kyc_inputs"] == 1
    # Unspent: C:1 (mixed) + D:0 (mixed).
    assert kyc_summary(db) == {"kyc": 0, "non_kyc": 0, "mixed": 2, "unknown": 0}
