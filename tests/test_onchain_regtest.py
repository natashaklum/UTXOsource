"""Regtest end-to-end: real bitcoind, real descriptor import, real sync.

Requires a regtest node (CI `regtest` job starts one; locally: see
`docker-compose.regtest.yml`). Skips when no node answers. Never runs on
mainnet: refuses any URL that is not regtest localhost.
"""

import os

import pytest
from embit import bip32

from utxoproof.bitcoin_rpc import BitcoinRPC, BitcoinRPCError
from utxoproof.db import open_memory_db
from utxoproof.descriptors import derive_addresses
from utxoproof.onchain import BitcoinCoreOnchainImporter

pytestmark = pytest.mark.regtest

# BIP84 test-vector account key, re-serialized with testnet version bytes:
# regtest Core rejects mainnet xpub/zpub in importdescriptors.
_MAINNET_ZPUB = (
    "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVCTo"
    "UG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs"
)
TPUB_VERSION = b"\x04\x35\x87\xcf"
REGTEST_XPUB = bip32.HDKey.from_base58(_MAINNET_ZPUB).to_base58(version=TPUB_VERSION)


def _node() -> BitcoinRPC:
    url = os.environ.get("UTXOPROOF_REGTEST_URL", "http://127.0.0.1:18443")
    if "18443" not in url and "regtest" not in url:
        pytest.fail("refusing to run regtest test against a non-regtest URL")
    rpc = BitcoinRPC(
        url,
        os.environ.get("UTXOPROOF_REGTEST_USER", "utxoproof"),
        os.environ.get("UTXOPROOF_REGTEST_PASSWORD", "utxoproof-test"),
    )
    try:
        rpc.get_block_count()
    except BitcoinRPCError:
        pytest.skip("no regtest node available")
    return rpc


def _ensure_wallet(rpc: BitcoinRPC, name: str, watch_only: bool) -> None:
    try:
        rpc.create_wallet(name, disable_private_keys=watch_only, blank=watch_only)
    except BitcoinRPCError as exc:
        if "already exists" not in str(exc):
            raise


def test_regtest_descriptor_sync() -> None:
    rpc = _node()
    watch = "utxoproof_regtest"
    miner_wallet = "miner"
    _ensure_wallet(rpc, watch, watch_only=True)
    _ensure_wallet(rpc, miner_wallet, watch_only=False)

    # Import first (timestamp 0 rescans the tiny regtest chain; mirrors real
    # `setup` -> fund -> `sync` ordering with no rescan gap).
    recv = derive_addresses(REGTEST_XPUB, 0, 0, 1, network="regtest")[0]
    assert recv.startswith("bcrt1")
    db = open_memory_db()
    importer = BitcoinCoreOnchainImporter(rpc, db)
    importer.import_descriptor(watch, f"wpkh([00000000/84h/1h/0h]{REGTEST_XPUB}/0/*)", 0)

    miner = rpc.get_new_address(miner_wallet)
    rpc.generate_to_address(101, miner)
    txid = rpc.send_to_address(miner_wallet, recv, 1.25)
    assert isinstance(txid, str) and len(txid) == 64
    rpc.generate_to_address(1, miner)

    summary = importer.sync(watch)
    assert summary["new_txs"] >= 1
    rows = db.execute("SELECT value_sat FROM tx_outputs WHERE address=?", (recv,)).fetchall()
    assert rows and rows[0][0] == 125_000_000
