"""onchain importer tests (mocked RPC, regtest-shaped payloads)."""

import httpx

from utxoproof.bitcoin_rpc import BitcoinRPC
from utxoproof.db import open_memory_db
from utxoproof.onchain import BitcoinCoreOnchainImporter

OUR_ADDR = "bcrt1qoursupposedchangeaddress000000000000000000"
EXT_ADDR = "bcrt1qexternalpaymentaddress0000000000000000000"

TX_COINBASE = {
    "txid": "aaa",
    "vin": [{"coinbase": "04ffff", "sequence": 0}],
    "vout": [
        {"value": 6.25, "n": 0, "scriptPubKey": {"address": OUR_ADDR}},
    ],
    "blockhash": "block1",
    "blocktime": 1700000000,
}

TX_SPEND = {
    "txid": "bbb",
    "vin": [{"txid": "aaa", "vout": 0, "sequence": 0}],
    "vout": [
        {"value": 1.0, "n": 0, "scriptPubKey": {"address": EXT_ADDR}},
        {"value": 5.2499, "n": 1, "scriptPubKey": {"address": OUR_ADDR}},
    ],
    "blockhash": "block2",
    "blocktime": 1700000600,
}


def _rpc() -> BitcoinRPC:
    raws = {"aaa": TX_COINBASE, "bbb": TX_SPEND}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        method = body["method"]
        if method == "listtransactions":
            return httpx.Response(
                200, json={"result": [{"txid": "aaa"}, {"txid": "bbb"}], "error": None}
            )
        if method == "getrawtransaction":
            return httpx.Response(200, json={"result": raws[body["params"][0]], "error": None})
        if method == "getblockheader":
            heights = {"block1": 101, "block2": 102}
            return httpx.Response(
                200, json={"result": {"height": heights[body["params"][0]]}, "error": None}
            )
        raise AssertionError(f"unexpected method {method}")

    return BitcoinRPC(
        "http://127.0.0.1:18443",
        "u",
        "p",
        client=httpx.Client(auth=httpx.BasicAuth("u", "p"), transport=httpx.MockTransport(handler)),
    )


def test_sync_stores_full_graph() -> None:
    db = open_memory_db()
    importer = BitcoinCoreOnchainImporter(_rpc(), db)
    summary = importer.sync("watch", known_addresses={OUR_ADDR})

    assert summary == {"txs_seen": 2, "new_txs": 2, "self_transfers": 1}
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone() == (2,)
    assert db.execute("SELECT COUNT(*) FROM tx_outputs").fetchone() == (3,)
    assert db.execute("SELECT COUNT(*) FROM tx_inputs").fetchone() == (1,)
    assert db.execute("SELECT is_coinbase FROM transactions WHERE txid='aaa'").fetchone() == (1,)
    assert db.execute("SELECT block_height FROM transactions WHERE txid='bbb'").fetchone() == (102,)
    assert db.execute(
        "SELECT value_sat FROM tx_outputs WHERE txid='bbb' AND vout=1"
    ).fetchone() == (524990000,)
    # spend linkage: coinbase output marked spent by bbb:0
    assert db.execute(
        "SELECT spent_by_txid, spent_by_input FROM tx_outputs WHERE txid='aaa'"
    ).fetchone() == ("bbb", 0)
    assert (
        db.execute("SELECT value FROM sync_state WHERE key='last_sync_at'").fetchone() is not None
    )


def test_sync_is_incremental() -> None:
    db = open_memory_db()
    importer = BitcoinCoreOnchainImporter(_rpc(), db)
    importer.sync("watch")
    summary = importer.sync("watch")
    assert summary == {"txs_seen": 2, "new_txs": 0, "self_transfers": 0}
