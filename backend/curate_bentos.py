#!/usr/bin/env python3
"""
curate_bentos.py — Generate pre-curated bento compositions at deploy time.

Ports curator logic from BentoView.tsx to Python, scores compositions by
visual impact, renders top 20 as PNGs, and exports metadata for the genie button.

Usage:
    python3 -m backend.curate_bentos              # generate top 20
    python3 -m backend.curate_bentos --count 10   # custom count
    python3 -m backend.curate_bentos --dry        # score without rendering
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from pathlib import Path
from typing import Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
OUTPUT_JSON = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "bento_compositions.json"

UNIT_RATIO = 4 / 3


# ── Layout definitions (matching BentoView.tsx) ──

def P(r, c, rs, cs):
    return {"r": r, "c": c, "rs": rs, "cs": cs, "orient": "P"}

def L(r, c, rs, cs):
    return {"r": r, "c": c, "rs": rs, "cs": cs, "orient": "L"}


DESKTOP_LAYOUTS = [
    {"id": "D1", "cols": 5, "rows": 4, "cells": [
        L(1,1,2,2), P(1,3,2,1), L(1,4,2,2), P(3,1,2,1), L(3,2,2,2), P(3,4,2,1), L(3,5,1,1), L(4,5,1,1),
    ]},
    {"id": "D2", "cols": 5, "rows": 4, "cells": [
        P(1,1,2,1), L(1,2,2,2), L(1,4,1,1), P(1,5,2,1), L(2,4,1,1),
        L(3,1,2,2), P(3,3,2,1), L(3,4,1,1), L(3,5,1,1), L(4,4,1,1), L(4,5,1,1),
    ]},
    {"id": "D4", "cols": 5, "rows": 4, "cells": [
        L(1,1,2,2), L(1,3,1,1), P(1,4,2,1), L(1,5,1,1), P(2,3,2,1), L(2,5,1,1),
        L(3,1,2,2), L(3,4,2,2), L(4,3,1,1),
    ]},
    {"id": "D5", "cols": 5, "rows": 4, "cells": [
        P(1,1,2,1), L(1,2,2,2), P(1,4,2,1), L(1,5,1,1), L(2,5,1,1),
        L(3,1,1,1), P(3,2,2,1), L(3,3,2,2), P(3,5,2,1), L(4,1,1,1),
    ]},
    {"id": "DS4", "cols": 2, "rows": 2, "cells": [L(1,1,1,1), L(1,2,1,1), L(2,1,1,1), L(2,2,1,1)]},
    {"id": "DS6p", "cols": 3, "rows": 2, "cells": [P(1,1,2,1), L(1,2,1,1), P(1,3,2,1), L(2,2,1,1)]},
]


# ── Photo data loading ──

def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def load_photos() -> list[dict]:
    """Load photo data needed for curation scoring."""
    conn = _get_conn()

    # Base images
    photos = {}
    for r in conn.execute(
        "SELECT uuid, width, height FROM images WHERE is_pick = 1"
    ).fetchall():
        w, h = r["width"], r["height"]
        orient = "portrait" if h > w else "landscape" if w > h else "square"
        photos[r["uuid"]] = {
            "id": r["uuid"],
            "w": w, "h": h,
            "orientation": orient,
        }

    # Aesthetic scores
    for r in conn.execute(
        "SELECT image_uuid, composite_score FROM aesthetic_scores_v2"
    ).fetchall():
        if r["image_uuid"] in photos:
            photos[r["image_uuid"]]["aesthetic"] = r["composite_score"]

    # Faces
    face_counts = {}
    for r in conn.execute(
        "SELECT image_uuid, COUNT(*) as cnt FROM face_detections GROUP BY image_uuid"
    ).fetchall():
        face_counts[r["image_uuid"]] = r["cnt"]
    for uid, cnt in face_counts.items():
        if uid in photos:
            photos[uid]["face_count"] = cnt

    # Dominant colors (first per image for hue)
    for r in conn.execute(
        "SELECT image_uuid, hex FROM dominant_colors WHERE percentage = ("
        "  SELECT MAX(percentage) FROM dominant_colors dc2 WHERE dc2.image_uuid = dominant_colors.image_uuid"
        ")"
    ).fetchall():
        uid = r["image_uuid"]
        if uid in photos and r["hex"]:
            photos[uid]["hex"] = r["hex"]

    # Image analysis (brightness, contrast)
    for r in conn.execute(
        "SELECT image_uuid, mean_brightness, dynamic_range FROM image_analysis"
    ).fetchall():
        uid = r["image_uuid"]
        if uid in photos:
            photos[uid]["brightness"] = r["mean_brightness"]
            photos[uid]["contrast"] = r["dynamic_range"]

    # Gemma analysis
    for r in conn.execute(
        "SELECT image_uuid, visual_weight, energy_direction, archetype, color_temp, "
        "print_worthy, crops FROM gemma_analysis"
    ).fetchall():
        uid = r["image_uuid"]
        if uid in photos:
            photos[uid]["gc_weight"] = r["visual_weight"]
            photos[uid]["gc_energy"] = r["energy_direction"]
            photos[uid]["gc_archetype"] = r["archetype"]
            photos[uid]["gc_temp"] = r["color_temp"]
            photos[uid]["print_worthy"] = bool(r["print_worthy"])
            try:
                photos[uid]["gemma_crops"] = json.loads(r["crops"]) if r["crops"] else None
            except (json.JSONDecodeError, TypeError):
                photos[uid]["gemma_crops"] = None

    # Saliency
    for r in conn.execute(
        "SELECT image_uuid, spread FROM saliency_maps"
    ).fetchall():
        uid = r["image_uuid"]
        if uid in photos:
            photos[uid]["saliency_spread"] = r["spread"]

    # Gemini vibes
    for r in conn.execute(
        "SELECT image_uuid, vibe FROM gemini_analysis"
    ).fetchall():
        uid = r["image_uuid"]
        if uid in photos and r["vibe"]:
            try:
                vibes = json.loads(r["vibe"]) if isinstance(r["vibe"], str) else r["vibe"]
                photos[uid]["vibes"] = vibes if isinstance(vibes, list) else []
            except (json.JSONDecodeError, TypeError):
                photos[uid]["vibes"] = []

    # Scene
    for r in conn.execute("SELECT image_uuid, scene_1 FROM scene_classification").fetchall():
        uid = r["image_uuid"]
        if uid in photos:
            photos[uid]["scene"] = r["scene_1"]

    # Time of day
    for r in conn.execute("SELECT image_uuid, time_of_day FROM gemini_analysis").fetchall():
        uid = r["image_uuid"]
        if uid in photos:
            photos[uid]["time"] = r["time_of_day"]

    # Style
    for r in conn.execute("SELECT image_uuid, style FROM style_classification").fetchall():
        uid = r["image_uuid"]
        if uid in photos:
            photos[uid]["style"] = r["style"]

    # Check display tier exists
    display_dir = PROJECT_ROOT / "images" / "rendered" / "display" / "jpeg"
    result = []
    for p in photos.values():
        if (display_dir / f"{p['id']}.jpg").exists():
            p["has_display"] = True
            # Compute hue from hex
            if "hex" in p:
                try:
                    hx = p["hex"].lstrip("#")
                    r_val, g, b = int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
                    import colorsys
                    h_val, _, _ = colorsys.rgb_to_hsv(r_val/255, g/255, b/255)
                    p["hue"] = h_val * 360
                    # Check if monochrome
                    p["mono"] = (max(r_val, g, b) - min(r_val, g, b)) < 30
                except Exception:
                    p["hue"] = 0
                    p["mono"] = False
            else:
                p["hue"] = 0
                p["mono"] = False
            result.append(p)

    conn.close()
    return result


# ── Scoring ──

def visual_impact(p: dict) -> float:
    """Port of visualImpact() from BentoView.tsx."""
    s = (p.get("aesthetic") or 5) * 1.5
    if (p.get("face_count") or 0) > 0:
        s += 4
    if (p.get("contrast") or 50) > 70:
        s += 2
    if p.get("saliency_spread") is not None and p["saliency_spread"] < 0.3:
        s += 2
    gc_w = p.get("gc_weight")
    if gc_w:
        s += (gc_w - 5) * 0.8
    if p.get("mono"):
        s += 1
    return s


def hue_dist(a: float, b: float) -> float:
    d = abs(a - b)
    return 360 - d if d > 180 else d


def crop_fitness(p: dict, cell: dict) -> float:
    crops = p.get("gemma_crops")
    if not crops:
        return 0
    ratio = (cell["cs"] * UNIT_RATIO) / cell["rs"]
    if ratio >= 1.6: key = "16:9"
    elif ratio >= 1.2: key = "3:2"
    elif ratio <= 0.85: key = "2:3"
    else: key = "1:1"
    crop = crops.get(key)
    if not crop:
        return 0
    return (crop.get("coverage", 50) - 50) * 0.06


def fill_cells(cells: list[dict], photos: list[dict], used: set, score_fn: Callable) -> list[dict]:
    """Port of fillCells() — heroes to large cells, supporters to small."""
    indexed = [(i, c, c["rs"] * c["cs"]) for i, c in enumerate(cells)]
    indexed.sort(key=lambda x: -x[2])

    pools = {
        "P": [p for p in photos if p["orientation"] == "portrait"],
        "L": [p for p in photos if p["orientation"] in ("landscape", "square")],
    }

    result = [None] * len(cells)

    for i, cell, _ in indexed:
        orient = cell.get("orient", "L")
        primary = pools.get(orient, pools["L"])
        fallback = pools["P"] if orient == "L" else pools["L"]

        best = None
        best_score = -math.inf
        for p in primary:
            if p["id"] in used:
                continue
            s = score_fn(p) + crop_fitness(p, cell)
            if s > best_score:
                best_score = s
                best = p
        if not best:
            for p in fallback:
                if p["id"] in used:
                    continue
                s = score_fn(p) + crop_fitness(p, cell)
                if s > best_score:
                    best_score = s
                    best = p
        if best:
            result[i] = best
            used.add(best["id"])

    return [p for p in result if p is not None]


# ── Curators ──

def curate_hero_story(photos: list[dict], cells: list[dict]) -> list[dict]:
    pool = [p for p in photos if p.get("has_display") and (p.get("aesthetic") or 0) > 4]
    if len(pool) < len(cells):
        return []
    scored = sorted(pool, key=lambda p: -visual_impact(p))
    top_n = max(5, len(scored) // 5)
    hero = random.choice(scored[:top_n])
    hero_hue = hero.get("hue", 0)
    hero_vibes = set(hero.get("vibes") or [])
    used = set()
    def score(p):
        if p["id"] == hero["id"]:
            return 999
        s = p.get("aesthetic") or 5
        shared = len(set(p.get("vibes") or []) & hero_vibes)
        s += shared * 4
        hd = hue_dist(p.get("hue", 0), hero_hue)
        if hd < 40: s += 5
        elif hd > 140: s += 3
        return s + random.random() * 2
    return fill_cells(cells, pool, used, score)


def curate_color_story(photos: list[dict], cells: list[dict]) -> list[dict]:
    pool = [p for p in photos if p.get("has_display") and not p.get("mono") and (p.get("aesthetic") or 0) > 4]
    if len(pool) < len(cells):
        return []
    buckets = [[] for _ in range(12)]
    for p in pool:
        idx = min(int((p.get("hue", 0)) / 30), 11)
        buckets[idx].append(p)
    best_start, best_count = 0, 0
    for i in range(12):
        cnt = len(buckets[i]) + len(buckets[(i+1) % 12]) + len(buckets[(i+2) % 12])
        if cnt > best_count:
            best_count = cnt
            best_start = i
    target_hue = (best_start * 30 + 45) % 360
    in_range = [p for p in pool if hue_dist(p.get("hue", 0), target_hue) < 45]
    if len(in_range) < len(cells):
        return []
    used = set()
    def score(p):
        s = visual_impact(p)
        s += (45 - hue_dist(p.get("hue", 0), target_hue)) / 4
        return s + random.random() * 2
    return fill_cells(cells, in_range, used, score)


def curate_print_worthy(photos: list[dict], cells: list[dict]) -> list[dict]:
    pool = [p for p in photos if p.get("has_display") and p.get("print_worthy") and (p.get("aesthetic") or 0) > 4]
    if len(pool) < len(cells):
        return []
    used = set()
    def score(p):
        s = visual_impact(p)
        gc_w = p.get("gc_weight")
        if gc_w and gc_w >= 8:
            s += 3
        return s + random.random() * 2
    return fill_cells(cells, pool, used, score)


def curate_mood_board(photos: list[dict], cells: list[dict]) -> list[dict]:
    pool = [p for p in photos if p.get("has_display") and p.get("vibes") and (p.get("aesthetic") or 0) > 4]
    if not pool:
        return []
    vibe_counts: dict[str, int] = {}
    for p in pool:
        for v in p.get("vibes", []):
            vibe_counts[v] = vibe_counts.get(v, 0) + 1
    good = [v for v, c in vibe_counts.items() if c >= len(cells) * 1.5]
    if not good:
        return []
    target = random.choice(good)
    matching = [p for p in pool if target in (p.get("vibes") or [])]
    used = set()
    def score(p):
        s = visual_impact(p)
        shared = sum(1 for v in (p.get("vibes") or []) if vibe_counts.get(v, 0) >= 5)
        s += shared * 3
        return s + random.random() * 2
    return fill_cells(cells, matching, used, score)


def curate_temperature_harmony(photos: list[dict], cells: list[dict]) -> list[dict]:
    pool = [p for p in photos if p.get("has_display") and (p.get("aesthetic") or 0) > 4]
    warm = [p for p in pool if p.get("gc_temp") in ("warm", "molten") or (not p.get("gc_temp") and (p.get("hue", 0) < 50 or p.get("hue", 0) > 310))]
    cool = [p for p in pool if p.get("gc_temp") in ("cool", "glacial") or (not p.get("gc_temp") and 160 < p.get("hue", 0) < 260)]
    chosen = warm if len(warm) >= len(cool) else cool
    temp = "warm" if chosen is warm else "cool"
    if len(chosen) < len(cells):
        return []
    target_hue = 30 if temp == "warm" else 210
    used = set()
    def score(p):
        s = visual_impact(p)
        s += (60 - hue_dist(p.get("hue", 0), target_hue)) / 6
        return s + random.random() * 2
    return fill_cells(cells, chosen, used, score)


def curate_default(photos: list[dict], cells: list[dict]) -> list[dict]:
    pool = [p for p in photos if p.get("has_display")]
    if not pool:
        return []
    sorted_pool = sorted(pool, key=lambda p: -visual_impact(p))[:500]
    used = set()
    seed = random.choice(sorted_pool)
    seed_hue = seed.get("hue", 0)
    def score(p):
        s = visual_impact(p)
        hd = hue_dist(seed_hue, p.get("hue", 0))
        if hd < 40: s += 4
        elif hd > 140: s += 2
        return s + random.random() * 2
    return fill_cells(cells, sorted_pool, used, score)


CURATORS = [
    ("hero_story", curate_hero_story),
    ("hero_story", curate_hero_story),
    ("color_story", curate_color_story),
    ("color_story", curate_color_story),
    ("print_worthy", curate_print_worthy),
    ("print_worthy", curate_print_worthy),
    ("mood_board", curate_mood_board),
    ("temperature_harmony", curate_temperature_harmony),
]


def generate_compositions(photos: list[dict], count: int = 20, dry: bool = False) -> list[dict]:
    """Try each curator x each layout, score by avg visual_impact, keep top N."""
    candidates = []

    for curator_name, curator_fn in CURATORS:
        for layout in DESKTOP_LAYOUTS:
            cells = layout["cells"]
            result = curator_fn(photos, cells)
            if len(result) < min(len(cells), 2):
                continue
            result = result[:len(cells)]
            avg_score = sum(visual_impact(p) for p in result) / len(result)
            candidates.append({
                "curator": curator_name,
                "layout": layout,
                "photos": result,
                "score": avg_score,
            })

    # Sort by score, deduplicate by photo set
    candidates.sort(key=lambda c: -c["score"])
    seen_sets: list[set] = []
    unique = []
    for c in candidates:
        photo_set = frozenset(p["id"] for p in c["photos"])
        # Skip if too similar to existing (>50% overlap)
        if any(len(photo_set & s) > len(photo_set) * 0.5 for s in seen_sets):
            continue
        seen_sets.append(set(photo_set))
        unique.append(c)
        if len(unique) >= count:
            break

    if not dry:
        from backend.render_bento import render_bento_png

        output_dir = PROJECT_ROOT / "images" / "rendered" / "bentos" / "curated"
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, comp in enumerate(unique):
            layout = comp["layout"]
            photo_ids = [p["id"] for p in comp["photos"]]
            result = render_bento_png(
                cols=layout["cols"],
                rows=layout["rows"],
                cells=layout["cells"],
                photo_ids=photo_ids,
                layout_id=f"curated_{layout['id']}",
            )
            if result:
                comp["rendered"] = {
                    "preview_url": result["preview_url"],
                    "png_url": result["url"],
                    "width": result["width"],
                    "height": result["height"],
                }
                print(f"  [{i+1}/{len(unique)}] {comp['curator']} × {layout['id']} — score {comp['score']:.1f}")
            else:
                print(f"  [{i+1}/{len(unique)}] FAILED {comp['curator']} × {layout['id']}")

    # Export metadata
    export = []
    for comp in unique:
        export.append({
            "curator": comp["curator"],
            "layout_id": comp["layout"]["id"],
            "cols": comp["layout"]["cols"],
            "rows": comp["layout"]["rows"],
            "cells": comp["layout"]["cells"],
            "photos": [p["id"] for p in comp["photos"]],
            "score": round(comp["score"], 2),
            "rendered": comp.get("rendered"),
        })

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(export, indent=2))
    print(f"\nExported {len(export)} compositions to {OUTPUT_JSON}")

    return export


def main():
    parser = argparse.ArgumentParser(description="Generate pre-curated bento compositions")
    parser.add_argument("--count", type=int, default=20, help="Number of compositions to generate")
    parser.add_argument("--dry", action="store_true", help="Score without rendering PNGs")
    args = parser.parse_args()

    print("Loading photo data...")
    photos = load_photos()
    print(f"Loaded {len(photos)} photos with display tier")

    print(f"\nGenerating top {args.count} compositions...")
    compositions = generate_compositions(photos, count=args.count, dry=args.dry)
    print(f"\nDone — {len(compositions)} compositions ready")


if __name__ == "__main__":
    main()
