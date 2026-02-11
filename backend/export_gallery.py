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

import database as db

PROJECT_ROOT = db.PROJECT_ROOT
DATA_DIR = PROJECT_ROOT / "frontend" / "show" / "data"
OUTPUT_PATH = DATA_DIR / "photos.json"

GCS_BASE = "https://storage.googleapis.com/myproject-public-assets/art/MADphotos/v"

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
    """Object detections grouped by image (top 10 per image), with bbox."""
    rows = conn.execute("""
        SELECT image_uuid, label, confidence, area_pct, x, y, w, h
        FROM object_detections
        ORDER BY image_uuid, confidence DESC
    """).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[Dict]]
    for r in rows:
        if len(result[r["image_uuid"]]) < 10:
            result[r["image_uuid"]].append({
                "label": r["label"] or "",
                "conf": round(r["confidence"] or 0, 2),
                "x": round(r["x"] or 0, 3),
                "y": round(r["y"] or 0, 3),
                "w": round(r["w"] or 0, 3),
                "h": round(r["h"] or 0, 3),
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


# ── V2 Signal Loaders ────────────────────────────────────────────────────────

def load_aesthetic_v2(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, composite_score, score_label
        FROM aesthetic_scores_v2
    """).fetchall()
    return {r["image_uuid"]: {
        "score": round(r["composite_score"] or 0, 1),
        "label": r["score_label"] or "",
    } for r in rows}


def load_tags(conn: Any) -> Dict[str, List[str]]:
    rows = conn.execute("SELECT image_uuid, tags FROM image_tags").fetchall()
    result = {}
    for r in rows:
        t = r["tags"]
        result[r["image_uuid"]] = t.split("|") if t else []
    return result


def load_saliency(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, peak_x, peak_y, spread, center_bias
        FROM saliency_maps
    """).fetchall()
    return {r["image_uuid"]: {
        "px": round(r["peak_x"] or 0, 3),
        "py": round(r["peak_y"] or 0, 3),
        "spread": round(r["spread"] or 0, 2),
        "cbias": round(r["center_bias"] or 0, 2),
    } for r in rows}


def load_foreground(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, foreground_pct, centroid_x, centroid_y
        FROM foreground_masks
    """).fetchall()
    return {r["image_uuid"]: {
        "fg": round(r["foreground_pct"] or 0, 3),
        "cx": round(r["centroid_x"] or 0, 3),
        "cy": round(r["centroid_y"] or 0, 3),
    } for r in rows}


def load_open_detections(conn: Any) -> Dict[str, List[Dict]]:
    rows = conn.execute("""
        SELECT image_uuid, label, confidence, area_pct
        FROM open_detections
        ORDER BY image_uuid, confidence DESC
    """).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[Dict]]
    for r in rows:
        if len(result[r["image_uuid"]]) < 10:
            result[r["image_uuid"]].append({
                "label": r["label"] or "",
                "conf": round(r["confidence"] or 0, 2),
                "area": round(r["area_pct"] or 0, 3),
            })
    return dict(result)


def load_poses(conn: Any) -> Dict[str, int]:
    rows = conn.execute("""
        SELECT image_uuid, COUNT(*) as cnt
        FROM pose_detections
        GROUP BY image_uuid
    """).fetchall()
    return {r["image_uuid"]: r["cnt"] for r in rows}


def load_segments(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, segment_count, figure_ground_ratio, edge_complexity
        FROM segmentation_masks
    """).fetchall()
    return {r["image_uuid"]: {
        "segs": r["segment_count"] or 0,
        "fgr": round(r["figure_ground_ratio"] or 0, 2),
        "edge": round(r["edge_complexity"] or 0, 2),
    } for r in rows}


def load_florence(conn: Any) -> Dict[str, str]:
    rows = conn.execute("""
        SELECT image_uuid, detailed_caption FROM florence_captions
    """).fetchall()
    return {r["image_uuid"]: r["detailed_caption"] or "" for r in rows}


def load_identities(conn: Any) -> Dict[str, List[int]]:
    rows = conn.execute("""
        SELECT image_uuid, identity_id
        FROM face_identities
        WHERE identity_id IS NOT NULL AND identity_id != -1
        ORDER BY image_uuid, face_index
    """).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[int]]
    for r in rows:
        result[r["image_uuid"]].append(r["identity_id"])
    return dict(result)


def load_borders(conn: Any) -> Dict[str, Dict]:
    """Return dict of UUID → crop percentages for bordered images."""
    cur = conn.execute("""
        SELECT image_uuid, crop_top, crop_bottom, crop_left, crop_right
        FROM border_crops WHERE has_border = 1
    """)
    result = {}
    for row in cur.fetchall():
        uuid, ct, cb, cl, cr = row
        # Get display tier dimensions to convert pixels → percentages
        tier_row = conn.execute(
            "SELECT width, height FROM tiers WHERE image_uuid = ? AND tier_name = 'display' AND format = 'webp' LIMIT 1",
            (uuid,)
        ).fetchone()
        if tier_row:
            tw, th = tier_row
            result[uuid] = {
                "top": round(ct / th * 100, 1),
                "bottom": round(cb / th * 100, 1),
                "left": round(cl / tw * 100, 1),
                "right": round(cr / tw * 100, 1),
            }
    return result


def load_gemma(conn: Any) -> Dict[str, Dict]:
    """Gemma analysis keyed by uuid (picks only)."""
    rows = conn.execute("""
        SELECT uuid, gemma_json, gemma_mood, print_worthy FROM gemma_picks
    """).fetchall()
    result = {}
    for r in rows:
        try:
            parsed = json.loads(r["gemma_json"])
        except (json.JSONDecodeError, TypeError):
            parsed = {}
        parsed["mood_summary"] = r["gemma_mood"] or ""
        parsed["print_worthy"] = bool(r["print_worthy"]) if r["print_worthy"] is not None else None
        result[r["uuid"]] = parsed
    return result


def load_best_captions(conn: Any) -> Dict[str, Dict[str, str]]:
    """Best caption per text_type per image from unified_texts."""
    rows = conn.execute("""
        SELECT t1.image_uuid, t1.text_type, t1.content
        FROM unified_texts t1
        WHERE t1.priority = (
            SELECT MIN(t2.priority) FROM unified_texts t2
            WHERE t2.image_uuid = t1.image_uuid AND t2.text_type = t1.text_type
        )
        ORDER BY t1.image_uuid, t1.text_type
    """).fetchall()
    result = defaultdict(dict)  # type: Dict[str, Dict[str, str]]
    for r in rows:
        result[r["image_uuid"]][r["text_type"]] = r["content"]
    return dict(result)


def load_consensus_labels(conn: Any, min_models: int = 2) -> Dict[str, List[Dict]]:
    """Labels agreed upon by 2+ models, with model count + avg confidence."""
    rows = conn.execute("""
        SELECT image_uuid, label, category,
               COUNT(DISTINCT source_model) as models,
               GROUP_CONCAT(DISTINCT source_model) as which_models,
               AVG(confidence) as avg_conf
        FROM unified_labels
        GROUP BY image_uuid, label
        HAVING models >= ?
        ORDER BY image_uuid, avg_conf DESC
    """, (min_models,)).fetchall()
    result = defaultdict(list)  # type: Dict[str, List[Dict]]
    for r in rows:
        result[r["image_uuid"]].append({
            "label": r["label"],
            "category": r["category"],
            "models": r["models"],
            "conf": round(r["avg_conf"] or 0, 3),
        })
    return dict(result)


def load_unified_labels_by_category(conn: Any) -> Dict[str, Dict[str, List[str]]]:
    """Top labels per category per image (best confidence, deduplicated, capped at 8)."""
    rows = conn.execute("""
        SELECT image_uuid, label, category, MAX(confidence) as best_conf
        FROM unified_labels
        GROUP BY image_uuid, label, category
        ORDER BY image_uuid, category, best_conf DESC
    """).fetchall()
    result = defaultdict(lambda: defaultdict(list))  # type: Dict[str, Dict[str, List[str]]]
    for r in rows:
        cat_list = result[r["image_uuid"]][r["category"]]
        if len(cat_list) < 8 and r["label"] not in cat_list:
            cat_list.append(r["label"])
    return {uuid: dict(cats) for uuid, cats in result.items()}


def load_locations(conn: Any) -> Dict[str, Dict]:
    rows = conn.execute("""
        SELECT image_uuid, latitude, longitude, location_name
        FROM image_locations
    """).fetchall()
    return {r["image_uuid"]: {
        "lat": round(r["latitude"], 5) if r["latitude"] else None,
        "lon": round(r["longitude"], 5) if r["longitude"] else None,
        "name": r["location_name"] or "",
    } for r in rows}


# ── Content-Aware Focal Point ────────────────────────────────────────────────

ANIMAL_LABELS = frozenset([
    "cat", "dog", "bird", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe",
])


def compute_focal_point(
    face_list: List[Dict],
    obj_list: List[Dict],
    saliency: Optional[Dict],
    foreground: Optional[Dict],
) -> List[int]:
    """Compute content-aware focal point (x%, y%) for object-position CSS.

    Priority cascade — highest priority with data wins:
      P1: Human faces (face_detections bbox)
      P2: Animal bodies (object_detections bbox for animal labels)
      P3: Person bodies (object_detections bbox for 'person')
      P4: Saliency peak
      P5: Foreground centroid
      Default: [50, 50] (center crop)

    For the winning priority: compute the union bounding box of all regions,
    then the focal point is the center of that union. This ensures multiple
    faces/subjects all stay in frame when object-fit: cover crops the image.
    """
    # Collect regions by priority tier
    # Each region is (x, y, w, h) normalized 0-1
    face_regions = [(f["x"], f["y"], f["w"], f["h"]) for f in face_list]
    animal_regions = [
        (o["x"], o["y"], o["w"], o["h"])
        for o in obj_list if o.get("label") in ANIMAL_LABELS
    ]
    person_regions = [
        (o["x"], o["y"], o["w"], o["h"])
        for o in obj_list if o.get("label") == "person"
    ]

    # Priority cascade
    regions = None
    if face_regions:
        regions = face_regions
    elif animal_regions:
        regions = animal_regions
    elif person_regions:
        regions = person_regions

    if regions:
        # Union bounding box of all regions at this priority
        min_x = min(r[0] for r in regions)
        min_y = min(r[1] for r in regions)
        max_x = max(r[0] + r[2] for r in regions)
        max_y = max(r[1] + r[3] for r in regions)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        return [round(cx * 100), round(cy * 100)]

    if saliency and saliency.get("px") is not None:
        return [round(saliency["px"] * 100), round(saliency["py"] * 100)]

    if foreground and foreground.get("cx") is not None:
        fg_cx = foreground["cx"]
        fg_cy = foreground["cy"]
        if fg_cx > 0 or fg_cy > 0:  # skip (0,0) fallback
            return [round(fg_cx * 100), round(fg_cy * 100)]

    return [50, 50]


# ── Build Photo Objects ──────────────────────────────────────────────────────

def gcs_url(uuid: str, tier: str, variant: str = "original", fmt: str = "webp") -> str:
    """Construct GCS public URL for an image tier."""
    ext = "webp" if fmt == "webp" else "jpg"
    return f"{GCS_BASE}/{variant}/{tier}/{fmt}/{uuid}.{ext}"


def build_photos(
    images: List[Dict],
    gemini_lk: Dict, colors_lk: Dict, aesthetics_lk: Dict,
    depth_lk: Dict, scenes_lk: Dict, styles_lk: Dict, captions_lk: Dict,
    pixel_lk: Dict, faces_lk: Dict, emotions_lk: Dict, objects_lk: Dict,
    ocr_lk: Dict, exif_lk: Dict,
    # V2 signals
    aesthetic_v2_lk: Dict = None, tags_lk: Dict = None,
    saliency_lk: Dict = None, foreground_lk: Dict = None,
    open_det_lk: Dict = None, poses_lk: Dict = None,
    segments_lk: Dict = None, florence_lk: Dict = None,
    identities_lk: Dict = None, locations_lk: Dict = None,
    borders_lk: Dict = None,
    # Unified signal layer
    gemma_lk: Dict = None, best_caps_lk: Dict = None,
    consensus_lk: Dict = None, labels_by_cat_lk: Dict = None,
) -> Tuple[List[Dict], Dict]:
    """Build all photo objects and collect unique filter values."""

    aesthetic_v2_lk = aesthetic_v2_lk or {}
    tags_lk = tags_lk or {}
    saliency_lk = saliency_lk or {}
    foreground_lk = foreground_lk or {}
    open_det_lk = open_det_lk or {}
    poses_lk = poses_lk or {}
    segments_lk = segments_lk or {}
    florence_lk = florence_lk or {}
    identities_lk = identities_lk or {}
    locations_lk = locations_lk or {}
    borders_lk = borders_lk or {}
    gemma_lk = gemma_lk or {}
    best_caps_lk = best_caps_lk or {}
    consensus_lk = consensus_lk or {}
    labels_by_cat_lk = labels_by_cat_lk or {}

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
        # V2
        aes2 = aesthetic_v2_lk.get(uuid)
        tags = tags_lk.get(uuid, [])
        sal = saliency_lk.get(uuid)
        fg = foreground_lk.get(uuid)
        odet = open_det_lk.get(uuid, [])
        pose_count = poses_lk.get(uuid, 0)
        seg = segments_lk.get(uuid)
        flor = florence_lk.get(uuid)
        idents = identities_lk.get(uuid, [])
        loc = locations_lk.get(uuid)

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
            # GCS URLs — original tiers
            "thumb": gcs_url(uuid, "thumb"),
            "micro": gcs_url(uuid, "micro"),
            "display": gcs_url(uuid, "display"),
            "mobile": gcs_url(uuid, "mobile"),
            # GCS URLs — enhanced tiers
            "e_thumb": gcs_url(uuid, "thumb", "enhanced"),
            "e_display": gcs_url(uuid, "display", "enhanced"),
            # Square experience
            "squarable": True,
            # V2 signals
            "aesthetic_v2": aes2["score"] if aes2 else None,
            "aesthetic_label": aes2["label"] if aes2 else None,
            "tags": tags[:10] if tags else [],
            "saliency": sal,
            "foreground": fg,
            "open_labels": [o["label"] for o in odet[:8]],
            "pose_count": pose_count,
            "segments": seg,
            "florence": flor or "",
            "identities": idents if idents else None,
            "location": loc,
            "has_border": uuid in borders_lk,
            "border_crop": borders_lk.get(uuid),
            "focus": compute_focal_point(face_list, obj_list, sal, fg),
            # Unified signal layer
            "best_caption": (best_caps_lk.get(uuid, {}).get("caption_detailed")
                             or best_caps_lk.get(uuid, {}).get("caption_short") or ""),
            "best_short": best_caps_lk.get(uuid, {}).get("caption_short", ""),
            "consensus": [c["label"] for c in consensus_lk.get(uuid, [])[:8]],
            "all_vibes": labels_by_cat_lk.get(uuid, {}).get("vibe", [])[:8],
            "all_objects": labels_by_cat_lk.get(uuid, {}).get("object", [])[:10],
            "all_scenes": labels_by_cat_lk.get(uuid, {}).get("scene", [])[:4],
            "gemma_mood": gemma_lk.get(uuid, {}).get("mood_summary") if uuid in gemma_lk else None,
            "gemma_strength": gemma_lk.get(uuid, {}).get("strength") if uuid in gemma_lk else None,
            "print_worthy": gemma_lk.get(uuid, {}).get("print_worthy") if uuid in gemma_lk else None,
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


# ── Auxiliary: Drift Neighbors (vector similarity) ─────────────────────────

DRIFT_NEIGHBORS = 8

def generate_drift_neighbors(pretty: bool = False) -> None:
    """Generate drift_neighbors.json from LanceDB v2 vectors (DINOv2-Large)."""
    import lancedb
    import numpy as np

    lance_path = str(PROJECT_ROOT / "images" / "vectors.lance")
    lance_db = lancedb.connect(lance_path)
    tables = lance_db.table_names() if hasattr(lance_db, 'table_names') else lance_db.list_tables()

    # Prefer v2, fall back to v1
    table_name = "image_vectors_v2" if "image_vectors_v2" in tables else "image_vectors"
    table = lance_db.open_table(table_name)
    print(f"  drift: using '{table_name}'")

    arrow = table.to_arrow()
    uuids = arrow.column("uuid").to_pylist()
    dino_vecs = arrow.column("dino").to_pylist()

    # Build numpy matrix for fast cosine similarity
    matrix = np.array(dino_vecs, dtype=np.float32)
    # Normalize (should already be, but ensure)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    matrix = matrix / norms

    uuid_to_idx = {u: i for i, u in enumerate(uuids)}
    neighbors = {}

    batch_size = 500
    total = len(uuids)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = matrix[start:end]
        # Cosine similarity: batch (B, D) @ matrix.T (D, N) -> (B, N)
        sims = batch @ matrix.T
        for local_i in range(end - start):
            global_i = start + local_i
            scores = sims[local_i]
            # Get top K+1 (includes self), then exclude self
            top_indices = np.argpartition(scores, -DRIFT_NEIGHBORS - 1)[-(DRIFT_NEIGHBORS + 1):]
            top_indices = top_indices[top_indices != global_i]
            # Sort by score descending
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]][:DRIFT_NEIGHBORS]
            neighbors[uuids[global_i]] = [
                {"id": uuids[j], "score": round(float(scores[j]), 4)}
                for j in top_indices
            ]
        if end % 2000 == 0 or end == total:
            print(f"  drift: {end}/{total}...")

    path = DATA_DIR / "drift_neighbors.json"
    with open(path, "w") as f:
        if pretty:
            json.dump(neighbors, f, indent=2)
        else:
            json.dump(neighbors, f, separators=(",", ":"))

    print(f"  drift_neighbors.json: {len(neighbors)} images, {DRIFT_NEIGHBORS} neighbors each ({path.stat().st_size / (1024*1024):.1f} MB)")


