#!/usr/bin/env python3
"""
prep_blind_test.py — Prepare a 3-way blind comparison test.

Samples 100 images and creates a shuffled blind test with:
  - Original (display tier)
  - Enhanced v1 (enhance_engine.py output)
  - Enhanced v2 (enhance_engine_v2.py output)

Each row's 3 images are placed in random order.
Output: ai_variants/blind_test/ with manifest.json + image files.

Usage:
    python3 prep_blind_test.py              # Sample 100 images
    python3 prep_blind_test.py --count 50   # Sample 50 images
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys
from pathlib import Path
from typing import List, Dict, Any

import database as db

PROJECT_ROOT = db.PROJECT_ROOT
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
BLIND_TEST_DIR = PROJECT_ROOT / "images" / "ai_variants" / "blind_test"
ENHANCED_V1_DIR = RENDERED_DIR / "enhanced" / "jpeg"
ENHANCED_V2_DIR = RENDERED_DIR / "enhanced_v2" / "jpeg"
DISPLAY_DIR = RENDERED_DIR / "display" / "jpeg"


def select_diverse_sample(conn, count: int = 100) -> List[Dict[str, Any]]:
    """Select a diverse sample of images across cameras and styles."""
    # Get images that have both v1 and v2 enhancements
    rows = conn.execute("""
        SELECT
            i.uuid, i.camera_body,
            st.style,
            sc.scene_1,
            t.local_path as display_path
        FROM images i
        JOIN enhancement_plans ep ON i.uuid = ep.image_uuid AND ep.status = 'enhanced'
        JOIN enhancement_plans_v2 ep2 ON i.uuid = ep2.image_uuid AND ep2.status = 'enhanced'
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = 'display' AND t.format = 'jpeg' AND t.variant_id IS NULL
        LEFT JOIN style_classification st ON i.uuid = st.image_uuid
        LEFT JOIN scene_classification sc ON i.uuid = sc.image_uuid
        ORDER BY RANDOM()
    """).fetchall()

    all_images = [dict(r) for r in rows]
    print(f"Found {len(all_images)} images with both v1 and v2 enhancements")

    if len(all_images) <= count:
        return all_images[:count]

    # Stratified sampling: aim for camera diversity
    by_camera = {}  # type: Dict[str, List]
    for img in all_images:
        cam = img.get("camera_body") or "Unknown"
        by_camera.setdefault(cam, []).append(img)

    selected = []  # type: List[Dict[str, Any]]
    # Allocate proportionally by camera
    for cam, imgs in by_camera.items():
        n = max(1, round(count * len(imgs) / len(all_images)))
        random.shuffle(imgs)
        selected.extend(imgs[:n])

    # Trim or fill to exact count
    random.shuffle(selected)
    if len(selected) > count:
        selected = selected[:count]
    elif len(selected) < count:
        remaining = [img for img in all_images if img not in selected]
        random.shuffle(remaining)
        selected.extend(remaining[:count - len(selected)])

    return selected[:count]


def prep_blind_test(count: int = 100) -> None:
    conn = db.get_connection()

    sample = select_diverse_sample(conn, count)
    if not sample:
        print("No images found with both v1 and v2 enhancements!")
        conn.close()
        return

    print(f"Selected {len(sample)} images for blind test")

    # Camera distribution
    cam_counts = {}  # type: Dict[str, int]
    for img in sample:
        cam = img.get("camera_body") or "Unknown"
        cam_counts[cam] = cam_counts.get(cam, 0) + 1
    for cam, cnt in sorted(cam_counts.items(), key=lambda x: -x[1]):
        print(f"  {cam}: {cnt}")

    # Prepare output directory
    BLIND_TEST_DIR.mkdir(parents=True, exist_ok=True)
    # Clean old files
    for f in BLIND_TEST_DIR.glob("*.jpg"):
        f.unlink()

    manifest = []
    methods = ["original", "enhanced_v1", "enhanced_v2"]
    copied = 0
    skipped = 0

    for img in sample:
        uuid = img["uuid"]

        # Source paths
        orig_path = DISPLAY_DIR / f"{uuid}.jpg"
        v1_path = ENHANCED_V1_DIR / f"{uuid}.jpg"
        v2_path = ENHANCED_V2_DIR / f"{uuid}.jpg"

        # Verify all 3 exist
        if not orig_path.exists() or not v1_path.exists() or not v2_path.exists():
            skipped += 1
            continue

        # Copy to blind test directory
        shutil.copy2(str(orig_path), str(BLIND_TEST_DIR / f"{uuid}_original.jpg"))
        shutil.copy2(str(v1_path), str(BLIND_TEST_DIR / f"{uuid}_enhanced_v1.jpg"))
        shutil.copy2(str(v2_path), str(BLIND_TEST_DIR / f"{uuid}_enhanced_v2.jpg"))

        # Random order for this row
        order = methods[:]
        random.shuffle(order)

        manifest.append({
            "uuid": uuid,
            "camera": img.get("camera_body", ""),
            "style": img.get("style", ""),
            "scene": img.get("scene_1", ""),
            "order": order,
        })
        copied += 1

    # Write manifest
    manifest_path = BLIND_TEST_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"\nBlind test prepared:")
    print(f"  Images: {copied} ({skipped} skipped)")
    print(f"  Files: {copied * 3} JPEGs + manifest.json")
    print(f"  Directory: {BLIND_TEST_DIR}")
    print(f"  Manifest: {manifest_path}")

    conn.close()


if __name__ == "__main__":
    count = 100
    if "--count" in sys.argv:
        idx = sys.argv.index("--count")
        if idx + 1 < len(sys.argv):
            count = int(sys.argv[idx + 1])
    prep_blind_test(count)
