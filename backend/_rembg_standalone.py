#!/usr/bin/env python3
"""
Standalone foreground mask extraction using rembg.

Run this in a CLEAN Python process — do NOT import torch first.
rembg uses ONNX internally; torch is not needed. The MPS float64 issue
prevents rembg from working inside signals_v2.py where torch is already
loaded with MPS, so this script exists as a workaround.

Usage:
    python _rembg_standalone.py
    python _rembg_standalone.py --limit 500
"""

import os

# Set before ANY imports in case rembg pulls in torch internally
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import argparse
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from rembg import new_session, remove
from scipy import ndimage

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
DISPLAY_DIR = PROJECT_ROOT / "images" / "rendered" / "display" / "jpeg"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS foreground_masks (
    image_uuid TEXT PRIMARY KEY,
    foreground_pct REAL,
    background_pct REAL,
    edge_sharpness REAL,
    centroid_x REAL,
    centroid_y REAL,
    bbox_x REAL,
    bbox_y REAL,
    bbox_w REAL,
    bbox_h REAL,
    analyzed_at TEXT
);
"""

UPSERT_SQL = """
INSERT INTO foreground_masks (
    image_uuid, foreground_pct, background_pct, edge_sharpness,
    centroid_x, centroid_y, bbox_x, bbox_y, bbox_w, bbox_h, analyzed_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(image_uuid) DO UPDATE SET
    foreground_pct = excluded.foreground_pct,
    background_pct = excluded.background_pct,
    edge_sharpness = excluded.edge_sharpness,
    centroid_x = excluded.centroid_x,
    centroid_y = excluded.centroid_y,
    bbox_x = excluded.bbox_x,
    bbox_y = excluded.bbox_y,
    bbox_w = excluded.bbox_w,
    bbox_h = excluded.bbox_h,
    analyzed_at = excluded.analyzed_at;
"""

# ---------------------------------------------------------------------------
# Query: images with display tier that lack foreground_masks
# ---------------------------------------------------------------------------
PENDING_SQL = """
SELECT i.uuid
FROM images i
JOIN tiers t
    ON t.image_uuid = i.uuid
    AND t.tier_name = 'display'
    AND t.format = 'jpeg'
    AND t.variant_id IS NULL
WHERE NOT EXISTS (
    SELECT 1 FROM foreground_masks fm WHERE fm.image_uuid = i.uuid
)
ORDER BY i.uuid;
"""


def resize_max(img: Image.Image, max_side: int = 512) -> Image.Image:
    """Resize so longest side is at most max_side, preserving aspect ratio."""
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    scale = max_side / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return img.resize((new_w, new_h), Image.LANCZOS)


def analyze_mask(mask: Image.Image) -> dict:
    """Compute foreground statistics from a binary mask."""
    mask_np = np.array(mask).astype(np.float32) / 255.0
    binary = (mask_np > 0.5).astype(np.float32)
    h, w = mask_np.shape

    total_px = h * w
    fg_px = int(binary.sum())
    bg_px = total_px - fg_px

    foreground_pct = fg_px / total_px if total_px > 0 else 0.0
    background_pct = bg_px / total_px if total_px > 0 else 1.0

    # Edge sharpness via Sobel gradient
    gradient = ndimage.sobel(mask_np)
    if fg_px > 0:
        edge_sharpness = float(gradient[binary > 0.3].mean())
    else:
        edge_sharpness = 0.0

    # Centroid (normalized 0-1)
    if fg_px > 0:
        ys, xs = np.where(binary > 0.5)
        centroid_x = float(xs.mean()) / w
        centroid_y = float(ys.mean()) / h
    else:
        centroid_x = 0.5
        centroid_y = 0.5

    # Bounding box (normalized 0-1)
    if fg_px > 0:
        bbox_x = float(xs.min()) / w
        bbox_y = float(ys.min()) / h
        bbox_w = float(xs.max() - xs.min()) / w
        bbox_h = float(ys.max() - ys.min()) / h
    else:
        bbox_x = 0.0
        bbox_y = 0.0
        bbox_w = 0.0
        bbox_h = 0.0

    return {
        "foreground_pct": round(foreground_pct, 6),
        "background_pct": round(background_pct, 6),
        "edge_sharpness": round(edge_sharpness, 6),
        "centroid_x": round(centroid_x, 6),
        "centroid_y": round(centroid_y, 6),
        "bbox_x": round(bbox_x, 6),
        "bbox_y": round(bbox_y, 6),
        "bbox_w": round(bbox_w, 6),
        "bbox_h": round(bbox_h, 6),
    }


def main():
    parser = argparse.ArgumentParser(description="Extract foreground masks with rembg")
    parser.add_argument("--limit", type=int, default=0, help="Max images to process (0 = all)")
    args = parser.parse_args()

    print(f"DB:       {DB_PATH}")
    print(f"Display:  {DISPLAY_DIR}")

    # Connect to DB
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()

    # Get pending images
    rows = conn.execute(PENDING_SQL).fetchall()
    uuids = [r[0] for r in rows]
    if args.limit > 0:
        uuids = uuids[: args.limit]

    total = len(uuids)
    print(f"Pending:  {total} images")

    if total == 0:
        print("Nothing to do.")
        conn.close()
        return

    # Create rembg session — CPU only, no torch needed
    print("Loading u2net session (ONNX CPU)...")
    session = new_session("u2net", providers=["CPUExecutionProvider"])
    print("Session ready.\n")

    t0 = time.time()
    done = 0
    errors = 0

    for i, uuid in enumerate(uuids):
        img_path = DISPLAY_DIR / f"{uuid}.jpg"

        if not img_path.exists():
            print(f"  SKIP {uuid} — file not found")
            errors += 1
            continue

        try:
            img = Image.open(img_path).convert("RGB")
            img = resize_max(img, 512)

            # Get binary mask from rembg
            mask = remove(img, only_mask=True, session=session)
            if mask.mode != "L":
                mask = mask.convert("L")

            stats = analyze_mask(mask)
            now = datetime.now(timezone.utc).isoformat()

            conn.execute(
                UPSERT_SQL,
                (
                    uuid,
                    stats["foreground_pct"],
                    stats["background_pct"],
                    stats["edge_sharpness"],
                    stats["centroid_x"],
                    stats["centroid_y"],
                    stats["bbox_x"],
                    stats["bbox_y"],
                    stats["bbox_w"],
                    stats["bbox_h"],
                    now,
                ),
            )
            done += 1

        except Exception as e:
            print(f"  ERROR {uuid}: {e}")
            errors += 1

        # Commit + progress every 100
        if (i + 1) % 100 == 0 or (i + 1) == total:
            conn.commit()
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            print(f"  [{i + 1}/{total}] done={done} errors={errors} rate={rate:.1f} img/s elapsed={elapsed:.0f}s")

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    rate = done / elapsed if elapsed > 0 else 0
    print(f"\nFinished: {done} processed, {errors} errors, {rate:.1f} img/s, {elapsed:.0f}s total")


if __name__ == "__main__":
    main()