# ── Auxiliary: Picks Enriched ────────────────────────────────────────────

def generate_picks_enriched(
    photos: List[Dict],
    gemma_lk: Dict,
    best_caps_lk: Dict,
    consensus_lk: Dict,
    labels_by_cat_lk: Dict,
    pretty: bool = False,
) -> None:
    """Generate picks_enriched.json — full signal package for curated picks."""
    picks_json_path = DATA_DIR / "picks.json"
    if not picks_json_path.exists():
        print("  picks_enriched.json: skipped (no picks.json)")
        return

    picks_data = json.loads(picks_json_path.read_text())
    pick_uuids = set(picks_data.get("portrait", []) + picks_data.get("landscape", []))
    photo_map = {p["id"]: p for p in photos}

    enriched = []
    for uuid in pick_uuids:
        p = photo_map.get(uuid)
        if not p:
            continue

        gemma = gemma_lk.get(uuid)
        caps = best_caps_lk.get(uuid, {})
        cons = consensus_lk.get(uuid, [])
        cats = labels_by_cat_lk.get(uuid, {})

        entry = {
            "id": uuid,
            "orientation": p.get("orientation", ""),
            "camera": p.get("camera", ""),
            "mono": p.get("mono", False),
            "best_caption": caps.get("caption_detailed") or caps.get("caption_short") or p.get("alt", ""),
            "best_short": caps.get("caption_short", ""),
            "consensus_tags": [c["label"] for c in cons[:8]],
            "all_vibes": cats.get("vibe", [])[:8],
            "all_objects": cats.get("object", [])[:10],
            # Existing fields carried over
            "vibes": p.get("vibes", []),
            "palette": p.get("palette", []),
            "aesthetic": p.get("aesthetic"),
            "scene": p.get("scene", ""),
            "style": p.get("style", ""),
            "emotion": p.get("emotion", ""),
            "date": p.get("date", ""),
            "gps": p.get("gps"),
            "focus": p.get("focus", [50, 50]),
            "thumb": p.get("thumb", ""),
            "mobile": p.get("mobile", ""),
            "display": p.get("display", ""),
        }

        if gemma:
            entry["gemma"] = {
                "description": gemma.get("description", ""),
                "subject": gemma.get("subject", ""),
                "story": gemma.get("story", ""),
                "mood": gemma.get("mood_summary", ""),
                "composition": gemma.get("composition", ""),
                "lighting": gemma.get("lighting", ""),
                "colors": gemma.get("colors", ""),
                "texture": gemma.get("texture", ""),
                "technical": gemma.get("technical", ""),
                "strength": gemma.get("strength", ""),
                "print_worthy": gemma.get("print_worthy"),
            }

        enriched.append(entry)

    path = DATA_DIR / "picks_enriched.json"
    with open(path, "w") as f:
        if pretty:
            json.dump(enriched, f, indent=2, ensure_ascii=False)
        else:
            json.dump(enriched, f, separators=(",", ":"), ensure_ascii=False)

    size_kb = path.stat().st_size / 1024
    print(f"  picks_enriched.json: {len(enriched)} picks ({size_kb:.0f} KB)")


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
    print(f"  All v1 signal tables loaded")

    # V2 signals
    aesthetic_v2_lk = load_aesthetic_v2(conn)
    tags_lk = load_tags(conn)
    saliency_lk = load_saliency(conn)
    foreground_lk = load_foreground(conn)
    open_det_lk = load_open_detections(conn)
    poses_lk = load_poses(conn)
    segments_lk = load_segments(conn)
    florence_lk = load_florence(conn)
    identities_lk = load_identities(conn)
    locations_lk = load_locations(conn)
    borders_lk = load_borders(conn)
    print(f"  All v2 signal tables loaded ({len(borders_lk)} bordered images)")

    # Unified signal layer (from populate_unified.py)
    gemma_lk = {}
    best_caps_lk = {}
    consensus_lk = {}
    labels_by_cat_lk = {}
    try:
        gemma_lk = load_gemma(conn)
        best_caps_lk = load_best_captions(conn)
        consensus_lk = load_consensus_labels(conn)
        labels_by_cat_lk = load_unified_labels_by_category(conn)
        print(f"  Unified: {len(gemma_lk)} gemma, {len(best_caps_lk)} captions, "
              f"{len(consensus_lk)} consensus, {len(labels_by_cat_lk)} label profiles")
    except Exception as e:
        print(f"  Unified tables not yet populated ({e}) — skipping unified fields")

    conn.close()

    print("Building photo objects...")
    print(f"  Using GCS URLs: {GCS_BASE}/...")
    photos, filters = build_photos(
        images, gemini_lk, colors_lk, aesthetics_lk, depth_lk, scenes_lk,
        styles_lk, captions_lk, pixel_lk, faces_lk, emotions_lk, objects_lk,
        ocr_lk, exif_lk,
        aesthetic_v2_lk=aesthetic_v2_lk, tags_lk=tags_lk,
        saliency_lk=saliency_lk, foreground_lk=foreground_lk,
        open_det_lk=open_det_lk, poses_lk=poses_lk,
        segments_lk=segments_lk, florence_lk=florence_lk,
        identities_lk=identities_lk, locations_lk=locations_lk,
        borders_lk=borders_lk,
        gemma_lk=gemma_lk, best_caps_lk=best_caps_lk,
        consensus_lk=consensus_lk, labels_by_cat_lk=labels_by_cat_lk,
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
    generate_drift_neighbors(pretty)
    generate_picks_enriched(photos, gemma_lk, best_caps_lk,
                            consensus_lk, labels_by_cat_lk, pretty)

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export gallery data to JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()
    export(pretty=args.pretty)


if __name__ == "__main__":
    main()
