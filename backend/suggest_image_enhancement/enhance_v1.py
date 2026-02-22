#!/usr/bin/env python3
"""
enhance_engine.py — Per-image, camera-aware enhancement engine.

Computes and executes deterministic quality improvements for each photograph
using signals from pixel analysis (image_analysis table) and camera metadata.
No AI, no style transfer — pure signal-driven corrections: white balance,
exposure, contrast, shadow/highlight recovery, saturation, noise-aware sharpening.

Each image gets its own recipe computed from its measured pixel data and the
known characteristics of the camera that took it.

Usage:
    python3 enhance_engine.py                  # Process all images
    python3 enhance_engine.py --dry-run        # Compute plans only (no images)
    python3 enhance_engine.py --limit 20       # Process 20 images
    python3 enhance_engine.py --workers 4      # Override parallelism
    python3 enhance_engine.py --force          # Re-process already enhanced
    python3 enhance_engine.py --camera "Leica M8"  # Only one camera body
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

import database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = db.PROJECT_ROOT
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
ENHANCED_DIR = RENDERED_DIR / "enhanced" / "jpeg"
JPEG_QUALITY = 92

# Source tier for enhancement (2048px for review)
SOURCE_TIER = "display"
SOURCE_FORMAT = "jpeg"


# ---------------------------------------------------------------------------
# Camera Profiles — tuning parameters per camera body
# ---------------------------------------------------------------------------

@dataclass
class CameraProfile:
    """Per-camera tuning parameters derived from measured averages."""
    name: str
    wb_strength: float          # How aggressively to correct WB (0=none, 1=full)
    exposure_strength: float    # How aggressively to correct brightness
    shadow_threshold: float     # clip_low_pct above which to lift shadows
    highlight_threshold: float  # clip_high_pct above which to pull highlights
    saturation_boost_cap: float # Max saturation multiplier
    preserve_grain: bool        # If True, gentler sharpening (film)
    is_monochrome: bool         # Never touch color channels
    notes: str = ""


CAMERA_PROFILES = {
    "Leica M8": CameraProfile(
        name="Leica M8",
        wb_strength=0.5,           # Careful — some warmth is CCD character
        exposure_strength=0.8,
        shadow_threshold=8.0,
        highlight_threshold=3.0,
        saturation_boost_cap=1.15,
        preserve_grain=False,
        is_monochrome=False,
        notes="CCD IR sensitivity, magenta in darks",
    ),
    "Leica MP": CameraProfile(
        name="Leica MP",
        wb_strength=0.3,           # Preserve film warmth
        exposure_strength=0.5,     # Gentler — preserve exposure intent
        shadow_threshold=10.0,     # Film grain lives in shadows
        highlight_threshold=3.0,
        saturation_boost_cap=1.10, # Portra already vivid
        preserve_grain=True,
        is_monochrome=False,
        notes="Kodak Portra 400 VC, intentional grain",
    ),
    "Leica Monochrom": CameraProfile(
        name="Leica Monochrom",
        wb_strength=0.0,           # NEVER touch color — pure B&W sensor
        exposure_strength=0.7,
        shadow_threshold=30.0,     # Heavy shadow clipping is stylistic (avg 22.5%)
        highlight_threshold=3.0,
        saturation_boost_cap=1.0,  # No saturation ops
        preserve_grain=False,
        is_monochrome=True,
        notes="No Bayer filter, pure B&W sensor",
    ),
    "Canon G12": CameraProfile(
        name="Canon G12",
        wb_strength=0.7,           # Aggressive — worst auto WB
        exposure_strength=0.9,     # Often underexposed
        shadow_threshold=8.0,
        highlight_threshold=3.0,
        saturation_boost_cap=1.20, # Compact cameras tend flat
        preserve_grain=False,
        is_monochrome=False,
        notes="Worst auto WB, often underexposed",
    ),
    "DJI Osmo Pro": CameraProfile(
        name="DJI Osmo Pro",
        wb_strength=0.6,
        exposure_strength=0.8,
        shadow_threshold=8.0,
        highlight_threshold=3.0,
        saturation_boost_cap=1.15,
        preserve_grain=False,
        is_monochrome=False,
        notes="Action cam, decent starting point",
    ),
    "DJI Osmo Memo": CameraProfile(
        name="DJI Osmo Memo",
        wb_strength=0.6,
        exposure_strength=0.7,     # Often overexposed
        shadow_threshold=8.0,
        highlight_threshold=2.0,   # Lower threshold — catches overexposure
        saturation_boost_cap=1.15,
        preserve_grain=False,
        is_monochrome=False,
        notes="Often overexposed",
    ),
}

# Fallback profile for unknown cameras
DEFAULT_PROFILE = CameraProfile(
    name="Unknown",
    wb_strength=0.5,
    exposure_strength=0.7,
    shadow_threshold=8.0,
    highlight_threshold=3.0,
    saturation_boost_cap=1.15,
    preserve_grain=False,
    is_monochrome=False,
)


# ---------------------------------------------------------------------------
# Enhancement Plan — per-image recipe
# ---------------------------------------------------------------------------

@dataclass
class EnhancementPlan:
    """Computed recipe for enhancing a single image."""
    image_uuid: str
    camera_body: str
    is_monochrome: bool

    # Step 1: White Balance
    skip_wb: bool = False
    wb_correction_r: float = 1.0
    wb_correction_b: float = 1.0
    wb_reason: str = ""

    # Step 2: Exposure
    skip_exposure: bool = False
    gamma: float = 1.0
    exposure_reason: str = ""

    # Step 3: Shadow & Highlight Recovery
    shadow_lift: float = 0.0       # 0 = no lift, positive = amount to lift
    highlight_pull: float = 0.0    # 0 = no pull, positive = amount to pull
    sh_reason: str = ""

    # Step 4: Contrast
    skip_contrast: bool = False
    contrast_strength: float = 0.0  # 0 = none, 1 = full S-curve
    contrast_reason: str = ""

    # Step 5: Saturation
    skip_saturation: bool = False
    saturation_scale: float = 1.0
    saturation_reason: str = ""

    # Step 6: Sharpening
    sharpen_radius: float = 1.5
    sharpen_percent: float = 80.0
    sharpen_threshold: int = 2
    sharpen_reason: str = ""

    # Source metrics (for comparison)
    pre_brightness: float = 0.0
    pre_wb_shift_r: float = 0.0
    pre_contrast: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @property
    def steps_applied(self) -> List[str]:
        steps = []
        if not self.skip_wb:
            steps.append("wb")
        if not self.skip_exposure:
            steps.append("exposure")
        if self.shadow_lift > 0 or self.highlight_pull > 0:
            steps.append("shadows_highlights")
        if not self.skip_contrast:
            steps.append("contrast")
        if not self.skip_saturation:
            steps.append("saturation")
        steps.append("sharpen")  # Always applied
        return steps


# ---------------------------------------------------------------------------
# Plan computation — pure signal math, no image loading
# ---------------------------------------------------------------------------

def compute_plan(image_uuid: str, pixel_data: Dict[str, Any],
                 camera_body: Optional[str], is_mono: bool) -> EnhancementPlan:
    """Compute the enhancement recipe for a single image from its signals."""

    profile = CAMERA_PROFILES.get(camera_body or "", DEFAULT_PROFILE)

    # Override monochrome from either DB flag or profile
    is_monochrome = is_mono or profile.is_monochrome

    plan = EnhancementPlan(
        image_uuid=image_uuid,
        camera_body=camera_body or "Unknown",
        is_monochrome=is_monochrome,
        pre_brightness=pixel_data.get("mean_brightness", 0.0),
        pre_wb_shift_r=pixel_data.get("wb_shift_r", 0.0),
        pre_contrast=pixel_data.get("contrast_ratio", 0.0),
    )

    # ---- Step 1: White Balance Correction ----
    wb_r = pixel_data.get("wb_shift_r", 0.0)
    wb_b = pixel_data.get("wb_shift_b", 0.0)

    if is_monochrome:
        plan.skip_wb = True
        plan.wb_reason = "Monochrome sensor — no color correction"
    elif abs(wb_r) < 0.02 and abs(wb_b) < 0.02:
        plan.skip_wb = True
        plan.wb_reason = "Negligible WB shift (< 0.02)"
    else:
        strength = profile.wb_strength
        plan.wb_correction_r = 1.0 - wb_r * strength
        plan.wb_correction_b = 1.0 - wb_b * strength
        # Clamp corrections to reasonable range
        plan.wb_correction_r = max(0.8, min(1.2, plan.wb_correction_r))
        plan.wb_correction_b = max(0.8, min(1.2, plan.wb_correction_b))
        plan.wb_reason = (f"WB shift r={wb_r:+.3f} b={wb_b:+.3f}, "
                          f"strength={strength} ({profile.name})")

    # ---- Step 2: Exposure / Brightness Correction ----
    brightness = pixel_data.get("mean_brightness", 110.0)
    is_low_key = pixel_data.get("is_low_key", 0)
    is_high_key = pixel_data.get("is_high_key", 0)

    if is_low_key:
        plan.skip_exposure = True
        plan.exposure_reason = "Intentional low-key exposure — preserving mood"
    elif is_high_key:
        plan.skip_exposure = True
        plan.exposure_reason = "Intentional high-key exposure — preserving mood"
    elif brightness < 70:
        # Underexposed — lift with gamma < 1.0
        # Scale gamma correction by camera's exposure strength
        deficit = (110 - brightness) / 110  # How far below target
        gamma_correction = 1.0 - deficit * 0.3 * profile.exposure_strength
        plan.gamma = max(0.70, min(0.95, gamma_correction))
        plan.exposure_reason = (f"Underexposed (brightness={brightness:.0f}), "
                                f"gamma={plan.gamma:.2f}")
    elif brightness > 150:
        # Overexposed — darken with gamma > 1.0
        excess = (brightness - 120) / 120  # How far above target
        gamma_correction = 1.0 + excess * 0.3 * profile.exposure_strength
        plan.gamma = max(1.05, min(1.30, gamma_correction))
        plan.exposure_reason = (f"Overexposed (brightness={brightness:.0f}), "
                                f"gamma={plan.gamma:.2f}")
    elif brightness < 90:
        # Slightly underexposed — gentle lift
        deficit = (110 - brightness) / 110
        gamma_correction = 1.0 - deficit * 0.2 * profile.exposure_strength
        plan.gamma = max(0.85, min(0.98, gamma_correction))
        plan.exposure_reason = (f"Slightly dark (brightness={brightness:.0f}), "
                                f"gamma={plan.gamma:.2f}")
    elif brightness > 135:
        # Slightly overexposed — gentle darken
        excess = (brightness - 120) / 120
        gamma_correction = 1.0 + excess * 0.15 * profile.exposure_strength
        plan.gamma = max(1.02, min(1.15, gamma_correction))
        plan.exposure_reason = (f"Slightly bright (brightness={brightness:.0f}), "
                                f"gamma={plan.gamma:.2f}")
    else:
        plan.skip_exposure = True
        plan.exposure_reason = f"Brightness OK ({brightness:.0f})"

    # ---- Step 3: Shadow & Highlight Recovery ----
    clip_low = pixel_data.get("clip_low_pct", 0.0)
    clip_high = pixel_data.get("clip_high_pct", 0.0)

    shadow_thresh = profile.shadow_threshold
    highlight_thresh = profile.highlight_threshold

    if clip_low > shadow_thresh:
        # Lift shadows proportionally to how much is clipped
        excess = clip_low - shadow_thresh
        plan.shadow_lift = min(0.4, excess * 0.03)  # Max 40% lift
        plan.sh_reason = f"Shadow clip {clip_low:.1f}% > {shadow_thresh}%"
    if clip_high > highlight_thresh:
        excess = clip_high - highlight_thresh
        plan.highlight_pull = min(0.3, excess * 0.02)  # Max 30% pull
        reason = f"Highlight clip {clip_high:.1f}% > {highlight_thresh}%"
        plan.sh_reason = (plan.sh_reason + "; " + reason) if plan.sh_reason else reason

    if not plan.sh_reason:
        plan.sh_reason = "No recovery needed"

    # ---- Step 4: Contrast Enhancement ----
    contrast = pixel_data.get("contrast_ratio", 0.85)

    if contrast < 0.55:
        plan.contrast_strength = 0.6  # Strong S-curve
        plan.contrast_reason = f"Very low contrast ({contrast:.2f})"
    elif contrast < 0.75:
        plan.contrast_strength = 0.4  # Moderate S-curve
        plan.contrast_reason = f"Low contrast ({contrast:.2f})"
    elif contrast < 0.92:
        plan.contrast_strength = 0.15  # Mild S-curve
        plan.contrast_reason = f"Adequate contrast ({contrast:.2f}), mild boost"
    else:
        plan.skip_contrast = True
        plan.contrast_reason = f"Good contrast ({contrast:.2f})"

    # ---- Step 5: Saturation Adjustment ----
    mean_sat = pixel_data.get("mean_saturation", 0.3)

    if is_monochrome:
        plan.skip_saturation = True
        plan.saturation_reason = "Monochrome — no saturation ops"
    elif mean_sat < 0.15:
        boost = min(profile.saturation_boost_cap, 1.15)
        plan.saturation_scale = boost
        plan.saturation_reason = f"Undersaturated ({mean_sat:.2f}), boost to {boost:.2f}x"
    elif mean_sat > 0.50:
        plan.saturation_scale = 0.95
        plan.saturation_reason = f"Oversaturated ({mean_sat:.2f}), reduce to 0.95x"
    elif mean_sat < 0.25:
        # Slightly undersaturated
        boost = min(profile.saturation_boost_cap, 1.08)
        plan.saturation_scale = boost
        plan.saturation_reason = f"Slightly low saturation ({mean_sat:.2f}), boost to {boost:.2f}x"
    else:
        plan.skip_saturation = True
        plan.saturation_reason = f"Saturation OK ({mean_sat:.2f})"

    # ---- Step 6: Noise-Aware Sharpening ----
    noise = pixel_data.get("noise_estimate", 1.5)

    if profile.preserve_grain:
        # Film: gentle sharpening to preserve grain texture
        plan.sharpen_radius = 0.8
        plan.sharpen_percent = 40.0
        plan.sharpen_threshold = 5
        plan.sharpen_reason = f"Film grain (noise={noise:.1f}), preserving texture"
    elif is_monochrome:
        # B&W benefits from crisp edges
        plan.sharpen_radius = 1.3
        plan.sharpen_percent = 70.0
        plan.sharpen_threshold = 2
        plan.sharpen_reason = f"Monochrome (noise={noise:.1f}), crisp edges"
    elif noise < 2.0:
        # Clean digital — standard sharpening
        plan.sharpen_radius = 1.5
        plan.sharpen_percent = 80.0
        plan.sharpen_threshold = 2
        plan.sharpen_reason = f"Clean digital (noise={noise:.1f})"
    elif noise < 3.0:
        # Noisy digital — gentler
        plan.sharpen_radius = 1.2
        plan.sharpen_percent = 60.0
        plan.sharpen_threshold = 3
        plan.sharpen_reason = f"Noisy digital (noise={noise:.1f}), reduced sharpening"
    else:
        # Very noisy — minimal
        plan.sharpen_radius = 0.8
        plan.sharpen_percent = 40.0
        plan.sharpen_threshold = 5
        plan.sharpen_reason = f"High noise ({noise:.1f}), minimal sharpening"

    return plan


# ---------------------------------------------------------------------------
# Enhancement execution — image processing
# ---------------------------------------------------------------------------

def _correct_white_balance(arr: np.ndarray, plan: EnhancementPlan) -> np.ndarray:
    """Step 1: Grey-world channel scaling for WB correction."""
    if plan.skip_wb:
        return arr

    result = arr.copy().astype(np.float64)
    result[:, :, 0] *= plan.wb_correction_r  # Red channel
    # Green channel untouched (reference)
    result[:, :, 2] *= plan.wb_correction_b  # Blue channel

    return np.clip(result, 0, 255).astype(np.uint8)


def _correct_exposure(arr: np.ndarray, plan: EnhancementPlan) -> np.ndarray:
    """Step 2: Gamma correction for brightness."""
    if plan.skip_exposure:
        return arr

    # Normalize to 0-1, apply gamma, scale back
    result = arr.astype(np.float64) / 255.0
    result = np.power(result, plan.gamma)
    result = (result * 255.0)

    return np.clip(result, 0, 255).astype(np.uint8)


def _recover_shadows_highlights(arr: np.ndarray, plan: EnhancementPlan) -> np.ndarray:
    """Step 3: Selective tone curve for shadow/highlight recovery."""
    if plan.shadow_lift == 0 and plan.highlight_pull == 0:
        return arr

    result = arr.astype(np.float64)

    # Compute luminance for masking
    luma = 0.299 * result[:, :, 0] + 0.587 * result[:, :, 1] + 0.114 * result[:, :, 2]

    if plan.shadow_lift > 0:
        # Lift shadows: pixels below 64 get boosted proportionally
        shadow_mask = luma < 64
        if np.any(shadow_mask):
            # Smooth lift: more lift for darker pixels
            lift_amount = plan.shadow_lift * (64 - luma[shadow_mask]) / 64.0
            for ch in range(3):
                channel = result[:, :, ch]
                channel[shadow_mask] += channel[shadow_mask] * lift_amount
                result[:, :, ch] = channel

    if plan.highlight_pull > 0:
        # Pull highlights: pixels above 220 get gently reduced
        highlight_mask = luma > 220
        if np.any(highlight_mask):
            # Smooth pull: more reduction for brighter pixels
            pull_amount = plan.highlight_pull * (luma[highlight_mask] - 220) / 35.0
            for ch in range(3):
                channel = result[:, :, ch]
                channel[highlight_mask] -= channel[highlight_mask] * pull_amount
                result[:, :, ch] = channel

    return np.clip(result, 0, 255).astype(np.uint8)


def _enhance_contrast(arr: np.ndarray, plan: EnhancementPlan) -> np.ndarray:
    """Step 4: Adaptive S-curve in luminance (LAB L channel)."""
    if plan.skip_contrast:
        return arr

    result = arr.astype(np.float64)

    # Work in luminance space to preserve color
    luma = 0.299 * result[:, :, 0] + 0.587 * result[:, :, 1] + 0.114 * result[:, :, 2]

    # S-curve: midtone contrast boost
    # Using a smooth sigmoid-like curve centered at 128
    strength = plan.contrast_strength
    normalized = luma / 255.0

    # S-curve formula: x + strength * sin(2*pi*x) / (2*pi)
    # This preserves 0 and 1 endpoints, boosts midtone separation
    curved = normalized + strength * 0.15 * np.sin(np.pi * normalized * 2) / (np.pi * 2)
    curved = np.clip(curved, 0, 1) * 255.0

    # Apply luminance change as a ratio to all channels (preserves color)
    ratio = np.ones_like(luma)
    safe_mask = luma > 1.0  # Avoid divide by zero
    ratio[safe_mask] = curved[safe_mask] / luma[safe_mask]
    ratio = np.clip(ratio, 0.5, 2.0)  # Safety clamp

    for ch in range(3):
        result[:, :, ch] *= ratio

    return np.clip(result, 0, 255).astype(np.uint8)


def _adjust_saturation(arr: np.ndarray, plan: EnhancementPlan) -> np.ndarray:
    """Step 5: HSV saturation scaling."""
    if plan.skip_saturation:
        return arr

    # Convert to PIL for HSV conversion
    img = Image.fromarray(arr, "RGB")
    hsv = img.convert("HSV")
    hsv_arr = np.array(hsv, dtype=np.float64)

    # Scale saturation channel
    hsv_arr[:, :, 1] *= plan.saturation_scale
    hsv_arr[:, :, 1] = np.clip(hsv_arr[:, :, 1], 0, 255)

    hsv_result = Image.fromarray(hsv_arr.astype(np.uint8), "HSV")
    return np.array(hsv_result.convert("RGB"))


def _sharpen(img: Image.Image, plan: EnhancementPlan) -> Image.Image:
    """Step 6: Pillow UnsharpMask with adaptive parameters."""
    return img.filter(ImageFilter.UnsharpMask(
        radius=plan.sharpen_radius,
        percent=int(plan.sharpen_percent),
        threshold=plan.sharpen_threshold,
    ))


def execute_plan(plan: EnhancementPlan, source_path: str) -> Optional[Image.Image]:
    """Execute all 6 enhancement steps on an image. Returns enhanced PIL.Image."""
    try:
        img = Image.open(source_path)
        img = img.convert("RGB")
        arr = np.array(img, dtype=np.uint8)

        # Steps 1-5: numpy array operations
        arr = _correct_white_balance(arr, plan)
        arr = _correct_exposure(arr, plan)
        arr = _recover_shadows_highlights(arr, plan)
        arr = _enhance_contrast(arr, plan)
        arr = _adjust_saturation(arr, plan)

        # Step 6: Pillow sharpening
        img = Image.fromarray(arr, "RGB")
        img = _sharpen(img, plan)

        return img

    except Exception as e:
        print(f"  Error enhancing {plan.image_uuid}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Post-enhancement metrics
# ---------------------------------------------------------------------------

def compute_post_metrics(img: Image.Image) -> Dict[str, float]:
    """Compute key metrics on the enhanced image for comparison."""
    arr = np.array(img, dtype=np.float64)
    luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    mean_r = float(np.mean(arr[:, :, 0]))
    mean_g = float(np.mean(arr[:, :, 1]))
    mean_b = float(np.mean(arr[:, :, 2]))
    grey_mean = (mean_r + mean_g + mean_b) / 3.0

    p2, p98 = np.percentile(luma, [2, 98])
    contrast = float((p98 - p2) / (p98 + p2)) if (p98 + p2) > 0 else 0.0

    return {
        "post_brightness": float(np.mean(luma)),
        "post_wb_shift_r": float((mean_r - grey_mean) / grey_mean) if grey_mean > 0 else 0.0,
        "post_contrast": contrast,
    }


# ---------------------------------------------------------------------------
# Worker process for multiprocessing
# ---------------------------------------------------------------------------

def _process_one(args: Tuple[str, str, str]) -> Optional[Dict[str, Any]]:
    """Worker: enhance one image. Returns result dict or None."""
    plan_json, source_path, output_path = args

    plan_dict = json.loads(plan_json)
    plan = EnhancementPlan(**{k: v for k, v in plan_dict.items()
                              if k in EnhancementPlan.__dataclass_fields__})

    enhanced = execute_plan(plan, source_path)
    if enhanced is None:
        return None

    # Save enhanced image
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    enhanced.save(output_path, "JPEG", quality=JPEG_QUALITY, subsampling=0)

    # Compute post metrics
    post = compute_post_metrics(enhanced)

    return {
        "image_uuid": plan.image_uuid,
        "output_path": output_path,
        "post_brightness": post["post_brightness"],
        "post_wb_shift_r": post["post_wb_shift_r"],
        "post_contrast": post["post_contrast"],
        "file_size": Path(output_path).stat().st_size,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Per-image camera-aware enhancement engine")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute plans only, don't process images")
    parser.add_argument("--limit", type=int, default=0, metavar="N",
                        help="Process only N images")
    parser.add_argument("--workers", type=int,
                        default=max(1, (os.cpu_count() or 4) - 2),
                        help="Parallel workers (default: cpu_count - 2)")
    parser.add_argument("--force", action="store_true",
                        help="Re-process already enhanced images")
    parser.add_argument("--camera", type=str, default=None,
                        help="Only process images from this camera body")
    args = parser.parse_args()

    conn = db.get_connection()
    now_str = datetime.now(timezone.utc).isoformat()

    # ---- Gather images with pixel analysis + display tier path ----
    camera_filter = ""
    params = [SOURCE_TIER, SOURCE_FORMAT]  # type: List[Any]
    if args.camera:
        camera_filter = "AND i.camera_body = ?"
        params.append(args.camera)

    if not args.force:
        skip_clause = """AND NOT EXISTS (
            SELECT 1 FROM enhancement_plans ep
            WHERE ep.image_uuid = i.uuid AND ep.status IN ('enhanced', 'accepted')
        )"""
    else:
        skip_clause = ""

    rows = conn.execute(f"""
        SELECT
            i.uuid, i.camera_body, i.is_monochrome,
            ia.mean_brightness, ia.std_brightness,
            ia.clip_low_pct, ia.clip_high_pct, ia.dynamic_range,
            ia.mean_saturation, ia.mean_r, ia.mean_g, ia.mean_b,
            ia.wb_shift_r, ia.wb_shift_b, ia.color_cast,
            ia.contrast_ratio, ia.noise_estimate,
            ia.is_low_key, ia.is_high_key,
            ia.shadow_pct, ia.midtone_pct, ia.highlight_pct,
            ia.shadow_mean, ia.midtone_mean, ia.highlight_mean,
            t.local_path as source_path
        FROM images i
        JOIN image_analysis ia ON i.uuid = ia.image_uuid
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = ? AND t.format = ? AND t.variant_id IS NULL
        WHERE ia.mean_brightness IS NOT NULL
            {camera_filter}
            {skip_clause}
        ORDER BY i.uuid
    """, params).fetchall()

    work = [dict(r) for r in rows]
    if args.limit:
        work = work[:args.limit]

    total_images = conn.execute("SELECT COUNT(*) as c FROM images").fetchone()["c"]
    already_enhanced = conn.execute(
        "SELECT COUNT(*) as c FROM enhancement_plans WHERE status = 'enhanced'"
    ).fetchone()["c"]

    print(f"Enhancement Engine")
    print(f"{'='*60}")
    print(f"Images: {total_images} total | {already_enhanced} enhanced | "
          f"{len(work)} to process")
    print(f"Mode: {'DRY RUN (plans only)' if args.dry_run else 'FULL PROCESSING'}")
    print(f"Workers: {args.workers}")
    if args.camera:
        print(f"Camera filter: {args.camera}")
    print(f"{'='*60}")

    if not work:
        print("Nothing to process.")
        conn.close()
        return

    # ---- Phase 1: Compute plans ----
    print(f"\nPhase 1: Computing enhancement plans for {len(work)} images...")
    plans_start = time.time()
    plans = []  # type: List[Tuple[EnhancementPlan, str]]

    for item in work:
        pixel_data = {k: item[k] for k in item if k not in
                      ("uuid", "camera_body", "is_monochrome", "source_path")}
        plan = compute_plan(
            image_uuid=item["uuid"],
            pixel_data=pixel_data,
            camera_body=item["camera_body"],
            is_mono=bool(item["is_monochrome"]),
        )
        plans.append((plan, item["source_path"]))

        # Save plan to DB
        output_path = str(ENHANCED_DIR / f"{item['uuid']}.jpg")
        conn.execute("""
            INSERT INTO enhancement_plans (
                image_uuid, version, camera_body, plan_json,
                wb_correction_r, wb_correction_b, gamma,
                shadow_lift, highlight_pull, contrast_strength,
                saturation_scale, sharpen_radius, sharpen_percent,
                status, source_tier, output_path,
                pre_brightness, pre_wb_shift_r, pre_contrast,
                planned_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(image_uuid) DO UPDATE SET
                version = enhancement_plans.version + 1,
                camera_body=excluded.camera_body, plan_json=excluded.plan_json,
                wb_correction_r=excluded.wb_correction_r,
                wb_correction_b=excluded.wb_correction_b,
                gamma=excluded.gamma, shadow_lift=excluded.shadow_lift,
                highlight_pull=excluded.highlight_pull,
                contrast_strength=excluded.contrast_strength,
                saturation_scale=excluded.saturation_scale,
                sharpen_radius=excluded.sharpen_radius,
                sharpen_percent=excluded.sharpen_percent,
                status='planned', source_tier=excluded.source_tier,
                output_path=excluded.output_path,
                pre_brightness=excluded.pre_brightness,
                pre_wb_shift_r=excluded.pre_wb_shift_r,
                pre_contrast=excluded.pre_contrast,
                planned_at=excluded.planned_at
        """, (
            item["uuid"], item["camera_body"], plan.to_json(),
            plan.wb_correction_r, plan.wb_correction_b, plan.gamma,
            plan.shadow_lift, plan.highlight_pull, plan.contrast_strength,
            plan.saturation_scale, plan.sharpen_radius, plan.sharpen_percent,
            SOURCE_TIER, output_path,
            plan.pre_brightness, plan.pre_wb_shift_r, plan.pre_contrast,
            now_str,
        ))

    conn.commit()
    plans_elapsed = time.time() - plans_start
    print(f"  {len(plans)} plans computed in {plans_elapsed:.1f}s")

    # ---- Print plan summary ----
    _print_plan_summary(plans)

    if args.dry_run:
        print("\n[DRY RUN] Plans saved to DB. No images processed.")
        conn.close()
        return

    # ---- Phase 2: Execute plans (multiprocessing) ----
    print(f"\nPhase 2: Enhancing {len(plans)} images with {args.workers} workers...")
    run_id = db.start_run(conn, "enhance", {
        "workers": args.workers, "limit": args.limit,
        "camera": args.camera, "force": args.force,
    })
    enhance_start = time.time()
    completed = 0
    errors = 0

    # Prepare work items for pool
    pool_work = []
    for plan, source_path in plans:
        output_path = str(ENHANCED_DIR / f"{plan.image_uuid}.jpg")
        pool_work.append((plan.to_json(), source_path, output_path))

    with Pool(processes=args.workers) as pool:
        for result in pool.imap_unordered(_process_one, pool_work):
            if result is None:
                errors += 1
                continue

            # Update DB with results
            conn.execute("""
                UPDATE enhancement_plans SET
                    status = 'enhanced',
                    output_path = ?,
                    post_brightness = ?,
                    post_wb_shift_r = ?,
                    post_contrast = ?,
                    enhanced_at = ?
                WHERE image_uuid = ?
            """, (
                result["output_path"],
                result["post_brightness"],
                result["post_wb_shift_r"],
                result["post_contrast"],
                now_str,
                result["image_uuid"],
            ))
            completed += 1

            if completed % 100 == 0:
                conn.commit()
                elapsed = time.time() - enhance_start
                rate = completed / elapsed
                remaining = (len(plans) - completed - errors) / rate if rate > 0 else 0
                print(f"  {completed}/{len(plans)} enhanced "
                      f"({rate:.1f}/s, ~{remaining:.0f}s remaining)")

    conn.commit()
    elapsed = time.time() - enhance_start
    db.finish_run(conn, run_id, images_processed=completed, images_failed=errors)

    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.1f}s")
    print(f"Enhanced: {completed} | Errors: {errors}")
    if completed > 0:
        print(f"Rate: {completed/elapsed:.1f} images/s")

    # ---- Print post-enhancement comparison ----
    _print_comparison(conn)

    conn.close()


def _print_plan_summary(plans: List[Tuple[EnhancementPlan, str]]) -> None:
    """Print summary of what the plans will do."""
    camera_counts = {}  # type: Dict[str, int]
    step_counts = {"wb": 0, "exposure": 0, "shadows_highlights": 0,
                   "contrast": 0, "saturation": 0, "sharpen": 0}

    for plan, _ in plans:
        cam = plan.camera_body
        camera_counts[cam] = camera_counts.get(cam, 0) + 1
        for step in plan.steps_applied:
            step_counts[step] += 1

    total = len(plans)
    print(f"\n--- Plan Summary ({total} images) ---")
    print(f"  By camera:")
    for cam, cnt in sorted(camera_counts.items(), key=lambda x: -x[1]):
        print(f"    {cam:20} {cnt:5} ({cnt/total*100:.0f}%)")

    print(f"  Steps applied:")
    for step, cnt in step_counts.items():
        print(f"    {step:25} {cnt:5} ({cnt/total*100:.0f}%)")


def _print_comparison(conn) -> None:
    """Print before/after metrics by camera."""
    rows = conn.execute("""
        SELECT camera_body,
               COUNT(*) as cnt,
               AVG(pre_brightness) as pre_b,
               AVG(post_brightness) as post_b,
               AVG(pre_wb_shift_r) as pre_wb,
               AVG(post_wb_shift_r) as post_wb,
               AVG(pre_contrast) as pre_c,
               AVG(post_contrast) as post_c
        FROM enhancement_plans
        WHERE status = 'enhanced'
        GROUP BY camera_body
        ORDER BY cnt DESC
    """).fetchall()

    if not rows:
        return

    print(f"\n--- Before/After by Camera ---")
    print(f"  {'Camera':20} {'Count':>6}  "
          f"{'Bright Pre':>10} {'Post':>6}  "
          f"{'WB_R Pre':>8} {'Post':>6}  "
          f"{'Contrast Pre':>12} {'Post':>6}")
    for r in rows:
        print(f"  {r['camera_body'] or 'Unknown':20} {r['cnt']:6}  "
              f"{r['pre_b']:10.1f} {r['post_b']:6.1f}  "
              f"{r['pre_wb']:+8.3f} {r['post_wb']:+6.3f}  "
              f"{r['pre_c']:12.3f} {r['post_c']:6.3f}")


if __name__ == "__main__":
    main()
