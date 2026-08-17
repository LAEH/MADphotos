#!/bin/bash
# Auto-restarting wrapper for Gemma analysis.
# Restarts on crash with a 5s cooldown. Stops on Ctrl+C.
#
# Guarded: the whole while-loop runs under a single acquire so the restart
# logic can't spawn a second instance in parallel if the script is double-
# launched. A 27B VLM on Ollama + ThreadPool comfortably peaks near 14 GB.

SCRIPT="/Users/laeh/Github/MADphotos/backend/image_signals/run_gemma_analysis.py"
PYTHON="/Users/laeh/Github/MADphotos/.venv-gen/bin/python3"
WORKERS="${1:-3}"
LOG="/tmp/gemma_run.log"

source "$HOME/.claude/laeh-heavy-guard.sh"
LAEH_BUDGET_GB="${LAEH_BUDGET_GB:-14}"
cleanup_guard() { laeh_heavy_release $?; }
trap 'echo ""; echo "Stopped by user."; cleanup_guard; exit 0' INT TERM
trap 'cleanup_guard' EXIT
laeh_heavy_acquire "madphotos-gemma-forever" "MADphotos Gemma auto-restart" "$LAEH_BUDGET_GB" || exit $?

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
