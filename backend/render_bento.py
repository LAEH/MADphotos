#!/usr/bin/env python3
"""
render_bento.py — Render a bento composition as a high-res PNG.

Takes a bento layout (cols, rows, cells) + photo IDs, composites them
into a single image using the same grid math and smart cropping as the
frontend BentoView.

Output: 4096px PNG + 1024px preview JPG + _meta.json sidecar.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
DISPLAY_DIR = PROJECT_ROOT / "images" / "rendered" / "display" / "jpeg"
OUTPUT_DIR = PROJECT_ROOT / "images" / "rendered" / "bentos"

UNIT_RATIO = 4 / 3  # matches BENTO_UNIT_RATIO in cropUtils.ts


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _crop_key_from_ratio(ratio: float) -> str:
    """Mirror cropKeyFromRatio() from cropUtils.ts."""
    if ratio >= 1.6:
        return "16:9"
    if ratio >= 1.2:
        return "3:2"
    if ratio <= 0.85:
        return "2:3"
    return "1:1"


def _get_crop_data(conn: sqlite3.Connection, photo_ids: list[str]) -> dict:
    """Fetch smart crop data for photos: gemma_crops, saliency, foreground centroid."""
    data: dict[str, dict] = {}
    placeholders = ",".join("?" for _ in photo_ids)

    # Gemma crops
    rows = conn.execute(
        f"SELECT image_uuid, crops FROM gemma_analysis WHERE image_uuid IN ({placeholders})",
        photo_ids,
    ).fetchall()
    for r in rows:
        uuid = r["image_uuid"]
        if uuid not in data:
            data[uuid] = {}
        try:
            data[uuid]["gemma_crops"] = json.loads(r["crops"]) if r["crops"] else None
        except (json.JSONDecodeError, TypeError):
            data[uuid]["gemma_crops"] = None

    # Saliency peaks
    rows = conn.execute(
        f"SELECT image_uuid, peak_x, peak_y FROM saliency_maps WHERE image_uuid IN ({placeholders})",
        photo_ids,
    ).fetchall()
    for r in rows:
        uuid = r["image_uuid"]
        if uuid not in data:
            data[uuid] = {}
        data[uuid]["saliency"] = (r["peak_x"], r["peak_y"])

    # Foreground centroid
    rows = conn.execute(
        f"SELECT image_uuid, centroid_x, centroid_y FROM foreground_masks WHERE image_uuid IN ({placeholders})",
        photo_ids,
    ).fetchall()
    for r in rows:
        uuid = r["image_uuid"]
        if uuid not in data:
            data[uuid] = {}
        data[uuid]["centroid"] = (r["centroid_x"], r["centroid_y"])

    return data


def _smart_focal_point(crop_data: dict, container_ratio: float) -> tuple[float, float]:
    """Return (fx, fy) as 0-1 fractions. Mirrors smartObjectPosition() cascade."""
    # 1. Gemma crops
    gemma = crop_data.get("gemma_crops")
    if gemma:
        key = _crop_key_from_ratio(container_ratio)
        crop = gemma.get(key)
        if crop and "center_x" in crop and "center_y" in crop:
            return (crop["center_x"] / 100.0, crop["center_y"] / 100.0)

    # 2. Saliency peak
    sal = crop_data.get("saliency")
    if sal and sal[0] is not None and sal[1] is not None:
        return (sal[0], sal[1])

    # 3. Foreground centroid
    cent = crop_data.get("centroid")
    if cent and cent[0] is not None and cent[1] is not None:
        return (cent[0], cent[1])

    # 4. Center
    return (0.5, 0.5)


def _smart_crop_resize(
    img: Image.Image, target_w: int, target_h: int,
    fx: float, fy: float,
) -> Image.Image:
    """Crop source image centered on focal point to fill target dimensions (object-fit: cover)."""
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # Source is wider — crop horizontally
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)
    else:
        # Source is taller — crop vertically
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)

    # Center crop on focal point
    cx = int(fx * src_w)
    cy = int(fy * src_h)

    left = max(0, min(cx - crop_w // 2, src_w - crop_w))
    top = max(0, min(cy - crop_h // 2, src_h - crop_h))

    cropped = img.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((target_w, target_h), Image.LANCZOS)


def _round_corner_mask(w: int, h: int, radius: int) -> Image.Image:
    """Create an alpha mask with rounded corners."""
    mask = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(mask)
    # Clear corners, then draw rounded arcs
    draw.rectangle([0, 0, radius, radius], fill=0)
    draw.rectangle([w - radius, 0, w, radius], fill=0)
    draw.rectangle([0, h - radius, radius, h], fill=0)
    draw.rectangle([w - radius, h - radius, w, h], fill=0)
    draw.pieslice([0, 0, radius * 2, radius * 2], 180, 270, fill=255)
    draw.pieslice([w - radius * 2, 0, w, radius * 2], 270, 360, fill=255)
    draw.pieslice([0, h - radius * 2, radius * 2, h], 90, 180, fill=255)
    draw.pieslice([w - radius * 2, h - radius * 2, w, h], 0, 90, fill=255)
    return mask


def render_bento_png(
    cols: int,
    rows: int,
    cells: list[dict],
    photo_ids: list[str],
    target_width: int = 4096,
    gap: int = 8,
    layout_id: str = "",
    bg_color: tuple[int, int, int] = (0, 0, 0),
    border_radius: int = 12,
    curator: str = "",
) -> Optional[dict]:
    """
    Render a bento composition as PNG.

    Args:
        cols, rows: Grid dimensions
        cells: List of {r, c, rs, cs, orient} dicts (1-indexed)
        photo_ids: Photo UUIDs matching cells
        target_width: Output width in pixels
        gap: Gap between cells in pixels (at target scale)
        layout_id: Layout identifier for filename
        bg_color: Background color
        border_radius: Corner radius for cells

    Returns:
        {path, preview_path, meta_path} or None on failure
    """
    if len(photo_ids) < len(cells):
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Scale gap to target width (CSS uses 8px at ~1200px viewport)
    scale = target_width / 1200
    scaled_gap = int(gap * scale)
    scaled_radius = int(border_radius * scale)

    # Grid math — matches CSS exactly
    cell_w = (target_width - (cols - 1) * scaled_gap) / cols
    cell_h = cell_w / UNIT_RATIO

    # Compute total height
    total_h = int(rows * cell_h + (rows - 1) * scaled_gap)

    # Create canvas
    canvas = Image.new("RGB", (target_width, total_h), bg_color)

    # Load crop data
    conn = _get_conn()
    crop_data = _get_crop_data(conn, photo_ids[:len(cells)])
    conn.close()

    placed = 0
    for i, cell in enumerate(cells):
        if i >= len(photo_ids):
            break

        uuid = photo_ids[i]
        img_path = DISPLAY_DIR / f"{uuid}.jpg"
        if not img_path.exists():
            continue

        try:
            img = Image.open(img_path).convert("RGB")
        except Exception:
            continue

        c_col = cell["c"]  # 1-indexed
        c_row = cell["r"]  # 1-indexed
        cs = cell.get("cs", 1)
        rs = cell.get("rs", 1)

        # Cell position and size
        x = int((c_col - 1) * (cell_w + scaled_gap))
        y = int((c_row - 1) * (cell_h + scaled_gap))
        w = int(cs * cell_w + (cs - 1) * scaled_gap)
        h = int(rs * cell_h + (rs - 1) * scaled_gap)

        # Container ratio for smart crop
        container_ratio = (cs * UNIT_RATIO) / rs

        # Get focal point
        cd = crop_data.get(uuid, {})
        fx, fy = _smart_focal_point(cd, container_ratio)

        # Smart crop + resize
        tile = _smart_crop_resize(img, w, h, fx, fy)

        # Apply rounded corners
        if scaled_radius > 0:
            mask = _round_corner_mask(w, h, scaled_radius)
            # Create a tile with alpha for compositing
            tile_rgba = tile.convert("RGBA")
            tile_rgba.putalpha(mask)
            canvas.paste(tile, (x, y), tile_rgba)
        else:
            canvas.paste(tile, (x, y))

        placed += 1

    if placed == 0:
        return None

    # Generate filename
    ts = int(time.time())
    hash_input = f"{layout_id}_{','.join(photo_ids[:len(cells)])}"
    hash8 = hashlib.md5(hash_input.encode()).hexdigest()[:8]
    base_name = f"{ts}_{layout_id}_{hash8}"

    png_path = OUTPUT_DIR / f"{base_name}.png"
    preview_path = OUTPUT_DIR / f"{base_name}_preview.jpg"
    meta_path = OUTPUT_DIR / f"{base_name}_meta.json"

    # Save full-res PNG
    canvas.save(str(png_path), "PNG")

    # Save preview JPG (1024px wide)
    preview_w = 1024
    preview_h = int(total_h * (preview_w / target_width))
    preview = canvas.resize((preview_w, preview_h), Image.LANCZOS)
    preview.save(str(preview_path), "JPEG", quality=90)

    # Save metadata sidecar
    meta = {
        "layout_id": layout_id,
        "cols": cols,
        "rows": rows,
        "cells": cells,
        "photo_ids": photo_ids[:len(cells)],
        "target_width": target_width,
        "output_width": target_width,
        "output_height": total_h,
        "placed": placed,
        "timestamp": ts,
        "png": png_path.name,
        "preview": preview_path.name,
        "curator": curator,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    return {
        "path": str(png_path),
        "preview_path": str(preview_path),
        "meta_path": str(meta_path),
        "url": f"/rendered/bentos/{png_path.name}",
        "preview_url": f"/rendered/bentos/{preview_path.name}",
        "width": target_width,
        "height": total_h,
        "placed": placed,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 backend/render_bento.py <meta.json>")
        print("  Renders a bento from a saved meta.json file.")
        sys.exit(1)

    meta_file = Path(sys.argv[1])
    if not meta_file.exists():
        print(f"File not found: {meta_file}")
        sys.exit(1)

    meta = json.loads(meta_file.read_text())
    result = render_bento_png(
        cols=meta["cols"],
        rows=meta["rows"],
        cells=meta["cells"],
        photo_ids=meta["photo_ids"],
        layout_id=meta.get("layout_id", ""),
    )
    if result:
        print(f"Rendered: {result['path']}")
        print(f"Preview:  {result['preview_path']}")
    else:
        print("Failed to render bento.")
        sys.exit(1)
