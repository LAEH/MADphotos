#!/usr/bin/env python3
"""
export_gallery_data.py — Export ALL 9,011 photos with full signals to JSON for Show.

Queries every signal table in the database, merges into rich photo objects,
and precomputes auxiliary data files for specific experiences.

Outputs:
    web/data/photos.json           — Core data: all photos + similarity connections
    web/data/faces.json            — Face crops + emotions for Les Visages
    web/data/game_rounds.json      — Precomputed game rounds for Le Terrain de Jeu
    web/data/stream_sequence.json  — Curated visual flow order for Le Flot

Usage:
    python3 export_gallery_data.py              # Export all
    python3 export_gallery_data.py --pretty     # Pretty-printed JSON
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mad_database as db

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "web" / "data"
OUTPUT_PATH = DATA_DIR / "photos.json"

SIMILARITY_NEIGHBORS = 6
GAME_ROUNDS = 200
STREAM_BREATHER_INTERVAL = 10


# ── Color Utilities ──────────────────────────────────────────────────────────

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def hex_to_hsl(hex_color: str) -> Tuple[float, float, float]:
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return (h * 360, s, l)


def color_distance(hex1: str, hex2: str) -> float:
    r1, g1, b1 = hex_to_rgb(hex1)
    r2, g2, b2 = hex_to_rgb(hex2)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def palette_distance(p1: List[str], p2: List[str]) -> float:
    if not p1 or not p2:
        return 999.0
    total = 0.0
    for c1 in p1:
        total += min(color_distance(c1, c2) for c2 in p2)
    return total / len(p1)


def dominant_hue_from_palette(palette: List[str]) -> float:
    best_hue = 0.0
    best_sat = -1.0
    for hex_color in palette:
        h, s, l = hex_to_hsl(hex_color)
        if s > best_sat and 0.1 < l < 0.9:
            best_sat = s
            best_hue = h
    return best_hue


def parse_json_field(value: Optional[str]) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


# ── Data Loaders ─────────────────────────────────────────────────────────────

def load_images(conn: Any) -> List[Dict]:
    """All 9,011 images."""
    return conn.execute("""
        SELECT uuid, category, subcategory, filename,
               width, height, aspect_ratio, orientation,
               camera_body, medium, is_monochrome
        FROM images
        ORDER BY uuid
    """).fetchall()


def load_gemini(conn: Any) -> Dict[str, Dict]:
    """Gemini analysis keyed by uuid."""
    rows = conn.execute("""
        SELECT image_uuid, color_palette, semantic_pops, grading_style,
               time_of_day, setting, weather, vibe, alt_text,
               exposure, depth, composition_technique, geometry, faces_count
        FROM gemini_analysis
        WHERE raw_json IS NOT NULL AND raw_json != '' AND error IS NULL
    """).fetchall()
    return {r["image_uuid"]: dict(r) for r in rows}


def load_colors(conn: Any) -> Dict[str, List[str]]:
    """Top 5 dominant colors (hex) per image, ordered by percentage."""
    rows = conn.execute("""
        SELECT image_uuid, hex
        FROM dominant_colors
        ORDER BY image_uuid, percentage DESC
    """).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[str]]
    for r in rows:
        if len(result[r["image_uuid"]]) < 5:
            result[r["image_uuid"]].append(r["hex"])
    return dict(result)


def load_aesthetics(conn: Any) -> Dict[str, float]:
    rows = conn.execute("SELECT image_uuid, score FROM aesthetic_scores").fetchall()
    return {r["image_uuid"]: round(r["score"], 1) for r in rows}


def load_depth(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, depth_complexity, near_pct, mid_pct, far_pct
        FROM depth_estimation
    """).fetchall()
    return {r["image_uuid"]: {
        "complexity": round(r["depth_complexity"] or 0, 1),
        "near": round(r["near_pct"] or 0, 1),
        "mid": round(r["mid_pct"] or 0, 1),
        "far": round(r["far_pct"] or 0, 1),
    } for r in rows}


