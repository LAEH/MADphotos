#!/usr/bin/env python3
"""
Generate static JSON data files for GitHub Pages deployment.

Runs the dashboard.py API functions and saves their output as static JSON
files into frontend/state/public/data/ so the React app can load them
without a backend.

Usage:
    python scripts/generate_static.py
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

OUTPUT_DIR = PROJECT_ROOT / "frontend" / "state" / "public" / "data"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from dashboard import (
        get_stats,
        get_journal_html,
        get_instructions_html,
        get_mosaics_data,
        get_cartoon_data,
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

    print(f"\nAll files written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
