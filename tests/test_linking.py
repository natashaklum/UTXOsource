"""Kraken-withdrawal to on-chain funding matcher (plan v5 Sec. 10)."""

import datetime
from decimal import Decimal

from utxoproof.linking import (
    FundingResult,
    Withdrawal,
    funding_from_ledgers,
    kraken_btc_withdrawals,
    match_funding,
)


def _w(refid: str, date: str, sats: int) -> Withdrawal:
    return Withdrawal(refid, datetime.date.fromisoformat(date), sats)


def test_exact_match_labels_chain_txid() -> None:
    result = match_funding(
        [_w("Q1", "2023-01-10", 100_000_000)],
        [("aaa", datetime.date(2023, 1, 11), 100_000_000)],
    )
    assert result.matches == {"aaa": "Kraken withdrawal Q1 (2023-01-10, 1 BTC)"}
    assert result.ambiguous == [] and result.unmatched == []


def test_outside_window_is_unmatched_not_guessed() -> None:
    result = match_funding(
        [_w("Q1", "2023-01-10", 100_000_000)],
        [("aaa", datetime.date(2023, 2, 10), 100_000_000)],
        window_days=3,
    )
    assert result.matches == {}
    assert result.unmatched == ["Q1 (1 BTC on 2023-01-10)"]


def test_multiple_candidates_are_ambiguous_not_guessed() -> None:
    result = match_funding(
        [_w("Q1", "2023-01-10", 50_000_000)],
        [
            ("aaa", datetime.date(2023, 1, 10), 50_000_000),
            ("bbb", datetime.date(2023, 1, 10), 50_000_000),
        ],
    )
    assert result.matches == {}
    assert result.unmatched == []
    assert len(result.ambiguous) == 1 and "2 candidates" in result.ambiguous[0]


def test_kraken_withdrawals_come_from_ledgers_fixture() -> None:
    from pathlib import Path

    ledgers = Path(__file__).parent / "fixtures" / "kraken_ledgers_2023.csv"
    withdrawals = kraken_btc_withdrawals(ledgers)
    assert withdrawals, "fixture must contain a BTC withdrawal leg"
    assert all(w.sats > 0 for w in withdrawals)


def test_funding_label_surfaces_in_provenance_evidence() -> None:

    from utxoproof.kyc import create_sample_graph
    from utxoproof.provenance import build_provenance_chain

    db = create_sample_graph()
    plain = build_provenance_chain("D", 0, db, lambda _d: Decimal("20000"))
    labeled = build_provenance_chain(
        "D", 0, db, lambda _d: Decimal("20000"), funding={"C": "Kraken withdrawal Q9"}
    )
    assert plain and labeled
    by_tx = {s.txid: s for s in labeled}
    assert by_tx["C"].source_evidence == "Kraken withdrawal Q9"
    assert "Kraken withdrawal Q9" not in {s.source_evidence for s in plain}


def test_truncation_flag_and_template_note(tmp_path) -> None:

    from utxoproof.kyc import create_sample_graph
    from utxoproof.reports import build_provenance_context, write_provenance_page

    db = create_sample_graph()
    ctx = build_provenance_context(
        db,
        "D",
        0,
        lambda _d: Decimal("20000"),
        Decimal("40000"),
        datetime.date(2024, 6, 1),
        max_depth=1,
    )
    assert ctx["truncated"] is True and ctx["max_depth"] == 1
    full = build_provenance_context(
        db,
        "D",
        0,
        lambda _d: Decimal("20000"),
        Decimal("40000"),
        datetime.date(2024, 6, 1),
    )
    assert full["truncated"] is False
    target = write_provenance_page(
        db,
        "D",
        0,
        lambda _d: Decimal("20000"),
        Decimal("40000"),
        datetime.date(2024, 6, 1),
        tmp_path,
        max_depth=1,
    )
    assert "truncated at 1 steps" in target.read_text(encoding="utf-8")


def test_funding_from_ledgers_empty_without_path() -> None:

    from utxoproof.kyc import create_sample_graph

    assert funding_from_ledgers(None, create_sample_graph()) == FundingResult(matches={})