def load_scenes(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, scene_1, score_1, environment
        FROM scene_classification
    """).fetchall()
    return {r["image_uuid"]: {
        "scene": r["scene_1"] or "",
        "score": round(r["score_1"] or 0, 2),
        "env": r["environment"] or "",
    } for r in rows}


def load_styles(conn: Any) -> Dict[str, str]:
    rows = conn.execute("SELECT image_uuid, style FROM style_classification").fetchall()
    return {r["image_uuid"]: r["style"] for r in rows}


def load_captions(conn: Any) -> Dict[str, str]:
    rows = conn.execute("SELECT image_uuid, caption FROM image_captions").fetchall()
    return {r["image_uuid"]: r["caption"] for r in rows}


def load_pixel(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, mean_brightness, contrast_ratio, noise_estimate,
               dominant_hue, is_low_key, is_high_key
        FROM image_analysis
    """).fetchall()
    return {r["image_uuid"]: {
        "brightness": round(r["mean_brightness"] or 0, 1),
        "contrast": round(r["contrast_ratio"] or 0, 1),
        "noise": round(r["noise_estimate"] or 0, 2),
        "pixel_hue": r["dominant_hue"] or 0,
        "low_key": bool(r["is_low_key"]),
        "high_key": bool(r["is_high_key"]),
    } for r in rows}


def load_faces(conn: Any) -> Dict[str, List[Dict]]:
    """Face detections grouped by image."""
    rows = conn.execute("""
        SELECT image_uuid, face_index, x, y, w, h, confidence, face_area_pct
        FROM face_detections
        ORDER BY image_uuid, face_index
    """).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[Dict]]
    for r in rows:
        result[r["image_uuid"]].append({
            "fi": r["face_index"],
            "x": round(r["x"], 3),
            "y": round(r["y"], 3),
            "w": round(r["w"], 3),
            "h": round(r["h"], 3),
            "conf": round(r["confidence"] or 0, 2),
            "area": round(r["face_area_pct"] or 0, 4),
        })
    return dict(result)


def load_emotions(conn: Any) -> Dict[str, List[Dict]]:
    """Facial emotions grouped by image."""
    rows = conn.execute("""
        SELECT image_uuid, face_index, dominant_emotion, confidence
        FROM facial_emotions
        ORDER BY image_uuid, face_index
    """).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[Dict]]
    for r in rows:
        result[r["image_uuid"]].append({
            "fi": r["face_index"],
            "emo": r["dominant_emotion"] or "",
            "conf": round(r["confidence"] or 0, 2),
        })
    return dict(result)


def load_objects(conn: Any) -> Dict[str, List[Dict]]:
    """Object detections grouped by image (top 10 per image)."""
    rows = conn.execute("""
        SELECT image_uuid, label, confidence, area_pct
        FROM object_detections
        ORDER BY image_uuid, confidence DESC
    """).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[Dict]]
    for r in rows:
        if len(result[r["image_uuid"]]) < 10:
            result[r["image_uuid"]].append({
                "label": r["label"] or "",
                "conf": round(r["confidence"] or 0, 2),
            })
    return dict(result)


def load_ocr(conn: Any) -> Dict[str, List[str]]:
    """OCR text per image."""
    rows = conn.execute("""
        SELECT image_uuid, text FROM ocr_detections ORDER BY image_uuid
    """).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[str]]
    for r in rows:
        result[r["image_uuid"]].append(r["text"])
    return dict(result)


