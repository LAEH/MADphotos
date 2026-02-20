#!/bin/bash
# Auto-restarting wrapper for Gemma analysis.
# Restarts on crash with a 5s cooldown. Stops on Ctrl+C.

SCRIPT="/Users/laeh/Github/MADphotos/backend/signals/run_gemma_analysis.py"
PYTHON="/Users/laeh/Github/MADphotos/.venv-gen/bin/python3"
WORKERS="${1:-3}"
LOG="/tmp/gemma_run.log"

trap 'echo ""; echo "Stopped by user."; exit 0' INT TERM

RUN=0
while true; do
    RUN=$((RUN + 1))
    echo ""
    echo "━━━ Run #${RUN} | $(date '+%H:%M:%S') | workers=${WORKERS} ━━━"
    echo ""

    $PYTHON -u "$SCRIPT" --workers "$WORKERS" 2>&1 | tee -a "$LOG"
    EXIT=$?

    if [ $EXIT -eq 0 ]; then
        echo ""
        echo "✓ Completed successfully."
        break
    fi

    echo ""
    echo "✗ Crashed (exit $EXIT). Restarting in 5s..."
    sleep 5
done
