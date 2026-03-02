#!/bin/bash
# Enhanced Liquidation Analysis Loop
# Runs the full pipeline every 30 minutes with proper error handling and logging

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Rotate logs: keep last 5 log files
rotate_logs() {
    local count=$(ls -1 "$LOG_DIR"/loop_*.log 2>/dev/null | wc -l)
    if [ "$count" -gt 5 ]; then
        ls -1t "$LOG_DIR"/loop_*.log | tail -n +6 | xargs rm -f
    fi
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

LOOP_COUNT=0

log "=========================================="
log "Enhanced Liquidation Analysis Automation"
log "Project dir: $SCRIPT_DIR"
log "Loop interval: 30 minutes"
log "=========================================="

while true; do
    LOOP_COUNT=$((LOOP_COUNT + 1))
    LOOP_LOG="$LOG_DIR/loop_$(date '+%Y%m%d_%H%M%S').log"
    rotate_logs

    log "--- Loop #$LOOP_COUNT starting ---"

    # Activate venv
    source "$SCRIPT_DIR/env/bin/activate"
    cd "$SCRIPT_DIR"

    export BATCH_MODE=1
    export NO_BTC_CORRELATION=1

    # Step 1: Fetch latest trader data (timeout 20 min to prevent hangs)
    log "Step 1: Fetching top trader data..."
    timeout 1200 python data_collection/fetch_top_traders.py --timeout 15 2>&1 | tee -a "$LOOP_LOG"
    STEP1_EXIT=$?
    if [ $STEP1_EXIT -ne 0 ]; then
        log "WARNING: fetch_top_traders exited with code $STEP1_EXIT"
    fi

    sleep 5

    # Step 2: Run enhanced liquidation analysis
    log "Step 2: Running enhanced liquidation analysis..."
    timeout 900 python analysis/enhanced_liquidation_analysis.py --no-btc-correlation 2>&1 | tee -a "$LOOP_LOG"
    STEP2_EXIT=$?
    if [ $STEP2_EXIT -ne 0 ]; then
        log "WARNING: enhanced_liquidation_analysis exited with code $STEP2_EXIT"
    fi

    # Step 3: Cleanup old files (3+ days)
    log "Step 3: Cleaning up old files..."
    python helpers/cleanup_old_files.py 2>&1 | tee -a "$LOOP_LOG"

    # Step 3.5: Database cleanup (will fail gracefully if no postgres)
    log "Step 3.5: Running database cleanup..."
    python helpers/db_cleanup.py 2>&1 | tee -a "$LOOP_LOG"

    # Step 4: Collect best trade recommendations
    log "Step 4: Collecting best trade recommendations..."
    timeout 600 python trading/collect_best_trades.py 2>&1 | tee -a "$LOOP_LOG"
    STEP4_EXIT=$?
    if [ $STEP4_EXIT -ne 0 ]; then
        log "WARNING: collect_best_trades exited with code $STEP4_EXIT"
    fi

    # Summary
    log "--- Loop #$LOOP_COUNT complete ---"
    log "Log saved to: $LOOP_LOG"

    # Show BTC correlation results if available
    if [ -d "data/btc_correlation" ]; then
        log "BTC correlation files: $(ls data/btc_correlation 2>/dev/null | wc -l)"
    fi

    log "Sleeping 30 minutes until next run..."
    log "=========================================="

    sleep 1800
done
