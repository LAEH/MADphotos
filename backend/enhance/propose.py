"""Iterative batch enhancement: generate ~30 proposals at a time,
learn from review history, and use acceptance rates to inform composition."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import BATCH_SIZE, DISPLAY_JPEG_DIR, ENHANCED_EXPOSURE_DIR, PREVIEW_DIR, PROJECT_ROOT
from .db import (
    cleanup_rejected_previews,
    ensure_tables,
    get_connection,
    get_learning_stats,
    get_proposed_uuids,
)
from .preview import render_combined, save_preview


def _load_picks() -> set[str]:
    """Load all picked photograph UUIDs."""
    picks_path = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "picks.json"
    if not picks_path.exists():
        return set()
    data = json.loads(picks_path.read_text())
    uuids = set()
    for key in ("portrait", "landscape"):
        val = data.get(key, [])
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    uuids.add(item)
                elif isinstance(item, dict) and "id" in item:
                    uuids.add(item["id"])
    return uuids


def _collect_signals(conn, picks: set[str]) -> dict[str, dict]:
    """Collect all enhancement signals per image. Only for picked photos."""
    signals: dict[str, dict] = {}

    # Border crops
    for r in conn.execute("""
        SELECT image_uuid, crop_top, crop_bottom, crop_left, crop_right, border_pct
        FROM border_crops WHERE has_border = 1
    """).fetchall():
        uuid = r["image_uuid"]
        if uuid not in picks:
            continue
        if uuid not in signals:
            signals[uuid] = {"transforms": []}
        signals[uuid]["transforms"].append("border_crop")
        signals[uuid]["border_crop"] = {
            "crop_top": r["crop_top"],
            "crop_bottom": r["crop_bottom"],
            "crop_left": r["crop_left"],
            "crop_right": r["crop_right"],
            "border_pct": r["border_pct"],
        }

    # Rotations
    for r in conn.execute("""
        SELECT image_uuid, should_rotate
        FROM gemini_analysis
        WHERE should_rotate IN ('cw90', 'ccw90', '180')
    """).fetchall():
        uuid = r["image_uuid"]
        if uuid not in picks:
            continue
        if uuid not in signals:
            signals[uuid] = {"transforms": []}
        signals[uuid]["transforms"].append("rotation")
        signals[uuid]["rotation"] = {"rotation": r["should_rotate"]}

    # Exposure enhancements
    if ENHANCED_EXPOSURE_DIR.exists():
        for jpg in ENHANCED_EXPOSURE_DIR.glob("*.jpg"):
            uuid = jpg.stem
            if uuid not in picks:
                continue
            if uuid not in signals:
                signals[uuid] = {"transforms": []}
            signals[uuid]["transforms"].append("exposure")
            exp_params: dict = {"source_path": str(jpg)}
            row = conn.execute(
                "SELECT gamma, shadow_lift FROM enhancement_plans WHERE image_uuid = ?",
                (uuid,),
            ).fetchone()
            if row:
                exp_params["gamma"] = row["gamma"]
                exp_params["shadow_lift"] = row["shadow_lift"]
            signals[uuid]["exposure"] = exp_params

    # Gemma crops (skip if border_crop already present — border_crop takes priority)
    for r in conn.execute("""
        SELECT uuid, crops FROM gemma_picks WHERE crops IS NOT NULL
    """).fetchall():
        uuid = r["uuid"]
        if uuid not in picks:
            continue
        if uuid not in signals:
            signals[uuid] = {"transforms": []}
        if "border_crop" in signals[uuid]["transforms"]:
            continue

        try:
            crops_data = json.loads(r["crops"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not crops_data:
            continue

        # Pick best crop ratio
        chosen_ratio = None
        chosen_crop = None
        for ratio in ["3:2", "2:3", "16:9"]:
            if ratio in crops_data:
                chosen_ratio = ratio
                chosen_crop = crops_data[ratio]
                break
        if not chosen_crop:
            chosen_ratio = next(iter(crops_data))
            chosen_crop = crops_data[chosen_ratio]

        signals[uuid]["transforms"].append("gemma_crop")
        signals[uuid]["gemma_crop"] = {
            "crop": {
                "ratio": chosen_ratio,
                "center_x": chosen_crop.get("center_x", 50),
                "center_y": chosen_crop.get("center_y", 50),
                "coverage": chosen_crop.get("coverage", 60),
            },
            "reason": chosen_crop.get("reason", ""),
        }

    return signals


def _primary_type(transforms: list[str]) -> str:
    """Pick the most significant transform as the display type."""
    priority = ["rotation", "border_crop", "exposure", "gemma_crop"]
    for t in priority:
        if t in transforms:
            return t
    return transforms[0] if transforms else "unknown"


def _plan_composition(
    candidates_by_type: dict[str, list[str]],
    learning: dict[str, dict],
    slots: int,
) -> dict[str, int]:
    """Allocate batch slots across types using acceptance rates.
    - Types with higher acceptance get more slots
    - Signal-based fixes (rotation, border_crop) get a floor of 2
    - Types with 0 history get a fair default share
    - Every type with candidates gets at least 1 slot"""
    types_with_candidates = {t for t, uuids in candidates_by_type.items() if uuids}
    if not types_with_candidates:
        return {}

    # Signal-based fixes always get a floor
    fix_types = {"rotation", "border_crop"}
    floor: dict[str, int] = {}
    for t in types_with_candidates:
        if t in fix_types:
            floor[t] = min(2, len(candidates_by_type[t]))
        else:
            floor[t] = 1

    floor_total = sum(floor.values())
    remaining = max(0, slots - floor_total)

    if remaining == 0:
        return floor

    # Weight by acceptance rate (default 0.5 for types with no history)
    weights: dict[str, float] = {}
    for t in types_with_candidates:
        if t in learning and (learning[t]["accepted"] + learning[t]["rejected"]) > 0:
            weights[t] = max(0.1, learning[t]["rate"])
        else:
            weights[t] = 0.5  # fair default

    total_weight = sum(weights.values())
    allocation = dict(floor)

    # Distribute remaining slots proportionally, then fill leftover round-robin
    if total_weight > 0:
        for t in types_with_candidates:
            extra = int(remaining * weights[t] / total_weight)
            allocation[t] = min(allocation.get(t, 0) + extra, len(candidates_by_type[t]))

    # Fill any remaining slots (from int truncation) round-robin by weight
    allocated = sum(allocation.values())
    leftover = slots - allocated
    if leftover > 0:
        ranked = sorted(types_with_candidates, key=lambda t: weights.get(t, 0), reverse=True)
        for t in ranked:
            if leftover <= 0:
                break
            headroom = len(candidates_by_type[t]) - allocation[t]
            add = min(leftover, headroom)
            allocation[t] += add
            leftover -= add

    return allocation


def generate_batch(batch_size: int = BATCH_SIZE) -> dict:
    """Generate a batch of ~batch_size proposals by randomly sampling from ALL picks.
    Photos with signals get enhancement proposals; photos without signals are skipped
    and replaced with another random pick until we fill the batch."""
    conn = get_connection()
    ensure_tables(conn)

    picks = _load_picks()
    if not picks:
        print("WARNING: No picks found in picks.json")
        conn.close()
        return {"batch_id": None, "created": 0, "composition": {}}

    # Collect all signals (fast DB reads)
    signals = _collect_signals(conn, picks)

    # Exclude already-proposed UUIDs
    proposed = get_proposed_uuids(conn)

    # Feedback items go first
    feedback_rows = conn.execute("""
        SELECT id, image_uuid, type, params_json, preview_path
        FROM enhance_proposals
        WHERE status = 'feedback' AND batch_id IS NULL
    """).fetchall()

    learning = get_learning_stats(conn)

    feedback_count = len(feedback_rows)
    new_slots = max(0, batch_size - feedback_count)

    # Build pool: all picks that haven't been proposed yet AND have signals
    pool = [u for u in picks if u not in proposed and u in signals]
    random.shuffle(pool)

    # Sample up to new_slots from the shuffled pool
    sampled: dict[str, dict] = {}
    for uuid in pool:
        if len(sampled) >= new_slots:
            break
        sampled[uuid] = signals[uuid]

    # Create batch
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO enhance_batches (created_at, status) VALUES (?, 'active')",
        (now,),
    )
    conn.commit()
    batch_id = cur.lastrowid

    # Assign feedback items to this batch
    for fb in feedback_rows:
        conn.execute(
            "UPDATE enhance_proposals SET batch_id = ? WHERE id = ?",
            (batch_id, fb["id"]),
        )

    # Render previews and create proposals
    created = 0
    errors = 0
    by_type: dict[str, int] = {}

    print(f"Batch {batch_id}: {feedback_count} feedback + {len(sampled)} new "
          f"(pool: {len(pool)} with signals, {len(picks)} total picks)")
    if learning:
        print("Learning stats:")
        for t, s in sorted(learning.items()):
            print(f"  {t}: {s['accepted']}A/{s['rejected']}R ({s['rate']:.0%})")

    for uuid, params in sampled.items():
        source = DISPLAY_JPEG_DIR / f"{uuid}.jpg"
        if not source.exists():
            continue

        transforms = params["transforms"]
        ptype = _primary_type(transforms)

        preview_path = PREVIEW_DIR / "combined" / f"{uuid}.jpg"
        try:
            img = render_combined(source, params)
            save_preview(img, preview_path)
        except Exception as e:
            print(f"  WARN: preview failed for {uuid} ({transforms}): {e}")
            errors += 1
            continue

        conn.execute(
            """INSERT INTO enhance_proposals
               (image_uuid, type, params_json, preview_path, batch_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (uuid, ptype, json.dumps(params),
             str(preview_path.relative_to(preview_path.parents[3])),
             batch_id, now),
        )
        created += 1
        by_type[ptype] = by_type.get(ptype, 0) + 1

    conn.commit()

    # Clean up rejected previews from past batches
    cleaned = cleanup_rejected_previews(conn)
    if cleaned:
        print(f"Cleaned up {cleaned} rejected preview files")

    conn.close()

    print(f"Created {created} proposals ({errors} errors), {feedback_count} feedback re-queued")
    for t, c in sorted(by_type.items()):
        print(f"  {t}: {c}")

    return {
        "batch_id": batch_id,
        "created": created,
        "feedback": feedback_count,
        "composition": by_type,
        "learning": {t: {"rate": s["rate"], "accepted": s["accepted"], "rejected": s["rejected"]}
                     for t, s in learning.items()},
    }


if __name__ == "__main__":
    generate_batch()
