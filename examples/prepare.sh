#!/usr/bin/env bash
# First run against a fresh data dir: converts everything, then STOPS for
# interrogation if coverage has shortfalls (new data should be questioned,
# not papered over). Copy next to your data dir and edit the variables.
#
#   cp examples/prepare.sh ~/utxoproof-data/prepare.sh
#   $EDITOR ~/utxoproof-data/prepare.sh   # set KRAKEN_LEDGERS etc.
#   bash ~/utxoproof-data/prepare.sh
set -euo pipefail

# ---- edit these (or export overrides) ------------------------------------
: "${DATA_DIR:=$HOME/utxoproof-data}"
: "${KRAKEN_LEDGERS:=$HOME/exports/kraken_ledgers.csv}"
: "${KRAKEN_TRADES:=}"   # e.g. "$HOME/exports/kraken_trades.csv"; empty skips the join
: "${TAX_YEAR:=2023}"
: "${BTC_PRICE:=}"            # empty = oracle yesterday-close for status
: "${CONFIG_FILE:=}"          # e.g. "$DATA_DIR/utxoproof.toml"
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
SHORTFALLS="$(stage_check | tail -n 1)"
echo "$SHORTFALLS"
case "$SHORTFALLS" in
    "shortfalls: 0") ;;
    *)
        fail "coverage has shortfalls - investigate with 'utxoproof check' before filing anything"
        ;;
esac
stage_compute
stage_sync
stage_report
stage_status
stage_portfolio
log "prepare done: $DATA_DIR"