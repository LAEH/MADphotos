#!/usr/bin/env python3
"""Detect and trim uniform-color borders from generated variant images.

Scans all variant images on disk, detects borders by checking for uniform
color strips along each edge, crops them off, and records the trim in the DB.

Usage:
  python3 backend/trim_variant_borders.py              # trim all variants
  python3 backend/trim_variant_borders.py --dry-run    # preview only, no writes
  python3 backend/trim_variant_borders.py --threshold 20  # adjust sensitivity
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
AI_VARIANTS_DIR = PROJECT_ROOT / "images" / "ai_variants"
GENERATED_DIR = PROJECT_ROOT / "backend" / "suggest_image_variant" / "output"


def detect_border(img_array: np.ndarray, threshold: float = 15.0) -> tuple[int, int, int, int]:
    """Detect uniform-color borders on all 4 sides.

    Returns (top, right, bottom, left) in pixels.

    Algorithm: for each edge, take a 1px strip and compute std deviation
    across all channels. If std < threshold, the strip is "uniform" (border).
    March inward until we hit content (std >= threshold).
    Also verify the border color is consistent — adjacent strips must be
    within tolerance of the edge color.
    """
    h, w = img_array.shape[:2]
    max_border = 0.25  # never trim more than 25% from any side

    def row_is_border(y: int, ref_color: np.ndarray) -> bool:
        row = img_array[y, :, :].astype(float)
        # Check if row is uniform (low variance)
        if np.std(row) > threshold * 3:
            return False
        # Check if row color matches the reference border color
        mean_color = np.mean(row, axis=0)
        return np.max(np.abs(mean_color - ref_color)) < threshold * 2

    def col_is_border(x: int, ref_color: np.ndarray) -> bool:
        col = img_array[:, x, :].astype(float)
        if np.std(col) > threshold * 3:
            return False
        mean_color = np.mean(col, axis=0)
        return np.max(np.abs(mean_color - ref_color)) < threshold * 2

    # Top border
    top = 0
    if h > 10:
        ref = np.mean(img_array[0, :, :].astype(float), axis=0)
        for y in range(min(int(h * max_border), h)):
            if row_is_border(y, ref):
                top = y + 1
            else:
                break

    # Bottom border
    bottom = 0
    if h > 10:
        ref = np.mean(img_array[h - 1, :, :].astype(float), axis=0)
        for y in range(h - 1, max(h - int(h * max_border), 0) - 1, -1):
            if row_is_border(y, ref):
                bottom = h - y
            else:
                break

    # Left border
    left = 0
    if w > 10:
        ref = np.mean(img_array[:, 0, :].astype(float), axis=0)
        for x in range(min(int(w * max_border), w)):
            if col_is_border(x, ref):
                left = x + 1
            else:
                break

    # Right border
    right = 0
    if w > 10:
        ref = np.mean(img_array[:, w - 1, :].astype(float), axis=0)
        for x in range(w - 1, max(w - int(w * max_border), 0) - 1, -1):
            if col_is_border(x, ref):
                right = w - x
            else:
                break

    return top, right, bottom, left


def find_variant_files() -> dict[str, Path]:
    """Map variant_id to file path by scanning ai_variants and suggest_image_variant/output dirs."""
    files: dict[str, Path] = {}

    # Scan ai_variants/{type}/{variant_id}.jpg
    if AI_VARIANTS_DIR.exists():
        for type_dir in AI_VARIANTS_DIR.iterdir():
            if not type_dir.is_dir():
                continue
            for f in type_dir.glob("*.jpg"):
                files[f.stem] = f
            for f in type_dir.glob("*.png"):
                files[f.stem] = f

    # Scan suggest_image_variant/output/{run}/{uuid}/imagen_*.jpg and neural_*.jpg
    if GENERATED_DIR.exists():
        for run_dir in sorted(GENERATED_DIR.iterdir()):
            if not run_dir.is_dir():
                continue
            for uuid_dir in run_dir.iterdir():
                if not uuid_dir.is_dir():
                    continue
                for f in uuid_dir.glob("imagen_*.jpg"):
                    # variant_id might match the filename stem or be tracked in DB
                    files[f.stem] = f
                for f in uuid_dir.glob("neural_*.jpg"):
                    files[f.stem] = f

    return files


def snap_to_ratio(w: int, h: int) -> tuple[int, int]:
    """Snap dimensions to nearest standard aspect ratio.

    Standard ratios: 1:1, 1:2, 2:1, 2:3, 3:2, 3:4, 4:3, 16:9, 9:16.
    Returns adjusted (width, height) that maintains aspect ratio
    by trimming the longer dimension.
    """
    ratio = w / h
    RATIOS = [
        (1, 2, 0.5),
        (9, 16, 9 / 16),
        (2, 3, 2 / 3),
        (3, 4, 3 / 4),
        (1, 1, 1.0),
        (4, 3, 4 / 3),
        (3, 2, 3 / 2),
        (16, 9, 16 / 9),
        (2, 1, 2.0),
    ]
    # Find closest ratio
    best = min(RATIOS, key=lambda r: abs(ratio - r[2]))
    target_ratio = best[2]

    if ratio > target_ratio:
        # Too wide — trim width
        new_w = int(h * target_ratio)
        return new_w, h
    else:
        # Too tall — trim height
        new_h = int(w / target_ratio)
        return w, new_h


def main():
    parser = argparse.ArgumentParser(description="Trim borders from variant images")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't modify files")
    parser.add_argument("--threshold", type=float, default=15.0, help="Border detection sensitivity (default 15)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")

    # Add border columns if they don't exist
    try:
        conn.execute("ALTER TABLE ai_variants ADD COLUMN border_top INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE ai_variants ADD COLUMN border_right INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE ai_variants ADD COLUMN border_bottom INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE ai_variants ADD COLUMN border_left INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE ai_variants ADD COLUMN trimmed INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # Get all successful variants
    rows = conn.execute(
        "SELECT variant_id, variant_type, image_uuid FROM ai_variants "
        "WHERE generation_status = 'success'"
    ).fetchall()
    print(f"Found {len(rows)} successful variants")

    # Find files on disk
    file_map = find_variant_files()
    print(f"Found {len(file_map)} variant files on disk")

    # Also check direct variant_id matches in ai_variants dirs
    for variant_id, variant_type, _ in rows:
        if variant_id not in file_map:
            # Try direct path
            for ext in (".jpg", ".png"):
                p = AI_VARIANTS_DIR / variant_type / (variant_id + ext)
                if p.exists():
                    file_map[variant_id] = p
                    break

    trimmed = 0
    skipped = 0
    no_file = 0
    no_border = 0
    errors = 0

    for variant_id, variant_type, image_uuid in rows:
        file_path = file_map.get(variant_id)
        if not file_path or not file_path.exists():
            no_file += 1
            continue

        try:
            img = Image.open(file_path).convert("RGB")
            arr = np.array(img)
            orig_h, orig_w = arr.shape[:2]

            top, right, bottom, left = detect_border(arr, args.threshold)

            has_border = (top + right + bottom + left) > 0

            if has_border:
                # Crop out the borders
                crop_left = left
                crop_top = top
                crop_right = orig_w - right
                crop_bottom = orig_h - bottom
                cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))
                cw, ch = cropped.size

                # Snap to standard ratio
                snap_w, snap_h = snap_to_ratio(cw, ch)
                if snap_w != cw or snap_h != ch:
                    # Center crop to snapped ratio
                    dx = (cw - snap_w) // 2
                    dy = (ch - snap_h) // 2
                    cropped = cropped.crop((dx, dy, dx + snap_w, dy + snap_h))

                final_w, final_h = cropped.size
                pct_removed = (1 - (final_w * final_h) / (orig_w * orig_h)) * 100

                print(f"  {variant_type:15s} {variant_id[:8]}  "
                      f"{orig_w}x{orig_h} → {final_w}x{final_h}  "
                      f"borders T:{top} R:{right} B:{bottom} L:{left}  "
                      f"({pct_removed:.1f}% removed)")

                if not args.dry_run:
                    # Save cropped image (JPEG quality 95)
                    cropped.save(str(file_path), "JPEG", quality=95)
                    conn.execute(
                        "UPDATE ai_variants SET border_top=?, border_right=?, border_bottom=?, border_left=?, trimmed=1 "
                        "WHERE variant_id=?",
                        (top, right, bottom, left, variant_id),
                    )
                trimmed += 1
            else:
                # No border — still snap ratio if needed
                snap_w, snap_h = snap_to_ratio(orig_w, orig_h)
                if snap_w != orig_w or snap_h != orig_h:
                    dx = (orig_w - snap_w) // 2
                    dy = (orig_h - snap_h) // 2
                    cropped = img.crop((dx, dy, dx + snap_w, dy + snap_h))
                    final_w, final_h = cropped.size
                    print(f"  {variant_type:15s} {variant_id[:8]}  "
                          f"{orig_w}x{orig_h} → {final_w}x{final_h}  "
                          f"ratio snap (no border)")
                    if not args.dry_run:
                        cropped.save(str(file_path), "JPEG", quality=95)
                        conn.execute(
                            "UPDATE ai_variants SET trimmed=1 WHERE variant_id=?",
                            (variant_id,),
                        )
                    trimmed += 1
                else:
                    no_border += 1
                    conn.execute(
                        "UPDATE ai_variants SET trimmed=0 WHERE variant_id=?",
                        (variant_id,),
                    )

        except Exception as e:
            print(f"  ERROR {variant_id[:8]}: {e}")
            errors += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\nDone{'  (DRY RUN)' if args.dry_run else ''}:")
    print(f"  Trimmed/snapped: {trimmed}")
    print(f"  No border:       {no_border}")
    print(f"  No file:         {no_file}")
    print(f"  Errors:          {errors}")


if __name__ == "__main__":
    main()
