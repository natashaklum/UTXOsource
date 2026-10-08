#!/usr/bin/env bash
# Shared stages for prepare.sh and refresh.sh. Source this file; do not run it.
# All settings arrive as environment variables with sane defaults so both
# pytest (offline fixtures) and real runs use the same code path.

set -euo pipefail

: "${UTXOPROOF_BIN:=utxoproof}"
: "${DATA_DIR:=$HOME/utxoproof-data}"
: "${KRAKEN_LEDGERS:=$HOME/exports/kraken_ledgers.csv}"
: "${KRAKEN_TRADES:=}"
: "${MANUAL:=$DATA_DIR/manual.csv}"
: "${TAX_YEAR:=$(date +%Y)}"
: "${BTC_PRICE:=}"
: "${CONFIG_FILE:=}"

log() { printf '==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

stage_import() {
    log "import: kraken ledgers -> manual CSV"
    [ -f "$KRAKEN_LEDGERS" ] || fail "ledgers file not found: $KRAKEN_LEDGERS"
    mkdir -p "$DATA_DIR"
    if [ -n "$KRAKEN_TRADES" ]; then
        [ -f "$KRAKEN_TRADES" ] || fail "trades file not found: $KRAKEN_TRADES"
        "$UTXOPROOF_BIN" import --file "$KRAKEN_LEDGERS" --type kraken \
            --trades "$KRAKEN_TRADES" --out "$MANUAL"
    else
        "$UTXOPROOF_BIN" import --file "$KRAKEN_LEDGERS" --type kraken \
            --out "$MANUAL"
    fi
    # Extension point: convert further sources and append their rows here.
    # Converted files share the manual columns, so concatenation is safe as
    # long as the combined file is re-sorted by date afterwards.
}

stage_check() {
    log "check: pool coverage (never crashes, shortfalls named)"
    "$UTXOPROOF_BIN" check --input "$MANUAL"
}

stage_compute() {
    log "compute: year $TAX_YEAR"
    "$UTXOPROOF_BIN" compute --input "$MANUAL" --year "$TAX_YEAR"
}

stage_report() {
    log "report: year $TAX_YEAR + evidence ZIP"
    if [ -n "$CONFIG_FILE" ]; then
        "$UTXOPROOF_BIN" report --input "$MANUAL" --year "$TAX_YEAR" \
            --config "$CONFIG_FILE" --source "$KRAKEN_LEDGERS" \
            ${KRAKEN_TRADES:+--source "$KRAKEN_TRADES"} \
            --out "$DATA_DIR/$TAX_YEAR"
    else
        "$UTXOPROOF_BIN" report --input "$MANUAL" --year "$TAX_YEAR" \
            --source "$KRAKEN_LEDGERS" \
            ${KRAKEN_TRADES:+--source "$KRAKEN_TRADES"} \
            --out "$DATA_DIR/$TAX_YEAR"
    fi
}

stage_status() {
    log "status: holdings snapshot"
    if [ -n "$BTC_PRICE" ]; then
        "$UTXOPROOF_BIN" status --input "$MANUAL" --price "$BTC_PRICE"
    else
        "$UTXOPROOF_BIN" status --input "$MANUAL" \
            --out "$DATA_DIR/current-status"
    fi
}

stage_alltime() {
    log "alltime: multi-year summary"
    "$UTXOPROOF_BIN" report --input "$MANUAL" --alltime \
        --out "$DATA_DIR/alltime"
}
