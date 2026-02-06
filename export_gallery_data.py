#!/usr/bin/env python3
"""
export_gallery_data.py — Export analyzed photo data from SQLite to JSON for the web gallery.

Queries the database for all photos with Gemini analysis, extracts palette, vibes,
semantic pops, and precomputes drift connections (neighbors by shared vibes + color distance).

Usage:
    python3 export_gallery_data.py              # Export to web/data/photos.json
    python3 export_gallery_data.py --pretty     # Pretty-printed JSON
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mad_database as db

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "web" / "data" / "photos.json"

# How many drift neighbors per photo
DRIFT_NEIGHBORS = 6


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert '#RRGGBB' to (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def hex_to_hsl(hex_color: str) -> Tuple[float, float, float]:
    """Convert '#RRGGBB' to (h, s, l) where h is 0-360, s and l are 0-1."""
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return (h * 360, s, l)


def color_distance(hex1: str, hex2: str) -> float:
    """Simple Euclidean distance in RGB space."""
    r1, g1, b1 = hex_to_rgb(hex1)
    r2, g2, b2 = hex_to_rgb(hex2)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def palette_distance(palette1: List[str], palette2: List[str]) -> float:
    """Average minimum color distance between two palettes."""
    if not palette1 or not palette2:
        return 999.0
    total = 0.0
    for c1 in palette1:
        min_dist = min(color_distance(c1, c2) for c2 in palette2)
        total += min_dist
    return total / len(palette1)


def dominant_hue(palette: List[str]) -> float:
    """Return the hue of the most saturated color in the palette."""
    best_hue = 0.0
    best_sat = -1.0
    for hex_color in palette:
        h, s, l = hex_to_hsl(hex_color)
        if s > best_sat and 0.1 < l < 0.9:
            best_sat = s
            best_hue = h
    return best_hue


def parse_json_field(value: Optional[str]) -> Any:
    """Safely parse a JSON string field from the DB."""
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def compute_drift_connections(photos: List[Dict]) -> Dict[str, List[Dict]]:
    """Precompute top 6 neighbors for each photo by shared vibes, color proximity, and pops."""

    # Build indexes
    vibe_index = defaultdict(set)  # vibe -> set of photo ids
    pop_object_index = defaultdict(set)  # object -> set of photo ids
    setting_index = defaultdict(set)  # setting -> set of photo ids

    id_to_idx = {}
    for i, photo in enumerate(photos):
        pid = photo["id"]
        id_to_idx[pid] = i
        for vibe in photo.get("vibes", []):
            vibe_index[vibe.lower()].add(pid)
        for pop in photo.get("pops", []):
            obj = pop.get("object", "").lower()
            if obj:
                pop_object_index[obj].add(pid)
        setting = (photo.get("setting") or "").lower()
        if setting:
            setting_index[setting].add(pid)

    connections = {}

    for i, photo in enumerate(photos):
        pid = photo["id"]
        candidates = {}  # other_id -> {score, reasons}

        # Score by shared vibes
        for vibe in photo.get("vibes", []):
            for other_id in vibe_index.get(vibe.lower(), set()):
                if other_id == pid:
                    continue
                if other_id not in candidates:
                    candidates[other_id] = {"score": 0, "reasons": []}
                candidates[other_id]["score"] += 3
                reason = "both " + vibe.lower()
                if reason not in candidates[other_id]["reasons"]:
                    candidates[other_id]["reasons"].append(reason)

        # Score by color similarity
        my_palette = photo.get("palette", [])
        if my_palette:
            for j, other in enumerate(photos):
                if i == j:
                    continue
                other_palette = other.get("palette", [])
                if not other_palette:
                    continue
                dist = palette_distance(my_palette, other_palette)
                if dist < 80:
                    oid = other["id"]
                    if oid not in candidates:
                        candidates[oid] = {"score": 0, "reasons": []}
                    color_score = max(0, 5 - dist / 20)
                    candidates[oid]["score"] += color_score
                    if "similar palette" not in candidates[oid]["reasons"]:
                        candidates[oid]["reasons"].append("similar palette")

        # Score by shared semantic pop objects
        for pop in photo.get("pops", []):
            obj = pop.get("object", "").lower()
            if not obj:
                continue
            for other_id in pop_object_index.get(obj, set()):
                if other_id == pid:
                    continue
                if other_id not in candidates:
                    candidates[other_id] = {"score": 0, "reasons": []}
                candidates[other_id]["score"] += 4
                reason = "both have " + pop.get("object", obj)
                if reason not in candidates[other_id]["reasons"]:
                    candidates[other_id]["reasons"].append(reason)

        # Score by same setting
        setting = (photo.get("setting") or "").lower()
        if setting:
            for other_id in setting_index.get(setting, set()):
                if other_id == pid:
                    continue
                if other_id not in candidates:
                    candidates[other_id] = {"score": 0, "reasons": []}
                candidates[other_id]["score"] += 1
                reason = "both " + photo.get("setting", setting)
                if reason not in candidates[other_id]["reasons"]:
                    candidates[other_id]["reasons"].append(reason)

        # Sort by score descending, take top N
        ranked = sorted(candidates.items(), key=lambda x: x[1]["score"], reverse=True)
        top = []
        for other_id, info in ranked[:DRIFT_NEIGHBORS]:
            top.append({
                "id": other_id,
                "reason": info["reasons"][0] if info["reasons"] else "related",
            })
        connections[pid] = top

    return connections


def export(pretty: bool = False) -> None:
    conn = db.get_connection()

    # Query all analyzed photos with their image data
    rows = conn.execute("""
        SELECT
            i.uuid, i.category, i.subcategory, i.filename,
            i.width, i.height, i.aspect_ratio, i.orientation,
            g.color_palette, g.semantic_pops, g.grading_style,
            g.time_of_day, g.setting, g.weather,
            g.vibe, g.alt_text, g.exposure, g.depth,
            g.composition_technique, g.geometry, g.faces_count
        FROM images i
        JOIN gemini_analysis g ON i.uuid = g.image_uuid
        WHERE g.raw_json IS NOT NULL AND g.raw_json != ''
          AND g.error IS NULL
        ORDER BY i.uuid
    """).fetchall()

    # Build tier lookup: uuid -> {tier_name: {format: local_path}}
    tier_rows = conn.execute("""
        SELECT t.image_uuid, t.tier_name, t.format, t.local_path
        FROM tiers t
        WHERE t.variant_id IS NULL
          AND t.tier_name IN ('thumb', 'micro', 'display', 'mobile')
    """).fetchall()

    tier_lookup = defaultdict(lambda: defaultdict(dict))
    for t in tier_rows:
        tier_lookup[t["image_uuid"]][t["tier_name"]][t["format"]] = t["local_path"]

    photos = []
    all_vibes = set()
    all_gradings = set()
    all_settings = set()
    all_times = set()

    for row in rows:
        uuid = row["uuid"]
        palette = parse_json_field(row["color_palette"]) or []
        pops = parse_json_field(row["semantic_pops"]) or []
        vibes = parse_json_field(row["vibe"]) or []
        geometry = parse_json_field(row["geometry"]) or []

        # Build image paths from tier lookup
        tiers = tier_lookup.get(uuid, {})

        # Prefer webp, fallback to jpeg
        def tier_path(tier_name: str) -> Optional[str]:
            t = tiers.get(tier_name, {})
            path = t.get("webp") or t.get("jpeg")
            if not path:
                return None
            # Convert absolute path to relative URL for the server
            # /Users/.../MADphotos/rendered/thumb/jpeg/uuid.jpg -> /rendered/thumb/jpeg/uuid.jpg
            base = str(BASE_DIR)
            if path.startswith(base):
                return path[len(base):]
            return path

        photo = {
            "id": uuid,
            "category": row["category"],
            "subcategory": row["subcategory"],
            "filename": row["filename"],
            "w": row["width"],
            "h": row["height"],
            "aspect": round(row["aspect_ratio"], 3),
            "orientation": row["orientation"],
            "palette": palette[:5],
            "pops": pops,
            "grading": row["grading_style"] or "",
            "time": row["time_of_day"] or "",
            "setting": row["setting"] or "",
            "weather": row["weather"] or "",
            "vibes": vibes,
            "alt": row["alt_text"] or "",
            "exposure": row["exposure"] or "",
            "depth": row["depth"] or "",
            "composition": row["composition_technique"] or "",
            "geometry": geometry,
            "faces": row["faces_count"] or 0,
            "hue": round(dominant_hue(palette[:5]), 1) if palette else 0,
            "thumb": tier_path("thumb"),
            "micro": tier_path("micro"),
            "display": tier_path("display"),
            "mobile": tier_path("mobile"),
        }
        photos.append(photo)

        for v in vibes:
            all_vibes.add(v)
        if row["grading_style"]:
            all_gradings.add(row["grading_style"])
        if row["setting"]:
            all_settings.add(row["setting"])
        if row["time_of_day"]:
            all_times.add(row["time_of_day"])

    conn.close()

    print(f"Exported {len(photos)} photos")
    print(f"  Vibes: {len(all_vibes)} unique")
    print(f"  Gradings: {sorted(all_gradings)}")
    print(f"  Settings: {sorted(all_settings)}")
    print(f"  Times: {sorted(all_times)}")

    # Precompute drift connections
    print("Computing drift connections...")
    drift = compute_drift_connections(photos)

    output = {
        "count": len(photos),
        "vibes": sorted(all_vibes),
        "gradings": sorted(all_gradings),
        "settings": sorted(all_settings),
        "times": sorted(all_times),
        "photos": photos,
        "drift": drift,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        if pretty:
            json.dump(output, f, indent=2)
        else:
            json.dump(output, f, separators=(",", ":"))

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Written to {OUTPUT_PATH} ({size_kb:.0f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export gallery data to JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()
    export(pretty=args.pretty)


if __name__ == "__main__":
    main()
