-- utxoproof SQLite schema (plan Sec. 8). Single database, all mutable state.
-- Raw source imports stay as flat files; everything derived/queryable lives here.

-- ── Transaction graph ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS transactions (
    txid            TEXT PRIMARY KEY,
    block_height    INTEGER,
    block_time      TEXT NOT NULL,       -- ISO 8601
    eur_price_btc   TEXT,                -- Decimal string; NULL until populated
    is_coinbase     INTEGER NOT NULL DEFAULT 0
);

-- Every output ever created in a watched transaction.
-- Core UTXO table; spent outputs remain here with spent_by set.
CREATE TABLE IF NOT EXISTS tx_outputs (
    txid            TEXT NOT NULL,
    vout            INTEGER NOT NULL,
    address         TEXT,
    value_sat       INTEGER NOT NULL,
    eur_value       TEXT,                -- value_sat/1e8 * eur_price_btc
    -- KYC
    kyc_status      TEXT NOT NULL DEFAULT 'unknown',
                                         -- kyc|non_kyc|mixed|unknown
    kyc_fraction    TEXT NOT NULL DEFAULT '0',
                                         -- Decimal 0.0-1.0
    -- Source annotation (populated at import time)
    source_type     TEXT,                -- exchange_purchase|p2p_purchase|
                                         -- mining|self_transfer|received|unknown
    source_label    TEXT,
    source_evidence TEXT,
    -- Wallet
    wallet_label    TEXT,
    descriptor      TEXT,
    -- Spend tracking
    spent_by_txid   TEXT,                -- NULL = currently unspent
    spent_by_input  INTEGER,
    PRIMARY KEY (txid, vout)
);

-- Every input in a watched transaction.
CREATE TABLE IF NOT EXISTS tx_inputs (
    txid            TEXT NOT NULL,
    input_index     INTEGER NOT NULL,
    prev_txid       TEXT NOT NULL,
    prev_vout       INTEGER NOT NULL,
    PRIMARY KEY (txid, input_index)
);

-- ── Price cache ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS price_cache (
    date        TEXT NOT NULL,           -- 'YYYY-MM-DD'
    pair        TEXT NOT NULL,           -- 'BTC/EUR' | 'USD/EUR' etc.
    close_eur   TEXT NOT NULL,           -- Decimal string
    source      TEXT NOT NULL,           -- 'kraken'|'coingecko'|'ecb'
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (date, pair)
);

-- ── Sync state ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sync_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
-- Keys used:
--   'last_block_height'           -> last Bitcoin Core block processed
--   'last_sync_at'                -> ISO 8601 datetime of last sync
--   'last_import_{source}'        -> datetime of last import per source name

-- ── Source file manifest ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS source_manifest (
    id          INTEGER PRIMARY KEY,
    filename    TEXT NOT NULL,
    sha256      TEXT NOT NULL UNIQUE,    -- UNIQUE prevents duplicate imports
    size_bytes  INTEGER NOT NULL,
    role        TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

-- ── Advisory cache ─────────────────────────────────────────────────
-- Derived; can be recomputed at any time.

CREATE TABLE IF NOT EXISTS advisory_cache (
    txid                    TEXT NOT NULL,
    vout                    INTEGER NOT NULL,
    computed_at             TEXT NOT NULL,
    acquisition_cost_eur    TEXT,
    current_value_eur       TEXT,
    unrealized_gain_eur     TEXT,
    tax_if_sold_eur         TEXT,
    holding_days            INTEGER,
    kyc_status              TEXT,
    kyc_fraction            TEXT,
    speculation_tainted       INTEGER NOT NULL DEFAULT 0,
    estate_score            INTEGER NOT NULL DEFAULT 0,
    advisory_flag           TEXT,
    PRIMARY KEY (txid, vout)
);
