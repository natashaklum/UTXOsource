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
# -------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/run-lib.sh"

export UTXOPROOF_DATA_DIR="$DATA_DIR"

stage_import
CHECK_OUT="$(stage_check)"
echo "$CHECK_OUT"
SHORTFALLS="$(printf '%s\n' "$CHECK_OUT" | tail -n 1)"
case "$SHORTFALLS" in
    "shortfalls: 0") ;;
    *)
        fail "coverage has shortfalls - investigate with 'utxoproof check' before filing anything"
        ;;
esac
stage_compute
stage_report
stage_status
log "prepare done: $DATA_DIR"
