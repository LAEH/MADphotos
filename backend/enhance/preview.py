"""Pure image manipulation for enhancement previews — no DB access."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

PREVIEW_MAX_EDGE = 1200
PREVIEW_QUALITY = 90


def _detect_border(img: Image.Image, hi: int = 230, lo: int = 30) -> tuple[int, int, int, int]:
    """Scan from each edge inward to find border strips (white, dark, or layered).
    Handles scanned photos with dark scan edge -> white paper border -> content.
    Does NOT break on transition rows — scans through gaps so layered borders
    (dark then white) are handled correctly.
    Returns (top, bottom, left, right) pixel counts to crop."""
    w, h = img.size
    step = 4

    def is_border_row(y: int) -> bool:
        bright = 0
        dark = 0
        n = 0
        for x in range(0, w, step):
            r, g, b = img.getpixel((x, y))
            avg = (r + g + b) / 3
            n += 1
            if avg > hi:
                bright += 1
            elif avg < lo:
                dark += 1
        # Row is border if >80% of pixels are uniformly bright or dark
        return n > 0 and (bright / n > 0.8 or dark / n > 0.8)

    def is_border_col(x: int) -> bool:
        bright = 0
        dark = 0
        n = 0
        for y in range(0, h, step):
            r, g, b = img.getpixel((x, y))
            avg = (r + g + b) / 3
            n += 1
            if avg > hi:
                bright += 1
            elif avg < lo:
                dark += 1
        return n > 0 and (bright / n > 0.8 or dark / n > 0.8)

    # Scan WITHOUT breaking immediately — allow up to 3 transition rows
    # between dark edge and white border layers.
    max_gap = 3

    top = 0
    gap = 0
    for y in range(h // 3):
        if is_border_row(y):
            top = y + 1
            gap = 0
        else:
            gap += 1
            if gap > max_gap:
                break

    bottom = 0
    gap = 0
    for y in range(h - 1, h - h // 3, -1):
        if is_border_row(y):
            bottom = h - y
            gap = 0
        else:
            gap += 1
            if gap > max_gap:
                break

    left = 0
    gap = 0
    for x in range(w // 3):
        if is_border_col(x):
            left = x + 1
            gap = 0
        else:
            gap += 1
            if gap > max_gap:
                break

    right = 0
    gap = 0
    for x in range(w - 1, w - w // 3, -1):
        if is_border_col(x):
            right = w - x
            gap = 0
        else:
            gap += 1
            if gap > max_gap:
                break

    return top, bottom, left, right


def render_border_crop(source_path: Path, params: dict, img: Image.Image | None = None) -> Image.Image:
    """Detect any border (white or dark), then fit the largest 3:2 (or 2:3)
    rectangle inside the content area."""
    if img is None:
        img = Image.open(source_path)
        img.load()
        img = img.convert("RGB")
    w, h = img.size

    # Detect content bounds (inside any border — white or dark)
    det_top, det_bottom, det_left, det_right = _detect_border(img)

    # Also use DB values as hints — take the larger of each
    db_top = params.get("crop_top", 0)
    db_bottom = params.get("crop_bottom", 0)
    db_left = params.get("crop_left", 0)
    db_right = params.get("crop_right", 0)

    top = max(db_top, det_top)
    bottom = max(db_bottom, det_bottom)
    left = max(db_left, det_left)
    right = max(db_right, det_right)

    # Extra inset: film scans have noisy edges — crop 1.5% extra
    inset_h = max(int(h * 0.015), 4)
    inset_w = max(int(w * 0.015), 4)
    if top > 0:
        top += inset_h
    if bottom > 0:
        bottom += inset_h
    if left > 0:
        left += inset_w
    if right > 0:
        right += inset_w

    # Safety: don't crop more than 25% from any side
    top = min(top, h // 4)
    bottom = min(bottom, h // 4)
    left = min(left, w // 4)
    right = min(right, w // 4)

    content_left = left
    content_top = top
    content_right = w - right
    content_bottom = h - bottom
    content_w = content_right - content_left
    content_h = content_bottom - content_top

    if content_w <= 0 or content_h <= 0:
        return img

    # Fit largest 3:2 (landscape) or 2:3 (portrait) rectangle inside content
    target = 3 / 2 if content_w >= content_h else 2 / 3

    if content_w / content_h > target:
        fit_h = content_h
        fit_w = int(fit_h * target)
    else:
        fit_w = content_w
        fit_h = int(fit_w / target)

    # Center within content bounds
    cx = content_left + content_w // 2
    cy = content_top + content_h // 2
    crop_left = cx - fit_w // 2
    crop_top = cy - fit_h // 2

    return img.crop((crop_left, crop_top, crop_left + fit_w, crop_top + fit_h))


def render_gemma_crop(source_path: Path, params: dict, img: Image.Image | None = None) -> Image.Image:
    if img is None:
        img = Image.open(source_path)
        img.load()
        img = img.convert("RGB")
    w, h = img.size

    crop = params.get("crop", {})
    cx_pct = crop.get("center_x", 50) / 100.0
    cy_pct = crop.get("center_y", 50) / 100.0
    coverage = crop.get("coverage", 60) / 100.0

    # Parse ratio string like "3:2" to compute crop dimensions
    ratio_str = crop.get("ratio", "3:2")
    parts = ratio_str.split(":")
    rw, rh = float(parts[0]), float(parts[1])

    # Determine crop dimensions that fit within the image at the given coverage
    crop_area = w * h * coverage
    aspect = rw / rh
    crop_h = int((crop_area / aspect) ** 0.5)
    crop_w = int(crop_h * aspect)

    # Clamp to image bounds
    crop_w = min(crop_w, w)
    crop_h = min(crop_h, h)

    # Center point
    cx = int(cx_pct * w)
    cy = int(cy_pct * h)

    # Compute box, clamped to edges
    left = max(0, min(cx - crop_w // 2, w - crop_w))
    top = max(0, min(cy - crop_h // 2, h - crop_h))

    return img.crop((left, top, left + crop_w, top + crop_h))


def render_rotation(source_path: Path, rotation: str, img: Image.Image | None = None) -> Image.Image:
    if img is None:
        img = Image.open(source_path)
        img.load()
        img = img.convert("RGB")
    angles = {"cw90": -90, "ccw90": 90, "180": 180}
    angle = angles.get(rotation, 0)
    if angle:
        img = img.rotate(angle, expand=True)
    return img


def render_exposure(source_path: Path, img: Image.Image | None = None) -> Image.Image:
    if img is not None:
        return img
    img = Image.open(source_path)
    img.load()
    return img.convert("RGB")


def render_combined(source_path: Path, params: dict) -> Image.Image:
    """Apply all transforms in order: rotate -> border_crop -> exposure.
    params['transforms'] lists which transforms to apply.
    Each transform's specific params are stored under its key in params."""
    transforms = params.get("transforms", [])

    img = Image.open(source_path)
    img.load()
    img = img.convert("RGB")

    # 1. Rotate first (changes orientation before cropping)
    if "rotation" in transforms:
        rotation = params.get("rotation", {}).get("rotation", "")
        if rotation:
            img = render_rotation(source_path, rotation, img=img)

    # 2. Border crop (removes scan frame)
    if "border_crop" in transforms:
        img = render_border_crop(source_path, params.get("border_crop", {}), img=img)

    # 3. Gemma crop (AI-recommended crop — only if no border crop)
    if "gemma_crop" in transforms and "border_crop" not in transforms:
        img = render_gemma_crop(source_path, params.get("gemma_crop", {}), img=img)

    # 4. Exposure — use the pre-rendered enhanced file
    if "exposure" in transforms:
        exposure_path = params.get("exposure", {}).get("source_path")
        if exposure_path:
            exp_img = Image.open(exposure_path)
            exp_img.load()
            img = exp_img.convert("RGB")
            # Re-apply crop/rotation to the exposure version
            if "rotation" in transforms:
                rotation = params.get("rotation", {}).get("rotation", "")
                if rotation:
                    img = render_rotation(source_path, rotation, img=img)
            if "border_crop" in transforms:
                img = render_border_crop(source_path, params.get("border_crop", {}), img=img)

    return img


def save_preview(img: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Resize to fit within PREVIEW_MAX_EDGE
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > PREVIEW_MAX_EDGE:
        ratio = PREVIEW_MAX_EDGE / long_edge
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    img.save(str(output_path), format="JPEG", quality=PREVIEW_QUALITY, optimize=True)
