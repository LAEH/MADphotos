#!/usr/bin/env python3
"""
Border detection and cropping pipeline for analog film scans.
Detects white/cream scan borders, stores crop coordinates, renders cropped tiers.

Usage: python3 border_crop.py [--dry-run] [--limit N]
"""

import os
import sys
import sqlite3
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = os.path.join(str(PROJECT_ROOT), "images/mad_photos.db")
DISPLAY_DIR = os.path.join(str(PROJECT_ROOT), "images/rendered/display/jpeg")
THUMB_DIR = os.path.join(str(PROJECT_ROOT), "images/rendered/thumb/jpeg")
CROPPED_DISPLAY_DIR = os.path.join(str(PROJECT_ROOT), "images/rendered/cropped/jpeg")
CROPPED_THUMB_DIR = os.path.join(str(PROJECT_ROOT), "images/rendered/cropped/thumb")


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS border_crops (
            image_uuid    TEXT PRIMARY KEY REFERENCES images(uuid),
            has_border    INTEGER NOT NULL DEFAULT 0,
            crop_top      INTEGER DEFAULT 0,
            crop_bottom   INTEGER DEFAULT 0,
            crop_left     INTEGER DEFAULT 0,
            crop_right    INTEGER DEFAULT 0,
            border_pct    REAL DEFAULT 0,
            edges_detected INTEGER DEFAULT 0,
            analyzed_at   TEXT NOT NULL
        )
    """)
    conn.commit()


def detect_border(img_path):
    """Detect white/cream film scan border. Returns crop coordinates or None."""
    img = cv2.imread(img_path)
    if img is None:
        return None

    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    border_width_pct = 0.03  # sample outer 3%
    brightness_thresh = 220
    saturation_thresh = 30
    content_thresh = 210
    min_border_px = 8

    edges = {}

    # Check each edge
    for edge in ["top", "bottom", "left", "right"]:
        if edge == "top":
            strip = hsv[:int(h * border_width_pct), :]
        elif edge == "bottom":
            strip = hsv[int(h * (1 - border_width_pct)):, :]
        elif edge == "left":
            strip = hsv[:, :int(w * border_width_pct)]
        else:
            strip = hsv[:, int(w * (1 - border_width_pct)):]

        mean_v = strip[:, :, 2].mean()
        mean_s = strip[:, :, 1].mean()

        if mean_v > brightness_thresh and mean_s < saturation_thresh:
            # Scan inward to find where content begins
            crop_px = 0
            if edge == "top":
                for row in range(h // 4):
                    row_v = hsv[row, w // 4 : 3 * w // 4, 2].mean()
                    if row_v < content_thresh:
                        crop_px = max(0, row - 2)
                        break
            elif edge == "bottom":
                for row in range(h - 1, 3 * h // 4, -1):
                    row_v = hsv[row, w // 4 : 3 * w // 4, 2].mean()
                    if row_v < content_thresh:
                        crop_px = max(0, h - 1 - row - 2)
                        break
            elif edge == "left":
                for col in range(w // 4):
                    col_v = hsv[h // 4 : 3 * h // 4, col, 2].mean()
                    if col_v < content_thresh:
                        crop_px = max(0, col - 2)
                        break
            else:
                for col in range(w - 1, 3 * w // 4, -1):
                    col_v = hsv[h // 4 : 3 * h // 4, col, 2].mean()
                    if col_v < content_thresh:
                        crop_px = max(0, w - 1 - col - 2)
                        break

            if crop_px >= min_border_px:
                edges[edge] = crop_px

    n_edges = len(edges)
    if n_edges < 2:
        return {"has_border": False, "crop_top": 0, "crop_bottom": 0,
                "crop_left": 0, "crop_right": 0, "border_pct": 0, "edges": 0}

    ct = edges.get("top", 0)
    cb = edges.get("bottom", 0)
    cl = edges.get("left", 0)
    cr = edges.get("right", 0)

    border_area = ct * w + cb * w + cl * (h - ct - cb) + cr * (h - ct - cb)
    border_pct = (border_area / (h * w)) * 100

    if border_pct < 1.0:
        return {"has_border": False, "crop_top": 0, "crop_bottom": 0,
                "crop_left": 0, "crop_right": 0, "border_pct": 0, "edges": 0}

    return {
        "has_border": True,
        "crop_top": ct,
        "crop_bottom": cb,
        "crop_left": cl,
        "crop_right": cr,
        "border_pct": round(border_pct, 2),
        "edges": n_edges,
    }


def render_cropped(uuid, crop, display_path, thumb_path):
    """Render cropped display and thumb tiers."""
    # Display tier
    img = Image.open(display_path)
    w, h = img.size
    # Scale crop coords from original to display tier
    orig_w = crop["orig_w"]
    orig_h = crop["orig_h"]
    scale_x = w / orig_w
    scale_y = h / orig_h

    ct = int(crop["crop_top"] * scale_y)
    cb = int(crop["crop_bottom"] * scale_y)
    cl = int(crop["crop_left"] * scale_x)
    cr = int(crop["crop_right"] * scale_x)

    cropped = img.crop((cl, ct, w - cr, h - cb))

    # Save cropped display
    out_display = os.path.join(CROPPED_DISPLAY_DIR, f"{uuid}.jpg")
    cropped.save(out_display, "JPEG", quality=92)

    # Save cropped thumb (320px long edge)
    cw, ch = cropped.size
    if cw > ch:
        thumb_w = 320
        thumb_h = int(320 * ch / cw)
    else:
        thumb_h = 320
        thumb_w = int(320 * cw / ch)
    thumb = cropped.resize((thumb_w, thumb_h), Image.LANCZOS)
    out_thumb = os.path.join(CROPPED_THUMB_DIR, f"{uuid}.jpg")
    thumb.save(out_thumb, "JPEG", quality=85)

    return out_display, out_thumb


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    os.makedirs(CROPPED_DISPLAY_DIR, exist_ok=True)
    os.makedirs(CROPPED_THUMB_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    create_table(conn)

    # Get all analog UUIDs with their dimensions
    rows = conn.execute("""
        SELECT uuid, width, height FROM images WHERE category = 'Analog'
    """).fetchall()

    if args.limit > 0:
        rows = rows[:args.limit]

    total = len(rows)
    print(f"Scanning {total} analog images for borders...")

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    detected = 0
    rendered = 0
    start = time.time()

    for idx, (uuid, orig_w, orig_h) in enumerate(rows):
        display_path = os.path.join(DISPLAY_DIR, f"{uuid}.jpg")
        if not os.path.exists(display_path):
            continue

        result = detect_border(display_path)
        if result is None:
            continue

        conn.execute("""
            INSERT OR REPLACE INTO border_crops
            (image_uuid, has_border, crop_top, crop_bottom, crop_left, crop_right,
             border_pct, edges_detected, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (uuid, 1 if result["has_border"] else 0,
              result["crop_top"], result["crop_bottom"],
              result["crop_left"], result["crop_right"],
              result["border_pct"], result["edges"],
              now))

        if result["has_border"] and not args.dry_run:
            detected += 1
            crop_data = {**result, "orig_w": orig_w, "orig_h": orig_h}
            try:
                thumb_path = os.path.join(THUMB_DIR, f"{uuid}.jpg")
                render_cropped(uuid, crop_data, display_path, thumb_path)
                rendered += 1
            except Exception as e:
                print(f"  Render error {uuid}: {e}")

        if (idx + 1) % 100 == 0:
            conn.commit()
            elapsed = time.time() - start
            print(f"  {idx + 1}/{total} ({elapsed:.1f}s, {detected} borders found, {rendered} rendered)")

    conn.commit()
    conn.close()

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Scanned: {total}")
    print(f"  Borders detected: {detected}")
    print(f"  Cropped tiers rendered: {rendered}")


if __name__ == "__main__":
    main()
