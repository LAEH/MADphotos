"""Phase 6: Regenerate all System static JSON files.

Absorbs the logic from scripts/generate_static.py and scripts/deploy.py phase 3.
Imports directly from backend.api modules.
"""
from __future__ import annotations

import json
import shutil
import sys
from . import BACKEND, SYSTEM_DATA_DIR, SHOW_DATA_DIR

# Ensure backend is importable
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def generate_all(dry: bool = False) -> dict:
    """Generate all static JSON files for the System app."""
    if dry:
        print("  Would regenerate JSON files → frontend/system/public/data/")
        return {"files": [], "dry": True}

    from api import (
        get_stats,
        get_journal_html,
        get_instructions_html,
        get_mosaics_data,
        get_cartoon_data,
        get_gemma_data,
        get_gemma_cartoon_data,
        get_all_cartoon_data,
        get_signal_inspector_picks_data,
        get_qwen_data,
    )

    SYSTEM_DATA_DIR.mkdir(parents=True, exist_ok=True)

    files_spec = [
        ("stats.json", lambda: get_stats()),
        ("journal.json", lambda: {"html": get_journal_html()}),
        ("instructions.json", lambda: {"html": get_instructions_html()}),
        ("mosaics.json", lambda: {"mosaics": get_mosaics_data()}),
        ("cartoon.json", lambda: {"pairs": get_cartoon_data()}),
        ("gemma.json", lambda: get_gemma_data()),
        ("gemma_cartoon.json", lambda: {"pairs": get_gemma_cartoon_data()}),
        ("cartoons.json", lambda: get_all_cartoon_data()),
        ("signal_inspector_picks.json", lambda: get_signal_inspector_picks_data()),
        ("qwen.json", lambda: get_qwen_data()),
    ]

    results = []
    for name, fn in files_spec:
        try:
            data = fn()
            content = json.dumps(data, separators=(",", ":"))
            (SYSTEM_DATA_DIR / name).write_text(content)
            size = len(content)
            print(f"    {name:<35s} {size:>10,} bytes")
            results.append({"file": name, "size": size, "ok": True})
        except Exception as e:
            print(f"    {name}: FAILED — {e}")
            results.append({"file": name, "ok": False, "error": str(e)})

    # Copy stats.json → frontend/show/data/ for Show app
    src = SYSTEM_DATA_DIR / "stats.json"
    if src.exists() and SHOW_DATA_DIR.exists():
        shutil.copy2(str(src), str(SHOW_DATA_DIR / "stats.json"))
        print(f"    Copied stats.json → show/data/")

    return {"files": results, "dry": False}


def run(dry: bool = False) -> dict:
    """Entry point for data phase."""
    return generate_all(dry)
