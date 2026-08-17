#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# OVERNIGHT QWEN PIPELINE
# ══════════════════════════════════════════════════════════════════════
#
# Phase 1: Qwen analysis on ALL remaining picks (~2,350 images, ~13h)
# Phase 2: Generate Imagen 3 variants from best Qwen prompts (~200 images, ~2h)
#
# Usage:
#   bash backend/image_signals/overnight_qwen.sh           # both phases
#   bash backend/image_signals/overnight_qwen.sh --phase1   # analysis only
#   bash backend/image_signals/overnight_qwen.sh --phase2   # variants only
#
# Budget: Phase 2 defaults to $10 (~250 variants)
# ══════════════════════════════════════════════════════════════════════

set -e
cd /Users/laeh/Github/MADphotos

# Shared heavy-job guard (persistent queue + RAM budget + runtime watchdog).
# Phase 1 loads Ollama Qwen 7B + 4 workers — peak ~10 GB. Phase 2 is API-only,
# trivially small. Use phase-1 budget.
source "$HOME/.claude/laeh-heavy-guard.sh"
LAEH_BUDGET_GB="${LAEH_BUDGET_GB:-10}"
trap 'laeh_heavy_release $?' EXIT
laeh_heavy_acquire "madphotos-overnight-qwen" "MADphotos overnight Qwen pipeline" "$LAEH_BUDGET_GB" || exit $?

PHASE1=true
PHASE2=true
BUDGET=20.0
VARIANT_STYLES=2

if [ "$1" = "--phase1" ]; then
    PHASE2=false
elif [ "$1" = "--phase2" ]; then
    PHASE1=false
fi

echo "╔══════════════════════════════════════════════════╗"
echo "║         OVERNIGHT QWEN PIPELINE                 ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Phase 1: Qwen analysis (all picks)   $PHASE1   ║"
echo "║  Phase 2: Imagen variants (\$$BUDGET)    $PHASE2   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Started: $(date)"
echo ""

# ── Phase 1: Qwen Analysis ──────────────────────────────────────────
if [ "$PHASE1" = true ]; then
    echo "═══ PHASE 1: Qwen Analysis (all remaining picks) ═══"
    echo ""

    # Check Ollama is running
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "ERROR: Ollama not running. Start it first: ollama serve"
        exit 1
    fi

    python3 -u backend/image_signals/run_qwen_analysis.py --workers 4 2>&1 | tee /tmp/qwen-overnight-analysis.log

    echo ""
    echo "Phase 1 complete: $(date)"
    echo ""
fi

# ── Phase 2: Imagen Variant Generation ──────────────────────────────
if [ "$PHASE2" = true ]; then
    echo "═══ PHASE 2: Imagen Variant Generation ═══"
    echo ""

    .venv-gen/bin/python3 -u backend/image_signals/generate_qwen_variants.py \
        --all --styles $VARIANT_STYLES --budget $BUDGET 2>&1 | tee /tmp/qwen-overnight-variants.log

    echo ""
    echo "Phase 2 complete: $(date)"
    echo ""
fi

echo "═══ ALL DONE ═══"
echo "Finished: $(date)"
echo ""
echo "Check results:"
echo "  Analysis:  sqlite3 images/mad_photos.db \"SELECT COUNT(*) FROM qwen_analysis\""
echo "  Variants:  sqlite3 images/mad_photos.db \"SELECT generation_status, COUNT(*) FROM ai_variants WHERE variant_type='qwen_variant' GROUP BY generation_status\""
echo "  Files:     ls -la backend/suggest_image_variant/output/qwen_*/"
