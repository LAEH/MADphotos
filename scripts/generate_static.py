#!/usr/bin/env python3
"""
Generate static JSON data files for GitHub Pages deployment.

DEPRECATED: Superseded by backend.update_and_deploy.data — use:
    python3 -m backend.update_and_deploy.run --data

This script is kept for backward compatibility. It still works but the
deploy agent's data.py is the canonical version going forward.

Usage:
    python scripts/generate_static.py
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

OUTPUT_DIR = PROJECT_ROOT / "frontend" / "system" / "public" / "data"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from dashboard import (
        get_stats,
        get_journal_html,
        get_instructions_html,
        get_mosaics_data,
        get_cartoon_data,
        get_gemma_data,
        get_gemma_cartoon_data,
        get_all_cartoon_data,
        get_signal_inspector_picks_data,
    )

    # Stats
    stats = get_stats()
    (OUTPUT_DIR / "stats.json").write_text(json.dumps(stats, indent=None))
    print(f"  stats.json          ({len(json.dumps(stats)):,} bytes)")

    # Journal
    journal = {"html": get_journal_html()}
    (OUTPUT_DIR / "journal.json").write_text(json.dumps(journal, indent=None))
    print(f"  journal.json        ({len(json.dumps(journal)):,} bytes)")

    # Instructions
    instructions = {"html": get_instructions_html()}
    (OUTPUT_DIR / "instructions.json").write_text(json.dumps(instructions, indent=None))
    print(f"  instructions.json   ({len(json.dumps(instructions)):,} bytes)")

    # Mosaics
    mosaics = {"mosaics": get_mosaics_data()}
    (OUTPUT_DIR / "mosaics.json").write_text(json.dumps(mosaics, indent=None))
    print(f"  mosaics.json        ({len(json.dumps(mosaics)):,} bytes)")

    # Cartoon
    cartoon = {"pairs": get_cartoon_data()}
    (OUTPUT_DIR / "cartoon.json").write_text(json.dumps(cartoon, indent=None))
    print(f"  cartoon.json        ({len(json.dumps(cartoon)):,} bytes)")

    # Gemma
    gemma = get_gemma_data()
    (OUTPUT_DIR / "gemma.json").write_text(json.dumps(gemma, indent=None))
    print(f"  gemma.json          ({len(json.dumps(gemma)):,} bytes)")

    # Gemma Cartoon
    gemma_cartoon = {"pairs": get_gemma_cartoon_data()}
    (OUTPUT_DIR / "gemma_cartoon.json").write_text(json.dumps(gemma_cartoon, indent=None))
    print(f"  gemma_cartoon.json  ({len(json.dumps(gemma_cartoon)):,} bytes)")

    # All Cartoons (merged)
    cartoons = get_all_cartoon_data()
    (OUTPUT_DIR / "cartoons.json").write_text(json.dumps(cartoons, indent=None))
    print(f"  cartoons.json       ({len(json.dumps(cartoons)):,} bytes)")

    # Signal Inspector (picks)
    signal_inspector = get_signal_inspector_picks_data()
    (OUTPUT_DIR / "signal_inspector_picks.json").write_text(json.dumps(signal_inspector, indent=None))
    print(f"  signal_inspector_picks.json ({len(json.dumps(signal_inspector)):,} bytes)")

    print(f"\nAll files written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
