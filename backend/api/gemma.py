"""Gemma analysis data and progress API."""
from __future__ import annotations

import json
import sqlite3

from ._common import DB_PATH, PROJECT_ROOT


def get_gemma_data():
    """Return Gemma analysis results from the unified gemma_analysis table."""
    conn = sqlite3.connect(str(DB_PATH))
    # Total picks
    picks_json = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
    try:
        picks = json.loads(picks_json.read_text())
        total = len(set(picks.get("portrait", []) + picks.get("landscape", [])))
    except Exception:
        total = 0

    # Count complete v2 rows (have structured labels)
    try:
        complete_v2 = conn.execute(
            "SELECT COUNT(*) FROM gemma_analysis WHERE setting IS NOT NULL AND setting != ''"
        ).fetchone()[0]
    except Exception:
        complete_v2 = 0

    results = []
    try:
        for row in conn.execute(
            "SELECT uuid, raw_json, processed_at, setting FROM gemma_analysis "
            "WHERE raw_json IS NOT NULL ORDER BY processed_at DESC"
        ).fetchall():
            uuid, raw_json, processed_at, setting = row
            try:
                gemma = json.loads(raw_json)
            except (json.JSONDecodeError, TypeError):
                gemma = {"raw": raw_json}

            # Get camera info
            camera_data = conn.execute(
                "SELECT camera_body, film_stock, medium FROM images WHERE uuid = ?", (uuid,)
            ).fetchone()
            camera_body = camera_data[0] if camera_data and camera_data[0] else None
            film_stock = camera_data[1] if camera_data and camera_data[1] else None
            medium = camera_data[2] if camera_data and camera_data[2] else None

            # Get top 4 labels by confidence
            top_labels = []
            try:
                for label_row in conn.execute(
                    """SELECT label, category, confidence
                       FROM unified_labels
                       WHERE image_uuid = ?
                       ORDER BY confidence DESC
                       LIMIT 4""", (uuid,)
                ).fetchall():
                    top_labels.append({
                        "label": label_row[0],
                        "category": label_row[1],
                        "confidence": label_row[2]
                    })
            except Exception:
                pass

            results.append({
                "uuid": uuid,
                "gemma": gemma,
                "processed_at": processed_at or "",
                "camera_body": camera_body,
                "film_stock": film_stock,
                "medium": medium,
                "top_labels": top_labels,
                "complete": bool(setting),
            })
    except Exception:
        pass
    conn.close()
    return {"total": total, "processed": len(results), "complete_v2": complete_v2, "results": results}


def get_gemma_progress():
    """Return real-time Gemma processing progress."""
    conn = sqlite3.connect(str(DB_PATH))

    # Total picks to process
    picks_json = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
    try:
        picks = json.loads(picks_json.read_text())
        total = len(set(picks.get("portrait", []) + picks.get("landscape", [])))
    except Exception:
        total = 0

    # Count processed with new fields
    processed_count = 0
    legacy_count = 0
    has_crops = 0
    has_stories = 0
    has_cartoon = 0

    try:
        # Count total processed
        processed_count = conn.execute("SELECT COUNT(*) FROM gemma_picks").fetchone()[0]

        # Count new enhanced fields
        has_crops = conn.execute(
            "SELECT COUNT(*) FROM gemma_picks WHERE crop_x IS NOT NULL"
        ).fetchone()[0]

        has_stories = conn.execute(
            "SELECT COUNT(*) FROM gemma_picks WHERE story_silly IS NOT NULL AND story_silly != ''"
        ).fetchone()[0]

        has_cartoon = conn.execute(
            "SELECT COUNT(*) FROM gemma_picks WHERE cartoon_style IS NOT NULL AND cartoon_style != ''"
        ).fetchone()[0]

        legacy_count = processed_count - has_stories

        # Get most recent processing time for rate estimation
        recent = conn.execute(
            "SELECT processed_at FROM gemma_picks ORDER BY processed_at DESC LIMIT 10"
        ).fetchall()

    except Exception:
        pass

    conn.close()

    pending = max(0, total - processed_count)
    progress_pct = round((processed_count / total * 100) if total > 0 else 0, 1)

    return {
        "total": total,
        "processed": processed_count,
        "pending": pending,
        "progress_pct": progress_pct,
        "enhanced": {
            "with_crops": has_crops,
            "with_stories": has_stories,
            "with_cartoon": has_cartoon,
            "legacy_format": legacy_count
        }
    }
