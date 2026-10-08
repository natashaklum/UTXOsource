#!/usr/bin/env bash
# Repeatable refresh: full re-import (rewrite, not merge - fast for CSVs),
# recompute, rebuild reports. Idempotent: same inputs, same outputs.
# Shortfalls print but do not stop the run; review them each time.
#
#   bash ~/utxoproof-data/refresh.sh            # current year
#   TAX_YEAR=2023 bash ~/utxoproof-data/refresh.sh   # filing year
set -euo pipefail

# ---- edit these (or export overrides; same values as prepare.sh) --------
: "${DATA_DIR:=$HOME/utxoproof-data}"
: "${KRAKEN_LEDGERS:=$HOME/exports/kraken_ledgers.csv}"
: "${KRAKEN_TRADES:=}"   # e.g. "$HOME/exports/kraken_trades.csv"; empty skips the join
: "${TAX_YEAR:=$(date +%Y)}"
: "${BTC_PRICE:=}"
: "${CONFIG_FILE:=}"
: "${XPUB:=}"             # account xpub/ypub/zpub; empty skips on-chain stages
: "${FINGERPRINT:=}"     # master fingerprint, 8 hex; paired with XPUB
: "${RPC_URL:=http://127.0.0.1:8332}"  # bitcoind RPC URL
: "${RPC_USER:=}"
: "${RPC_PASSWORD:=}"
: "${WALLET:=utxoproof_watchonly}"
: "${PURPOSE:=84}"
: "${COIN:=0}"
: "${ACCOUNT:=0}"
: "${ENTITIES_FILE:=}"    # path to entities config (TOML); empty skips portfolio
# -------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/run-lib.sh"

export UTXOPROOF_DATA_DIR="$DATA_DIR"

stage_import
stage_check || true
stage_compute
stage_sync
stage_report
stage_status
stage_portfolio
stage_alltime
log "refresh done: $DATA_DIR"