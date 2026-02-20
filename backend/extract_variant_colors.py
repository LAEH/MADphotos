#!/usr/bin/env python3
"""
extract_variant_colors.py — Extract dominant colors from style_transfer variants.

Scans generated_test/ directories for Imagen style-transfer outputs,
matches them to ai_variants DB rows via deterministic variant_id,
and runs K-means LAB clustering (same algorithm as signals.py).

Results go into the dominant_colors table with image_uuid = variant_id,
so they can be loaded by export_gallery.py alongside original photo colors.

Usage:
    python3 extract_variant_colors.py              # Process all unprocessed
    python3 extract_variant_colors.py --reprocess  # Redo all
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
GENERATED_DIR = Path(__file__).resolve().parent / "generated_test"

UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Same color name mapping as signals.py
NAMED_COLORS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "gray": (128, 128, 128),
    "silver": (192, 192, 192), "red": (255, 0, 0), "maroon": (128, 0, 0),
    "yellow": (255, 255, 0), "olive": (128, 128, 0), "lime": (0, 255, 0),
    "green": (0, 128, 0), "aqua": (0, 255, 255), "teal": (0, 128, 128),
    "blue": (0, 0, 255), "navy": (0, 0, 128), "fuchsia": (255, 0, 255),
    "purple": (128, 0, 128), "orange": (255, 165, 0), "brown": (139, 69, 19),
    "beige": (245, 245, 220), "ivory": (255, 255, 240), "coral": (255, 127, 80),
    "salmon": (250, 128, 114), "pink": (255, 192, 203), "gold": (255, 215, 0),
    "khaki": (240, 230, 140), "tan": (210, 180, 140), "crimson": (220, 20, 60),
    "indigo": (75, 0, 130), "violet": (238, 130, 238), "cyan": (0, 255, 255),
    "turquoise": (64, 224, 208), "slate": (112, 128, 144), "charcoal": (54, 69, 79),
    "cream": (255, 253, 208), "rust": (183, 65, 14), "burgundy": (128, 0, 32),
    "forest": (34, 139, 34), "sky": (135, 206, 235), "steel": (70, 130, 180),
    "peach": (255, 218, 185), "lavender": (230, 230, 250), "mint": (189, 252, 201),
}


def nearest_color_name(r: int, g: int, b: int) -> str:
    best_name = "gray"
    best_dist = float("inf")
    for name, (nr, ng, nb) in NAMED_COLORS.items():
        d = (r - nr) ** 2 + (g - ng) ** 2 + (b - nb) ** 2
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name


def variant_id_for(image_uuid: str, style_idx: int, style_name: str) -> str:
    """Deterministic variant ID — must match generate_test_images.py."""
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:style_{style_idx}_{style_name}"))


def smart_variant_id_for(image_uuid: str, style_key: str) -> str:
    """Deterministic smart variant ID — must match generate_smart_variants.py."""
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:smart_{style_key}"))


def scan_variant_files() -> Dict[str, Path]:
    """Scan generated_test/ to build variant_id → file_path mapping.

    Uses the latest run_dir for each variant (sorted by timestamp dirname).
    """
    mapping: Dict[str, Path] = {}
    style_re = re.compile(r"^imagen_(\d+)_(.+)\.jpg$")
    smart_re = re.compile(r"^imagen_smart_(.+)\.jpg$")

    # Sort run dirs by name (timestamp order) so later ones override earlier
    run_dirs = sorted(d for d in GENERATED_DIR.iterdir() if d.is_dir())

    for run_dir in run_dirs:
        for uuid_dir in run_dir.iterdir():
            if not uuid_dir.is_dir():
                continue
            image_uuid = uuid_dir.name
            for img_file in uuid_dir.iterdir():
                if not img_file.name.endswith(".jpg"):
                    continue

                # Smart variants: imagen_smart_{style}.jpg
                ms = smart_re.match(img_file.name)
                if ms:
                    style_key = ms.group(1)
                    vid = smart_variant_id_for(image_uuid, style_key)
                    mapping[vid] = img_file
                    continue

                # Legacy style variants: imagen_{idx}_{style}.jpg
                m = style_re.match(img_file.name)
                if m:
                    style_idx = int(m.group(1))
                    safe_name = m.group(2)
                    vid = variant_id_for(image_uuid, style_idx, safe_name)
                    mapping[vid] = img_file

    return mapping


def extract_colors_for_image(path: Path, n_clusters: int = 5) -> List[Dict]:
    """Run K-means LAB clustering on one image. Returns list of cluster dicts."""
    from sklearn.cluster import KMeans

    img = cv2.imread(str(path))
    if img is None:
        return []

    # Resize to ~200px for speed
    h, w = img.shape[:2]
    scale = 200.0 / max(w, h)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # Convert to LAB
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    pixels = lab.reshape(-1, 3).astype(np.float32)

    # K-means
    km = KMeans(n_clusters=n_clusters, n_init=3, max_iter=100, random_state=42)
    km.fit(pixels)

    # Get cluster sizes
    labels, counts_arr = np.unique(km.labels_, return_counts=True)
    total_px = len(km.labels_)

    # Sort by cluster size (largest first)
    order = np.argsort(-counts_arr)

    clusters = []
    for idx, cluster_idx in enumerate(order):
        center_lab = km.cluster_centers_[cluster_idx]
        pct = counts_arr[cluster_idx] / total_px

        # Convert LAB center back to RGB
        lab_pixel = np.uint8([[center_lab]])
        bgr_pixel = cv2.cvtColor(lab_pixel, cv2.COLOR_LAB2BGR)
        b_val, g_val, r_val = int(bgr_pixel[0, 0, 0]), int(bgr_pixel[0, 0, 1]), int(bgr_pixel[0, 0, 2])
        hex_str = f"#{r_val:02x}{g_val:02x}{b_val:02x}"
        name = nearest_color_name(r_val, g_val, b_val)

        clusters.append({
            "cluster_index": idx,
            "r": r_val, "g": g_val, "b": b_val,
            "hex": hex_str,
            "l": float(center_lab[0]), "a": float(center_lab[1]), "b_val": float(center_lab[2]),
            "percentage": float(pct),
            "color_name": name,
        })

    return clusters


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract dominant colors from style_transfer variants")
    parser.add_argument("--reprocess", action="store_true", help="Redo already-processed variants")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Get ALL successful variants (every type, every review status)
    rows = conn.execute("""
        SELECT variant_id, image_uuid, variant_type, review_status
        FROM ai_variants
        WHERE generation_status = 'success'
    """).fetchall()
    all_variants = {r["variant_id"]: r["image_uuid"] for r in rows}

    by_type = {}
    for r in rows:
        key = f"{r['variant_type']}:{r['review_status'] or 'unreviewed'}"
        by_type[key] = by_type.get(key, 0) + 1
    print(f"[Colors] {len(all_variants)} successful variants in DB")
    for key in sorted(by_type.keys()):
        print(f"  {key}: {by_type[key]}")

    # Find which already have colors
    if args.reprocess:
        existing = set()
    else:
        existing = set(
            r[0] for r in conn.execute(
                "SELECT DISTINCT image_uuid FROM dominant_colors"
            ).fetchall()
        )

    # Scan filesystem for variant files
    print("[Colors] Scanning generated_test/ for variant files...")
    file_map = scan_variant_files()
    print(f"[Colors] Found {len(file_map)} variant files on disk")

    # Also scan ai_variants/ for all variant type directories
    ai_variants_dir = PROJECT_ROOT / "images" / "ai_variants"
    if ai_variants_dir.exists():
        for vtype_dir in ai_variants_dir.iterdir():
            if not vtype_dir.is_dir():
                continue
            for jpg in vtype_dir.rglob("*.jpg"):
                vid = jpg.stem  # variant_id is the filename without extension
                if vid in all_variants:
                    file_map[vid] = jpg

    # Filter to variants that need processing
    todo = []
    for vid, image_uuid in all_variants.items():
        if vid in existing:
            continue
        if vid not in file_map:
            continue
        todo.append((vid, file_map[vid]))

    print(f"[Colors] {len(todo)} variants to process ({len(existing & set(all_variants.keys()))} already done, "
          f"{len(all_variants) - len(todo) - len(existing & set(all_variants.keys()))} missing files)")

    if not todo:
        print("[Colors] Nothing to do.")
        conn.close()
        return

    ts = datetime.now(timezone.utc).isoformat()
    count = 0
    t0 = time.time()

    for vid, path in todo:
        try:
            clusters = extract_colors_for_image(path)
            if not clusters:
                count += 1
                continue

            for c in clusters:
                conn.execute("""
                    INSERT OR REPLACE INTO dominant_colors (
                        image_uuid, cluster_index, r, g, b, hex, l, a, b_val,
                        percentage, color_name, analyzed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    vid, c["cluster_index"], c["r"], c["g"], c["b"], c["hex"],
                    c["l"], c["a"], c["b_val"],
                    c["percentage"], c["color_name"], ts,
                ))

            count += 1
            if count % 20 == 0:
                conn.commit()
                elapsed = time.time() - t0
                print(f"  {count}/{len(todo)} ({elapsed:.1f}s, {count/elapsed:.1f}/s)")

        except Exception as e:
            print(f"  ERROR {vid}: {e}")
            count += 1

    conn.commit()
    conn.close()
    elapsed = time.time() - t0
    print(f"[Colors] Done: {count} variants in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