def load_exif(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, date_taken, gps_lat, gps_lon, focal_length_35mm,
               aperture, iso, shutter_speed
        FROM exif_metadata
    """).fetchall()
    result = {}
    for r in rows:
        d = {}  # type: Dict[str, Any]
        if r["date_taken"]:
            # Normalize date to YYYY-MM-DD
            dt = r["date_taken"]
            if len(dt) >= 10:
                d["date"] = dt[:10].replace(":", "-")
        if r["gps_lat"] is not None and r["gps_lon"] is not None:
            d["gps"] = [round(r["gps_lat"], 5), round(r["gps_lon"], 5)]
        if r["focal_length_35mm"]:
            d["focal"] = int(r["focal_length_35mm"])
        if r["aperture"]:
            d["f"] = round(r["aperture"], 1)
        if r["iso"]:
            d["iso"] = r["iso"]
        if r["shutter_speed"]:
            d["ss"] = r["shutter_speed"]
        result[r["image_uuid"]] = d
    return result


def load_tiers(conn: Any) -> Dict[str, Dict[str, Dict[str, str]]]:
    """Tier paths: uuid -> {tier_name: {format: local_path}}."""
    rows = conn.execute("""
        SELECT image_uuid, tier_name, format, local_path
        FROM tiers
        WHERE variant_id IS NULL
          AND tier_name IN ('thumb', 'micro', 'display', 'mobile')
    """).fetchall()
    result = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        result[r["image_uuid"]][r["tier_name"]][r["format"]] = r["local_path"]
    return dict(result)


# ── Build Photo Objects ──────────────────────────────────────────────────────

def tier_url(tiers: Dict, tier_name: str, base: str) -> Optional[str]:
    """Convert tier local_path to relative URL."""
    t = tiers.get(tier_name, {})
    path = t.get("webp") or t.get("jpeg")
    if not path:
        return None
    if path.startswith(base):
        return path[len(base):]
    return path


def build_photos(
    images: List[Dict],
    gemini_lk: Dict, colors_lk: Dict, aesthetics_lk: Dict,
    depth_lk: Dict, scenes_lk: Dict, styles_lk: Dict, captions_lk: Dict,
    pixel_lk: Dict, faces_lk: Dict, emotions_lk: Dict, objects_lk: Dict,
    ocr_lk: Dict, exif_lk: Dict, tiers_lk: Dict,
) -> Tuple[List[Dict], Dict]:
    """Build all photo objects and collect unique filter values."""

    base = str(BASE_DIR)
    photos = []
    filters = {
        "vibes": set(),
        "gradings": set(),
        "settings": set(),
        "times": set(),
        "cameras": set(),
        "styles": set(),
        "scenes": set(),
        "emotions": set(),
    }

    for img in images:
        uuid = img["uuid"]
        tiers = tiers_lk.get(uuid, {})
        gem = gemini_lk.get(uuid)
        palette = colors_lk.get(uuid, [])
        aes = aesthetics_lk.get(uuid)
        dep = depth_lk.get(uuid)
        sce = scenes_lk.get(uuid)
        sty = styles_lk.get(uuid)
        cap = captions_lk.get(uuid)
        pix = pixel_lk.get(uuid)
        face_list = faces_lk.get(uuid, [])
        emo_list = emotions_lk.get(uuid, [])
        obj_list = objects_lk.get(uuid, [])
        ocr_list = ocr_lk.get(uuid, [])
        exif = exif_lk.get(uuid, {})

        # Gemini fields (may be None for ~2,808 images)
        vibes = []
        pops = []
        geometry = []
        grading = ""
        time_of_day = ""
        setting = ""
        weather = ""
        alt_text = ""
        exposure = ""
        gem_depth = ""
        composition = ""
        gem_faces = 0

        if gem:
            vibes = parse_json_field(gem["vibe"]) or []
            pops = parse_json_field(gem["semantic_pops"]) or []
            geometry = parse_json_field(gem["geometry"]) or []
            grading = gem["grading_style"] or ""
            time_of_day = gem["time_of_day"] or ""
            setting = gem["setting"] or ""
            weather = gem["weather"] or ""
            alt_text = gem["alt_text"] or ""
            exposure = gem["exposure"] or ""
            gem_depth = gem["depth"] or ""
            composition = gem["composition_technique"] or ""
            gem_faces = gem["faces_count"] or 0

        # Primary emotion for this image
        primary_emotion = ""
        if emo_list:
            primary_emotion = emo_list[0].get("emo", "")

        camera = img["camera_body"] or ""

        photo = {
            "id": uuid,
            "category": img["category"],
            "subcategory": img["subcategory"],
            "filename": img["filename"],
            "w": img["width"],
            "h": img["height"],
            "aspect": round(img["aspect_ratio"], 3),
            "orientation": img["orientation"],
            "camera": camera,
            "medium": img["medium"] or "",
            "mono": bool(img["is_monochrome"]),
            # Colors
            "palette": palette[:5],
            "hue": round(dominant_hue_from_palette(palette[:5]), 1) if palette else 0,
            # Gemini signals
            "vibes": vibes,
            "pops": pops,
            "grading": grading,
            "time": time_of_day,
            "setting": setting,
            "weather": weather,
            "alt": alt_text,
            "exposure": exposure,
            "depth": gem_depth,
            "composition": composition,
            "geometry": geometry,
            # Advanced signals
            "aesthetic": aes,
            "caption": cap or "",
            "style": sty or "",
            "scene": sce["scene"] if sce else "",
            "environment": sce["env"] if sce else "",
            "depth_complexity": dep["complexity"] if dep else None,
            "near_pct": dep["near"] if dep else None,
            "mid_pct": dep["mid"] if dep else None,
            "far_pct": dep["far"] if dep else None,
            "brightness": pix["brightness"] if pix else None,
            "contrast": pix["contrast"] if pix else None,
            "face_count": len(face_list),
            "object_count": len(obj_list),
            "has_text": len(ocr_list) > 0,
            "emotion": primary_emotion,
            # Objects (top 5 labels)
            "objects": [o["label"] for o in obj_list[:5]],
            # EXIF
            "date": exif.get("date", ""),
            "gps": exif.get("gps"),
            "focal": exif.get("focal"),
            # Tier URLs
            "thumb": tier_url(tiers, "thumb", base),
            "micro": tier_url(tiers, "micro", base),
            "display": tier_url(tiers, "display", base),
            "mobile": tier_url(tiers, "mobile", base),
        }
        photos.append(photo)

        # Collect filter values
        for v in vibes:
            filters["vibes"].add(v)
        if grading:
            filters["gradings"].add(grading)
        if setting:
            filters["settings"].add(setting)
        if time_of_day:
            filters["times"].add(time_of_day)
        if camera:
            filters["cameras"].add(camera)
        if sty:
            filters["styles"].add(sty)
        if sce and sce["scene"]:
            filters["scenes"].add(sce["scene"])
        if primary_emotion:
            filters["emotions"].add(primary_emotion)

    return photos, filters


# ── Similarity Connections (was "drift") ─────────────────────────────────────

def compute_similarity(photos: List[Dict]) -> Dict[str, List[Dict]]:
    """Precompute top neighbors by shared vibes, objects, colors, settings."""

    # Build inverted indexes
    vibe_idx = defaultdict(set)    # type: Dict[str, set]
    obj_idx = defaultdict(set)     # type: Dict[str, set]
    setting_idx = defaultdict(set)  # type: Dict[str, set]
    camera_idx = defaultdict(set)   # type: Dict[str, set]
    scene_idx = defaultdict(set)    # type: Dict[str, set]

    for i, p in enumerate(photos):
        pid = p["id"]
        for v in p.get("vibes", []):
            vibe_idx[v.lower()].add(pid)
        for obj in p.get("objects", []):
            obj_idx[obj.lower()].add(pid)
        s = (p.get("setting") or "").lower()
        if s:
            setting_idx[s].add(pid)
        cam = (p.get("camera") or "").lower()
        if cam:
            camera_idx[cam].add(pid)
        sc = (p.get("scene") or "").lower()
        if sc:
            scene_idx[sc].add(pid)

    connections = {}
    total = len(photos)

    for i, p in enumerate(photos):
        if i % 1000 == 0:
            print(f"  Similarity: {i}/{total}...")
        pid = p["id"]
        cands = {}  # type: Dict[str, Dict]

        # Shared vibes (weight 3)
        for v in p.get("vibes", []):
            for oid in vibe_idx.get(v.lower(), set()):
                if oid == pid:
                    continue
                if oid not in cands:
                    cands[oid] = {"score": 0, "reasons": []}
                cands[oid]["score"] += 3
                r = "both " + v.lower()
                if r not in cands[oid]["reasons"]:
                    cands[oid]["reasons"].append(r)

        # Shared objects (weight 4)
        for obj in p.get("objects", []):
            for oid in obj_idx.get(obj.lower(), set()):
                if oid == pid:
                    continue
                if oid not in cands:
                    cands[oid] = {"score": 0, "reasons": []}
                cands[oid]["score"] += 4
                r = "both have " + obj
                if r not in cands[oid]["reasons"]:
                    cands[oid]["reasons"].append(r)

        # Same setting (weight 1)
        s = (p.get("setting") or "").lower()
        if s:
            for oid in setting_idx.get(s, set()):
                if oid == pid:
                    continue
                if oid not in cands:
                    cands[oid] = {"score": 0, "reasons": []}
                cands[oid]["score"] += 1
                r = "both " + p.get("setting", s)
                if r not in cands[oid]["reasons"]:
                    cands[oid]["reasons"].append(r)

        # Same scene (weight 2)
        sc = (p.get("scene") or "").lower()
        if sc:
            for oid in scene_idx.get(sc, set()):
                if oid == pid:
                    continue
                if oid not in cands:
                    cands[oid] = {"score": 0, "reasons": []}
                cands[oid]["score"] += 2
                r = "same scene: " + p.get("scene", sc)
                if r not in cands[oid]["reasons"]:
                    cands[oid]["reasons"].append(r)

        # Sort and take top N
        ranked = sorted(cands.items(), key=lambda x: x[1]["score"], reverse=True)
        top = []
        for oid, info in ranked[:SIMILARITY_NEIGHBORS]:
            top.append({
                "id": oid,
                "reason": info["reasons"][0] if info["reasons"] else "related",
            })
        connections[pid] = top

    return connections


# ── Auxiliary: Faces JSON ────────────────────────────────────────────────────

def generate_faces_json(
    photos: List[Dict],
    faces_lk: Dict[str, List[Dict]],
    emotions_lk: Dict[str, List[Dict]],
    pretty: bool = False,
) -> None:
    """Generate faces.json for Les Visages experience."""
    face_data = {}
    for p in photos:
        uuid = p["id"]
        faces = faces_lk.get(uuid, [])
        if not faces:
            continue
        emos = {e["fi"]: e for e in emotions_lk.get(uuid, [])}
        face_entries = []
        for f in faces:
            entry = {
                "x": f["x"],
                "y": f["y"],
                "w": f["w"],
                "h": f["h"],
                "conf": f["conf"],
            }
            emo = emos.get(f["fi"])
            if emo:
                entry["emo"] = emo["emo"]
                entry["emo_conf"] = emo["conf"]
            face_entries.append(entry)
        face_data[uuid] = face_entries

    path = DATA_DIR / "faces.json"
    with open(path, "w") as f:
        if pretty:
            json.dump(face_data, f, indent=2)
        else:
            json.dump(face_data, f, separators=(",", ":"))

    print(f"  faces.json: {len(face_data)} images with faces ({path.stat().st_size / 1024:.0f} KB)")


# ── Auxiliary: Game Rounds ───────────────────────────────────────────────────

def generate_game_rounds(photos: List[Dict], pretty: bool = False) -> None:
    """Generate game_rounds.json for Le Terrain de Jeu."""

    # Build connection pools
    connection_types = []

    # Group by camera
    by_camera = defaultdict(list)
    for p in photos:
        if p["camera"]:
            by_camera[p["camera"]].append(p["id"])

    # Group by emotion
    by_emotion = defaultdict(list)
    for p in photos:
        if p["emotion"]:
            by_emotion[p["emotion"]].append(p["id"])

    # Group by scene
    by_scene = defaultdict(list)
    for p in photos:
        if p["scene"]:
            by_scene[p["scene"]].append(p["id"])

    # Group by vibe
    by_vibe = defaultdict(list)
    for p in photos:
        for v in p.get("vibes", []):
            by_vibe[v].append(p["id"])

    # Group by time
    by_time = defaultdict(list)
    for p in photos:
        if p["time"]:
            by_time[p["time"]].append(p["id"])

    # Group by style
    by_style = defaultdict(list)
    for p in photos:
        if p["style"]:
            by_style[p["style"]].append(p["id"])

    # Build candidate pools: (connection_label, list_of_ids, category)
    pools = []
    for cam, ids in by_camera.items():
        if len(ids) >= 10:
            pools.append(("Same camera: " + cam, ids, "camera"))
    for emo, ids in by_emotion.items():
        if len(ids) >= 10:
            pools.append(("Same emotion: " + emo, ids, "emotion"))
    for sc, ids in by_scene.items():
        if len(ids) >= 10:
            pools.append(("Same scene: " + sc, ids, "scene"))
    for v, ids in by_vibe.items():
        if len(ids) >= 10:
            pools.append(("Same vibe: " + v, ids, "vibe"))
    for t, ids in by_time.items():
        if len(ids) >= 10:
            pools.append(("Same time: " + t, ids, "time"))
    for s, ids in by_style.items():
        if len(ids) >= 10:
            pools.append(("Same style: " + s, ids, "style"))

    if not pools:
        print("  game_rounds.json: no valid pools, skipping")
        return

    random.seed(42)  # Deterministic for reproducibility
    rounds = []
    used_pairs = set()  # type: set

    for _ in range(GAME_ROUNDS * 3):  # Generate extras, trim later
        if len(rounds) >= GAME_ROUNDS:
            break

        pool_label, pool_ids, pool_cat = random.choice(pools)
        if len(pool_ids) < 2:
            continue

        # Pick two different photos from this pool
        a, b = random.sample(pool_ids, 2)
        pair_key = tuple(sorted([a, b]))
        if pair_key in used_pairs:
            continue
        used_pairs.add(pair_key)

        # Generate wrong answers from other categories
        all_labels = [p[0] for p in pools if p[2] != pool_cat]
        if len(all_labels) < 5:
            all_labels = [p[0] for p in pools if p[0] != pool_label]
        wrong = random.sample(all_labels, min(5, len(all_labels)))

        rounds.append({
            "a": a,
            "b": b,
            "answer": pool_label,
            "wrong": wrong,
        })

    path = DATA_DIR / "game_rounds.json"
    with open(path, "w") as f:
        if pretty:
            json.dump(rounds, f, indent=2)
        else:
            json.dump(rounds, f, separators=(",", ":"))

    print(f"  game_rounds.json: {len(rounds)} rounds ({path.stat().st_size / 1024:.0f} KB)")


# ── Auxiliary: Stream Sequence ───────────────────────────────────────────────

def generate_stream_sequence(photos: List[Dict], pretty: bool = False) -> None:
    """Generate stream_sequence.json — curated order for visual flow."""

    # Separate monochrome and color photos
    mono_ids = [p["id"] for p in photos if p.get("mono")]
    color_photos = [p for p in photos if not p.get("mono")]

    if not color_photos:
        return

    # Greedy nearest-neighbor by palette for color photos
    random.seed(42)
    remaining = {p["id"]: p for p in color_photos}
    current = random.choice(color_photos)
    sequence = [current["id"]]
    del remaining[current["id"]]

    # For efficiency, sample candidates instead of checking all
    sample_size = min(200, len(remaining))

    while remaining:
        if len(remaining) <= sample_size:
            candidates = list(remaining.values())
        else:
            candidates = random.sample(list(remaining.values()), sample_size)

        best_id = candidates[0]["id"]
        best_dist = 999.0
        cur_palette = current.get("palette", [])

        if cur_palette:
            for c in candidates:
                d = palette_distance(cur_palette, c.get("palette", []))
                if d < best_dist:
                    best_dist = d
                    best_id = c["id"]

        current = remaining.pop(best_id)
        sequence.append(current["id"])

    # Insert monochrome breathers every N images
    if mono_ids:
        random.shuffle(mono_ids)
        final = []
        mono_i = 0
        for i, pid in enumerate(sequence):
            final.append(pid)
            if (i + 1) % STREAM_BREATHER_INTERVAL == 0 and mono_i < len(mono_ids):
                final.append(mono_ids[mono_i])
                mono_i += 1
        sequence = final

    path = DATA_DIR / "stream_sequence.json"
    with open(path, "w") as f:
        if pretty:
            json.dump(sequence, f, indent=2)
        else:
            json.dump(sequence, f, separators=(",", ":"))

    print(f"  stream_sequence.json: {len(sequence)} images ({path.stat().st_size / 1024:.0f} KB)")


# ── Main Export ──────────────────────────────────────────────────────────────

def export(pretty: bool = False) -> None:
    conn = db.get_connection()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading signals...")
    images = load_images(conn)
    print(f"  {len(images)} images")

    gemini_lk = load_gemini(conn)
    print(f"  {len(gemini_lk)} Gemini analyses")

    colors_lk = load_colors(conn)
    aesthetics_lk = load_aesthetics(conn)
    depth_lk = load_depth(conn)
    scenes_lk = load_scenes(conn)
    styles_lk = load_styles(conn)
    captions_lk = load_captions(conn)
    pixel_lk = load_pixel(conn)
    faces_lk = load_faces(conn)
    emotions_lk = load_emotions(conn)
    objects_lk = load_objects(conn)
    ocr_lk = load_ocr(conn)
    exif_lk = load_exif(conn)
    tiers_lk = load_tiers(conn)
    print(f"  All signal tables loaded")

    conn.close()

    print("Building photo objects...")
    photos, filters = build_photos(
        images, gemini_lk, colors_lk, aesthetics_lk, depth_lk, scenes_lk,
        styles_lk, captions_lk, pixel_lk, faces_lk, emotions_lk, objects_lk,
        ocr_lk, exif_lk, tiers_lk,
    )

    print(f"Exported {len(photos)} photos")
    for key in sorted(filters.keys()):
        print(f"  {key}: {len(filters[key])} unique")

    print("Computing similarity connections...")
    similarity = compute_similarity(photos)

    output = {
        "count": len(photos),
        "vibes": sorted(filters["vibes"]),
        "gradings": sorted(filters["gradings"]),
        "settings": sorted(filters["settings"]),
        "times": sorted(filters["times"]),
        "cameras": sorted(filters["cameras"]),
        "styles": sorted(filters["styles"]),
        "scenes": sorted(filters["scenes"]),
        "emotions": sorted(filters["emotions"]),
        "photos": photos,
        "similarity": similarity,
    }

    with open(OUTPUT_PATH, "w") as f:
        if pretty:
            json.dump(output, f, indent=2)
        else:
            json.dump(output, f, separators=(",", ":"))

    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"Written to {OUTPUT_PATH} ({size_mb:.1f} MB)")

    # Generate auxiliary files
    print("Generating auxiliary data files...")
    generate_faces_json(photos, faces_lk, emotions_lk, pretty)
    generate_game_rounds(photos, pretty)
    generate_stream_sequence(photos, pretty)

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export gallery data to JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()
    export(pretty=args.pretty)


if __name__ == "__main__":
    main()
