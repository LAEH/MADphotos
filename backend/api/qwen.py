"""Qwen 2.5 VL analysis data API."""
from __future__ import annotations

import json
import sqlite3

from ._common import DB_PATH, PROJECT_ROOT


def get_qwen_data():
    """Return Qwen analysis results from the qwen_analysis table."""
    conn = sqlite3.connect(str(DB_PATH))
    # Total picks
    picks_json = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
    try:
        picks = json.loads(picks_json.read_text())
        total = len(set(picks.get("portrait", []) + picks.get("landscape", [])))
    except Exception:
        total = 0

    # Orientation map for display
    orientation = {}
    try:
        picks = json.loads(picks_json.read_text())
        for u in picks.get("portrait", []):
            if "_" not in u:
                orientation[u] = "portrait"
        for u in picks.get("landscape", []):
            if "_" not in u:
                orientation.setdefault(u, "landscape")
    except Exception:
        pass

    results = []
    try:
        for row in conn.execute(
            "SELECT uuid, raw_json, processed_at FROM qwen_analysis "
            "WHERE raw_json IS NOT NULL ORDER BY processed_at DESC"
        ).fetchall():
            uuid, raw_json, processed_at = row
            try:
                qwen = json.loads(raw_json)
            except (json.JSONDecodeError, TypeError):
                qwen = {"raw": raw_json}

            results.append({
                "uuid": uuid,
                "qwen": qwen,
                "processed_at": processed_at or "",
                "orientation": orientation.get(uuid, "landscape"),
            })
    except Exception:
        pass
    conn.close()
    return {"total": total, "processed": len(results), "results": results}
