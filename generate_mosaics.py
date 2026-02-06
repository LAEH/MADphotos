#!/usr/bin/env python3
"""
generate_mosaics.py — Create 4096px square mosaic images from the photo collection.

Each mosaic tiles all images sorted by a different dimension:
brightness, hue, saturation, color temperature, category, camera,
time of day, grading, faces, objects, blur, random, etc.
"""
from __future__ import annotations

import json
import math
import os
import random
import sqlite3
import sys
import colorsys
from pathlib import Path
from typing import Optional, List, Tuple, Dict

from PIL import Image

DB_PATH = Path(__file__).resolve().parent / "mad_photos.db"
RENDERED_DIR = Path(__file__).resolve().parent / "rendered"
MOSAIC_DIR = Path(__file__).resolve().parent / "rendered" / "mosaics"
TARGET_SIZE = 4096


def get_conn():
    # type: () -> sqlite3.Connection
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_micro_paths():
    # type: () -> Dict[str, str]
    """Return {uuid: local_path} for all micro/jpeg tier files."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT image_uuid, local_path FROM tiers "
        "WHERE tier_name='micro' AND format='jpeg' AND variant_id IS NULL"
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        p = r["local_path"]
        if p and os.path.exists(p):
            result[r["image_uuid"]] = p
    return result


def build_mosaic(uuids, micro_paths, filename, title):
    # type: (List[str], Dict[str, str], str, str) -> Optional[str]
    """Build a square mosaic from ordered UUIDs. Returns output path."""
    # Filter to UUIDs that have micro paths
    valid = [u for u in uuids if u in micro_paths]
    if not valid:
        print(f"  [SKIP] {filename} — no valid images")
        return None

    n = int(math.ceil(math.sqrt(len(valid))))
    tile_size = TARGET_SIZE // n
    mosaic_size = n * tile_size

    print(f"  [{filename}] {len(valid)} images, {n}x{n} grid, {tile_size}px tiles, {mosaic_size}px mosaic")

    mosaic = Image.new("RGB", (mosaic_size, mosaic_size), (0, 0, 0))

    for idx, uuid in enumerate(valid):
        if idx >= n * n:
            break
        row = idx // n
        col = idx % n
        x = col * tile_size
        y = row * tile_size

        try:
            img = Image.open(micro_paths[uuid])
            img = img.convert("RGB")
            # Center-crop to square, then resize
            w, h = img.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
            img = img.resize((tile_size, tile_size), Image.LANCZOS)
            mosaic.paste(img, (x, y))
        except Exception as e:
            pass  # Leave black tile

    out_path = MOSAIC_DIR / f"{filename}.jpg"
    mosaic.save(str(out_path), "JPEG", quality=92)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"    → {out_path.name} ({size_mb:.1f} MB)")
    return str(out_path)


def generate_all():
    # type: () -> List[Dict]
    """Generate all mosaic variants. Returns metadata list."""
    MOSAIC_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    micro_paths = get_micro_paths()
    all_uuids = list(micro_paths.keys())

    print(f"Loaded {len(all_uuids)} images with micro tier paths")
    print(f"Target: {TARGET_SIZE}px mosaics")
    print()

    mosaics = []  # type: List[Dict]

    # ── 1. Random ─────────────────────────────────────────────
    print("1/14 Random")
    shuffled = list(all_uuids)
    random.seed(42)
    random.shuffle(shuffled)
    build_mosaic(shuffled, micro_paths, "random", "Random")
    mosaics.append({
        "file": "random.jpg",
        "title": "Random",
        "desc": f"{len(shuffled)} images in random order",
        "count": len(shuffled)
    })

    # ── 2. By Category ───────────────────────────────────────
    print("2/14 By Category")
    rows = conn.execute(
        "SELECT uuid, category FROM images ORDER BY category, uuid"
    ).fetchall()
    ordered = [r["uuid"] for r in rows if r["uuid"] in micro_paths]
    cats = {}
    for r in rows:
        cats.setdefault(r["category"], 0)
        if r["uuid"] in micro_paths:
            cats[r["category"]] += 1
    build_mosaic(ordered, micro_paths, "by_category", "By Category")
    cat_desc = ", ".join(f"{k}: {v}" for k, v in sorted(cats.items(), key=lambda x: -x[1]))
    mosaics.append({
        "file": "by_category.jpg",
        "title": "By Category",
        "desc": f"Grouped by category — {cat_desc}",
        "count": len(ordered)
    })

    # ── 3. By Camera Body ─────────────────────────────────────
    print("3/14 By Camera Body")
    _cam_map = {
        ("Digital", None): "Leica Digital", ("Digital", "Landscape"): "Leica Digital",
        ("Digital", "Portrait"): "Leica Digital",
        ("Analog", None): "Leica Analog", ("Analog", "Landscape"): "Leica Analog",
        ("Analog", "Portrait"): "Leica Analog",
        ("Monochrome", None): "Leica Monochrom", ("Monochrome", "Landscape"): "Leica Monochrom",
        ("Monochrome", "Portrait"): "Leica Monochrom",
        ("G12", None): "Canon G12",
        ("Osmo", "OsmoPro"): "DJI Osmo Pro", ("Osmo", "OsmoMemo"): "DJI Osmo Memo",
        ("Osmo", None): "DJI Osmo",
    }
    rows = conn.execute("SELECT uuid, category, subcategory FROM images").fetchall()
    cam_order = ["Leica Analog", "Leica Digital", "Leica Monochrom", "Canon G12", "DJI Osmo Pro", "DJI Osmo Memo"]
    cam_groups = {c: [] for c in cam_order}
    for r in rows:
        if r["uuid"] not in micro_paths:
            continue
        cam = _cam_map.get((r["category"], r["subcategory"]),
                           _cam_map.get((r["category"], None), r["category"]))
        if cam in cam_groups:
            cam_groups[cam].append(r["uuid"])
        else:
            cam_groups.setdefault(cam, []).append(r["uuid"])
    ordered = []
    cam_desc_parts = []
    for cam in cam_order:
        if cam in cam_groups:
            cam_desc_parts.append(f"{cam}: {len(cam_groups[cam])}")
            ordered.extend(cam_groups[cam])
    build_mosaic(ordered, micro_paths, "by_camera", "By Camera Body")
    mosaics.append({
        "file": "by_camera.jpg",
        "title": "By Camera Body",
        "desc": "Grouped by camera — " + ", ".join(cam_desc_parts),
        "count": len(ordered)
    })

    # ── 4. By Brightness (dark → light) ──────────────────────
    print("4/14 By Brightness")
    rows = conn.execute(
        "SELECT image_uuid, mean_brightness FROM image_analysis "
        "WHERE mean_brightness IS NOT NULL ORDER BY mean_brightness ASC"
    ).fetchall()
    ordered = [r["image_uuid"] for r in rows if r["image_uuid"] in micro_paths]
    build_mosaic(ordered, micro_paths, "by_brightness", "By Brightness")
    mosaics.append({
        "file": "by_brightness.jpg",
        "title": "By Brightness",
        "desc": f"Sorted dark → light by mean pixel brightness — {len(ordered)} images",
        "count": len(ordered)
    })

    # ── 5. By Dominant Hue ────────────────────────────────────
    print("5/14 By Dominant Hue")
    rows = conn.execute(
        "SELECT image_uuid, dominant_hue FROM image_analysis "
        "WHERE dominant_hue IS NOT NULL ORDER BY dominant_hue ASC"
    ).fetchall()
    ordered = [r["image_uuid"] for r in rows if r["image_uuid"] in micro_paths]
    build_mosaic(ordered, micro_paths, "by_hue", "By Dominant Hue")
    mosaics.append({
        "file": "by_hue.jpg",
        "title": "By Dominant Hue",
        "desc": f"Sorted by dominant hue angle (0°→360°, red→yellow→green→blue→violet) — {len(ordered)} images",
        "count": len(ordered)
    })

    # ── 6. By Saturation ─────────────────────────────────────
    print("6/14 By Saturation")
    rows = conn.execute(
        "SELECT image_uuid, mean_saturation FROM image_analysis "
        "WHERE mean_saturation IS NOT NULL ORDER BY mean_saturation ASC"
    ).fetchall()
    ordered = [r["image_uuid"] for r in rows if r["image_uuid"] in micro_paths]
    build_mosaic(ordered, micro_paths, "by_saturation", "By Saturation")
    mosaics.append({
        "file": "by_saturation.jpg",
        "title": "By Saturation",
        "desc": f"Sorted desaturated → vivid by mean saturation — {len(ordered)} images",
        "count": len(ordered)
    })

    # ── 7. By Color Temperature ───────────────────────────────
    print("7/14 By Color Temperature")
    rows = conn.execute(
        "SELECT image_uuid, est_color_temp FROM image_analysis "
        "WHERE est_color_temp IS NOT NULL ORDER BY est_color_temp ASC"
    ).fetchall()
    ordered = [r["image_uuid"] for r in rows if r["image_uuid"] in micro_paths]
    build_mosaic(ordered, micro_paths, "by_colortemp", "By Color Temperature")
    mosaics.append({
        "file": "by_colortemp.jpg",
        "title": "By Color Temperature",
        "desc": f"Sorted warm → cool by estimated color temperature — {len(ordered)} images",
        "count": len(ordered)
    })

    # ── 8. By Dominant Color (K-means cluster 0 hue) ─────────
    print("8/14 By Dominant Color")
    rows = conn.execute(
        "SELECT image_uuid, r, g, b FROM dominant_colors WHERE cluster_index = 0"
    ).fetchall()
    uuid_hue = []
    for r in rows:
        if r["image_uuid"] not in micro_paths:
            continue
        rgb = (r["r"] / 255.0, r["g"] / 255.0, r["b"] / 255.0)
        h, s, v = colorsys.rgb_to_hsv(*rgb)
        uuid_hue.append((r["image_uuid"], h, s, v))
    # Sort by hue, then saturation
    uuid_hue.sort(key=lambda x: (x[1], x[2]))
    ordered = [u[0] for u in uuid_hue]
    build_mosaic(ordered, micro_paths, "by_dominant_color", "By Dominant Color")
    mosaics.append({
        "file": "by_dominant_color.jpg",
        "title": "By Dominant Color",
        "desc": f"Sorted by K-means primary cluster hue (HSV) — {len(ordered)} images",
        "count": len(ordered)
    })

    # ── 9. By Contrast ───────────────────────────────────────
    print("9/14 By Contrast")
    rows = conn.execute(
        "SELECT image_uuid, contrast_ratio FROM image_analysis "
        "WHERE contrast_ratio IS NOT NULL ORDER BY contrast_ratio ASC"
    ).fetchall()
    ordered = [r["image_uuid"] for r in rows if r["image_uuid"] in micro_paths]
    build_mosaic(ordered, micro_paths, "by_contrast", "By Contrast")
    mosaics.append({
        "file": "by_contrast.jpg",
        "title": "By Contrast",
        "desc": f"Sorted flat → punchy by contrast ratio — {len(ordered)} images",
        "count": len(ordered)
    })

    # ── 10. By Sharpness (blur score) ─────────────────────────
    print("10/14 By Sharpness")
    rows = conn.execute(
        "SELECT image_uuid, blur_score FROM image_hashes "
        "WHERE blur_score IS NOT NULL ORDER BY blur_score ASC"
    ).fetchall()
    ordered = [r["image_uuid"] for r in rows if r["image_uuid"] in micro_paths]
    build_mosaic(ordered, micro_paths, "by_sharpness", "By Sharpness")
    mosaics.append({
        "file": "by_sharpness.jpg",
        "title": "By Sharpness",
        "desc": f"Sorted soft → sharp by Laplacian blur score — {len(ordered)} images",
        "count": len(ordered)
    })

    # ── 11. By Time of Day (Gemini) ───────────────────────────
    print("11/14 By Time of Day")
    time_order = {"dawn": 0, "sunrise": 1, "morning": 2, "midday": 3, "afternoon": 4,
                  "golden hour": 5, "sunset": 6, "twilight": 7, "evening": 8, "night": 9}
    rows = conn.execute(
        "SELECT image_uuid, time_of_day FROM gemini_analysis "
        "WHERE time_of_day IS NOT NULL"
    ).fetchall()
    time_list = []
    for r in rows:
        if r["image_uuid"] not in micro_paths:
            continue
        tod = (r["time_of_day"] or "").strip().lower()
        order = time_order.get(tod, 5)
        time_list.append((r["image_uuid"], order, tod))
    time_list.sort(key=lambda x: x[1])
    ordered = [t[0] for t in time_list]
    time_counts = {}
    for t in time_list:
        time_counts[t[2]] = time_counts.get(t[2], 0) + 1
    td = ", ".join(f"{k}: {v}" for k, v in sorted(time_counts.items(), key=lambda x: time_order.get(x[0], 99)))
    build_mosaic(ordered, micro_paths, "by_time_of_day", "By Time of Day")
    mosaics.append({
        "file": "by_time_of_day.jpg",
        "title": "By Time of Day",
        "desc": f"Grouped dawn → night (Gemini analysis) — {td}",
        "count": len(ordered)
    })

    # ── 12. By Grading Style (Gemini) ─────────────────────────
    print("12/14 By Grading Style")
    rows = conn.execute(
        "SELECT image_uuid, grading_style FROM gemini_analysis "
        "WHERE grading_style IS NOT NULL"
    ).fetchall()
    grade_list = []
    for r in rows:
        if r["image_uuid"] not in micro_paths:
            continue
        grade_list.append((r["image_uuid"], (r["grading_style"] or "").strip().lower()))
    grade_list.sort(key=lambda x: x[1])
    ordered = [g[0] for g in grade_list]
    grade_counts = {}
    for g in grade_list:
        grade_counts[g[1]] = grade_counts.get(g[1], 0) + 1
    gd = ", ".join(f"{k}: {v}" for k, v in sorted(grade_counts.items(), key=lambda x: -x[1])[:8])
    build_mosaic(ordered, micro_paths, "by_grading", "By Grading Style")
    mosaics.append({
        "file": "by_grading.jpg",
        "title": "By Grading Style",
        "desc": f"Grouped by Gemini color grading — {gd}",
        "count": len(ordered)
    })

    # ── 13. Faces First ───────────────────────────────────────
    print("13/14 Faces First")
    rows = conn.execute(
        "SELECT image_uuid, COUNT(*) as fc FROM face_detections "
        "GROUP BY image_uuid ORDER BY fc DESC"
    ).fetchall()
    face_uuids = [r["image_uuid"] for r in rows if r["image_uuid"] in micro_paths]
    # Add remaining images (no faces) sorted randomly
    no_face = [u for u in all_uuids if u not in set(face_uuids)]
    random.seed(42)
    random.shuffle(no_face)
    ordered = face_uuids + no_face
    build_mosaic(ordered, micro_paths, "by_faces", "Faces First")
    mosaics.append({
        "file": "by_faces.jpg",
        "title": "Faces First",
        "desc": f"{len(face_uuids)} images with faces (sorted by face count, most first), then {len(no_face)} without",
        "count": len(ordered)
    })

    # ── 14. By GPS Latitude ───────────────────────────────────
    print("14/14 By GPS Latitude")
    rows = conn.execute(
        "SELECT image_uuid, gps_lat FROM exif_metadata "
        "WHERE gps_lat IS NOT NULL ORDER BY gps_lat ASC"
    ).fetchall()
    ordered = [r["image_uuid"] for r in rows if r["image_uuid"] in micro_paths]
    if len(ordered) > 100:
        lat_min = conn.execute("SELECT MIN(gps_lat) FROM exif_metadata WHERE gps_lat IS NOT NULL").fetchone()[0]
        lat_max = conn.execute("SELECT MAX(gps_lat) FROM exif_metadata WHERE gps_lat IS NOT NULL").fetchone()[0]
        build_mosaic(ordered, micro_paths, "by_latitude", "By GPS Latitude")
        mosaics.append({
            "file": "by_latitude.jpg",
            "title": "By GPS Latitude",
            "desc": f"Sorted south → north ({lat_min:.1f}° → {lat_max:.1f}°) — {len(ordered)} images with GPS",
            "count": len(ordered)
        })
    else:
        print("  [SKIP] Not enough GPS data")

    conn.close()

    # Save metadata
    meta_path = MOSAIC_DIR / "mosaics.json"
    with open(str(meta_path), "w") as f:
        json.dump(mosaics, f, indent=2)
    print(f"\nDone! {len(mosaics)} mosaics saved to {MOSAIC_DIR}")
    print(f"Metadata: {meta_path}")
    return mosaics


if __name__ == "__main__":
    generate_all()
