"""On-chain importer skeleton (plan Sec. 9, Sprint 3 start).

Stores the full watched tx graph (transactions, tx_inputs, tx_outputs) in the
Sec. 8 SQLite schema. Covered: watch-only wallet setup, descriptor import,
incremental sync from `listtransactions` with `getrawtransaction` resolution,
spend linkage, self-transfer counting. Explicitly pending (full Sprint 3):
block-height backfill tracking, rescan orchestration, BIP329 labels.
"""

from __future__ import annotations

import datetime
import sqlite3
from decimal import Decimal
from typing import Any

from utxoproof.bitcoin_rpc import BitcoinRPC, BitcoinRPCError

SAT_PER_BTC = 100_000_000


def _btc_to_sat(value: float | str) -> int:
    return int(Decimal(str(value)) * SAT_PER_BTC)


def _iso(ts: float | int) -> str:
    return datetime.datetime.fromtimestamp(int(ts), datetime.UTC).isoformat()


class BitcoinCoreOnchainImporter:
    def __init__(self, rpc: BitcoinRPC, db: sqlite3.Connection) -> None:
        self._rpc = rpc
        self._db = db
        self._height_cache: dict[str, int] = {}

    # -- setup -----------------------------------------------------------

    def setup_wallet(self, wallet_name: str) -> None:
        """Create a blank watch-only wallet; tolerate an existing one."""
        try:
            self._rpc.create_wallet(wallet_name, disable_private_keys=True, blank=True)
        except BitcoinRPCError as exc:
            if "already exists" not in str(exc):
                raise

    def import_descriptor(self, wallet: str, descriptor: str, timestamp: int | str) -> None:
        """Import one ranged descriptor without rescan orchestration (Sprint 3)."""
        self._rpc.import_descriptors(
            wallet,
            [{"desc": descriptor, "timestamp": timestamp, "range": [0, 1000], "active": False}],
        )

    # -- sync ------------------------------------------------------------

    def sync(self, wallet: str, known_addresses: set[str] | None = None) -> dict[str, int]:
        """Import all wallet transactions not yet in the DB. Returns a summary."""
        seen = {row[0] for row in self._db.execute("SELECT txid FROM transactions").fetchall()}
        summary = {"txs_seen": 0, "new_txs": 0, "self_transfers": 0}
        for entry in self._rpc.list_transactions(wallet):
            summary["txs_seen"] += 1
            txid = str(entry["txid"])
            if txid in seen:
                continue
            raw = self._rpc.get_raw_transaction(txid)
            self_transfer = self._store_tx(raw, known_addresses)
            summary["new_txs"] += 1
            summary["self_transfers"] += int(self_transfer)
            seen.add(txid)
        self._db.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES (?,?,?)",
            (
                "last_sync_at",
                datetime.datetime.now(datetime.UTC).isoformat(),
                datetime.datetime.now(datetime.UTC).isoformat(),
            ),
        )
        self._db.commit()
        return summary

    # -- storage ----------------------------------------------------------

    def _block_height(self, blockhash: str | None) -> int | None:
        if not blockhash:
            return None
        if blockhash not in self._height_cache:
            header = self._rpc.call("getblockheader", blockhash)
            self._height_cache[blockhash] = int(header["height"])
        return self._height_cache[blockhash]

    def _store_tx(self, raw: dict[str, Any], known_addresses: set[str] | None) -> bool:
        txid = str(raw["txid"])
        is_coinbase = any("coinbase" in vin for vin in raw.get("vin", []))
        block_time = raw.get("blocktime", raw.get("time", 0))
        self._db.execute(
            "INSERT OR IGNORE INTO transactions "
            "(txid, block_height, block_time, is_coinbase) VALUES (?,?,?,?)",
            (txid, self._block_height(raw.get("blockhash")), _iso(block_time), int(is_coinbase)),
        )
        for index, vin in enumerate(raw.get("vin", [])):
            if "coinbase" in vin:
                continue
            self._db.execute(
                "INSERT OR IGNORE INTO tx_inputs "
                "(txid, input_index, prev_txid, prev_vout) VALUES (?,?,?,?)",
                (txid, index, str(vin["txid"]), int(vin["vout"])),
            )
            self._db.execute(
                "UPDATE tx_outputs SET spent_by_txid=?, spent_by_input=? WHERE txid=? AND vout=?",
                (txid, index, str(vin["txid"]), int(vin["vout"])),
            )
        addresses: list[str | None] = []
        for vout in raw.get("vout", []):
            address = vout.get("scriptPubKey", {}).get("address")
            addresses.append(address)
            self._db.execute(
                "INSERT OR IGNORE INTO tx_outputs (txid, vout, address, value_sat) "
                "VALUES (?,?,?,?)",
                (txid, int(vout["n"]), address, _btc_to_sat(vout["value"])),
            )
        self._db.commit()
        if known_addresses is None or not addresses:
            return False
        return all(addr in known_addresses for addr in addresses)
