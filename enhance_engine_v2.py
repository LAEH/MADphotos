#!/usr/bin/env python3
"""
enhance_engine_v2.py — Signal-aware per-image enhancement engine.

V2 uses ALL available signals to make smarter editing decisions:
- Depth estimation  → foreground/background-aware processing
- Scene classification → scene-adaptive color grading and contrast
- Style classification → style-specific processing intensity
- Gemini analysis → vibe/mood-aware toning, AI exposure assessment
- Face detection → face-aware exposure and skin tone protection
- Pixel analysis → measured brightness, WB, contrast, noise (same as v1)
- Camera profiles → camera-specific tuning (same as v1)

Output: rendered/enhanced_v2/jpeg/{uuid}.jpg

Usage:
    python3 enhance_engine_v2.py                 # Process all images
    python3 enhance_engine_v2.py --dry-run       # Compute plans only
    python3 enhance_engine_v2.py --limit 100     # Process N images
    python3 enhance_engine_v2.py --workers 4     # Override parallelism
    python3 enhance_engine_v2.py --force          # Re-process existing
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

import mad_database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
RENDERED_DIR = BASE_DIR / "rendered"
ENHANCED_V2_DIR = RENDERED_DIR / "enhanced_v2" / "jpeg"
JPEG_QUALITY = 92

SOURCE_TIER = "display"
SOURCE_FORMAT = "jpeg"


# ---------------------------------------------------------------------------
# Camera Profiles (same as v1)
# ---------------------------------------------------------------------------

@dataclass
class CameraProfile:
    name: str
    wb_strength: float
    exposure_strength: float
    shadow_threshold: float
    highlight_threshold: float
    saturation_boost_cap: float
    preserve_grain: bool
    is_monochrome: bool
    notes: str = ""


CAMERA_PROFILES = {
    "Leica M8": CameraProfile(
        name="Leica M8", wb_strength=0.5, exposure_strength=0.8,
        shadow_threshold=8.0, highlight_threshold=3.0,
        saturation_boost_cap=1.15, preserve_grain=False, is_monochrome=False,
        notes="CCD IR sensitivity, magenta in darks",
    ),
    "Leica MP": CameraProfile(
        name="Leica MP", wb_strength=0.3, exposure_strength=0.5,
        shadow_threshold=10.0, highlight_threshold=3.0,
        saturation_boost_cap=1.10, preserve_grain=True, is_monochrome=False,
        notes="Kodak Portra 400 VC, intentional grain",
    ),
    "Leica Monochrom": CameraProfile(
        name="Leica Monochrom", wb_strength=0.0, exposure_strength=0.7,
        shadow_threshold=30.0, highlight_threshold=3.0,
        saturation_boost_cap=1.0, preserve_grain=False, is_monochrome=True,
        notes="No Bayer filter, pure B&W sensor",
    ),
    "Canon G12": CameraProfile(
        name="Canon G12", wb_strength=0.7, exposure_strength=0.9,
        shadow_threshold=8.0, highlight_threshold=3.0,
        saturation_boost_cap=1.20, preserve_grain=False, is_monochrome=False,
        notes="Worst auto WB, often underexposed",
    ),
    "DJI Osmo Pro": CameraProfile(
        name="DJI Osmo Pro", wb_strength=0.6, exposure_strength=0.8,
        shadow_threshold=8.0, highlight_threshold=3.0,
        saturation_boost_cap=1.15, preserve_grain=False, is_monochrome=False,
    ),
    "DJI Osmo Memo": CameraProfile(
        name="DJI Osmo Memo", wb_strength=0.6, exposure_strength=0.7,
        shadow_threshold=8.0, highlight_threshold=2.0,
        saturation_boost_cap=1.15, preserve_grain=False, is_monochrome=False,
    ),
}

DEFAULT_PROFILE = CameraProfile(
    name="Unknown", wb_strength=0.5, exposure_strength=0.7,
    shadow_threshold=8.0, highlight_threshold=3.0,
    saturation_boost_cap=1.15, preserve_grain=False, is_monochrome=False,
)


# ---------------------------------------------------------------------------
# Scene-based adjustments
# ---------------------------------------------------------------------------

# Scenes that benefit from warmer tones
WARM_SCENES = {
    "bedroom", "living_room", "dining_room", "kitchen", "restaurant",
    "bar", "coffee_shop", "hotel_room", "temple", "church",
    "sunset", "campfire", "fireplace",
}

# Scenes that benefit from cooler / natural tones
COOL_SCENES = {
    "mountain", "glacier", "ocean", "lake", "waterfall", "river",
    "snow", "ice", "arctic", "pond", "swimming_pool",
}

# Scenes needing extra shadow lift (typically dark interiors)
DARK_SCENES = {
    "basement", "tunnel", "cave", "cellar", "subway",
    "alley", "bar", "nightclub", "theater",
}

# Scenes needing highlight protection (bright outdoor)
BRIGHT_SCENES = {
    "beach", "desert", "snow", "ski_slope", "glacier",
    "sky", "cloud",
}

# High-contrast scenes
HIGH_CONTRAST_SCENES = {
    "street", "alley", "crosswalk", "highway", "parking_lot",
    "bridge", "skyscraper", "downtown", "building_facade",
}

# Nature scenes that benefit from saturation boost
NATURE_SCENES = {
    "forest", "garden", "park", "field", "meadow", "jungle",
    "mountain", "valley", "lake", "ocean", "beach", "waterfall",
    "flower", "tree",
}


# ---------------------------------------------------------------------------
# Style-based multipliers
# ---------------------------------------------------------------------------

STYLE_ADJUSTMENTS = {
    "Street Photography": {"contrast_mult": 1.3, "saturation_mult": 0.92, "sharpen_mult": 1.2},
    "Documentary": {"contrast_mult": 1.2, "saturation_mult": 0.95, "sharpen_mult": 1.1},
    "Portrait": {"contrast_mult": 0.8, "saturation_mult": 1.0, "sharpen_mult": 0.7},
    "Landscape": {"contrast_mult": 1.1, "saturation_mult": 1.15, "sharpen_mult": 1.1},
    "Architecture": {"contrast_mult": 1.15, "saturation_mult": 0.95, "sharpen_mult": 1.3},
    "Abstract": {"contrast_mult": 1.3, "saturation_mult": 1.1, "sharpen_mult": 1.0},
    "Still Life": {"contrast_mult": 1.05, "saturation_mult": 1.05, "sharpen_mult": 1.0},
    "Night Photography": {"contrast_mult": 1.2, "saturation_mult": 0.9, "sharpen_mult": 0.8},
    "Travel": {"contrast_mult": 1.05, "saturation_mult": 1.1, "sharpen_mult": 1.0},
    "Nature": {"contrast_mult": 1.0, "saturation_mult": 1.15, "sharpen_mult": 1.0},
    "Macro": {"contrast_mult": 1.1, "saturation_mult": 1.05, "sharpen_mult": 1.3},
}


# ---------------------------------------------------------------------------
# Vibe-based mood adjustments
# ---------------------------------------------------------------------------

WARM_VIBES = {
    "warm", "cozy", "intimate", "romantic", "golden", "nostalgic",
    "tender", "gentle", "peaceful", "serene",
}

COOL_VIBES = {
    "cool", "cold", "stark", "clinical", "industrial", "metallic",
    "icy", "frozen", "sterile",
}

MOODY_VIBES = {
    "moody", "dark", "dramatic", "mysterious", "somber", "brooding",
    "melancholic", "gloomy", "noir", "ominous", "haunting",
}

VIBRANT_VIBES = {
    "vibrant", "energetic", "lively", "colorful", "bold", "dynamic",
    "playful", "joyful", "festive", "bright",
}


# ---------------------------------------------------------------------------
# V2 Enhancement Plan
# ---------------------------------------------------------------------------

@dataclass
class EnhancementPlanV2:
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
    shadow_lift: float = 0.0
    highlight_pull: float = 0.0
    sh_reason: str = ""

    # Step 4: Contrast
    skip_contrast: bool = False
    contrast_strength: float = 0.0
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

    # Signal annotations (for DB storage)
    depth_adjustment: str = ""
    scene_adjustment: str = ""
    style_adjustment: str = ""
    vibe_adjustment: str = ""
    face_adjustment: str = ""

    # Pre-metrics
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
        steps.append("sharpen")
        return steps


# ---------------------------------------------------------------------------
# Plan computation — signal-aware
# ---------------------------------------------------------------------------

def compute_plan_v2(
    image_uuid: str,
    pixel_data: Dict[str, Any],
    camera_body: Optional[str],
    is_mono: bool,
    depth_data: Optional[Dict[str, Any]],
    scene_data: Optional[Dict[str, Any]],
    style_data: Optional[Dict[str, Any]],
    gemini_data: Optional[Dict[str, Any]],
    face_count: int,
) -> EnhancementPlanV2:
    """Compute signal-aware enhancement recipe for one image."""

    profile = CAMERA_PROFILES.get(camera_body or "", DEFAULT_PROFILE)
    is_monochrome = is_mono or profile.is_monochrome

    plan = EnhancementPlanV2(
        image_uuid=image_uuid,
        camera_body=camera_body or "Unknown",
        is_monochrome=is_monochrome,
        pre_brightness=pixel_data.get("mean_brightness", 0.0),
        pre_wb_shift_r=pixel_data.get("wb_shift_r", 0.0),
        pre_contrast=pixel_data.get("contrast_ratio", 0.0),
    )

    # --- Parse signals ---
    scene_name = (scene_data or {}).get("scene_1", "").lower().replace("/", "_").replace(" ", "_")
    style_name = (style_data or {}).get("style", "")
    style_mults = STYLE_ADJUSTMENTS.get(style_name, {"contrast_mult": 1.0, "saturation_mult": 1.0, "sharpen_mult": 1.0})
    near_pct = (depth_data or {}).get("near_pct", 33.0) or 33.0
    far_pct = (depth_data or {}).get("far_pct", 33.0) or 33.0

    vibes = []
    time_of_day = ""
    gemini_exposure = ""
    if gemini_data:
        vibe_str = gemini_data.get("vibe", "") or ""
        try:
            vibes = json.loads(vibe_str) if vibe_str.startswith("[") else [v.strip().lower() for v in vibe_str.split(",")]
        except Exception:
            vibes = [v.strip().lower() for v in vibe_str.split(",") if v.strip()]
        time_of_day = (gemini_data.get("time_of_day", "") or "").lower()
        gemini_exposure = (gemini_data.get("exposure", "") or "").lower()

    vibe_set = set(vibes)
    is_warm_vibe = bool(vibe_set & WARM_VIBES)
    is_cool_vibe = bool(vibe_set & COOL_VIBES)
    is_moody = bool(vibe_set & MOODY_VIBES)
    is_vibrant = bool(vibe_set & VIBRANT_VIBES)
    has_faces = face_count > 0

    # --- Depth-aware adjustments ---
    depth_note = ""
    depth_shadow_bonus = 0.0
    depth_highlight_bonus = 0.0
    depth_contrast_bonus = 0.0

    if depth_data:
        if near_pct > 50:
            # Foreground-dominant: boost clarity, slightly more contrast
            depth_contrast_bonus = 0.08
            depth_note = f"foreground-dominant ({near_pct:.0f}%): +contrast"
        elif far_pct > 50:
            # Background-dominant (landscape): protect highlights, gentle lift
            depth_highlight_bonus = 0.03
            depth_shadow_bonus = 0.02
            depth_note = f"landscape depth ({far_pct:.0f}%): +highlights +shadows"
        elif (depth_data.get("depth_complexity", 0) or 0) > 0.7:
            # Complex depth: balanced processing
            depth_contrast_bonus = 0.05
            depth_note = f"complex depth: mild contrast"
    plan.depth_adjustment = depth_note

    # --- Scene-aware adjustments ---
    scene_note = ""
    scene_wb_warm = 0.0
    scene_shadow_bonus = 0.0
    scene_highlight_bonus = 0.0
    scene_sat_bonus = 0.0

    if scene_name:
        if scene_name in WARM_SCENES:
            scene_wb_warm = 0.03  # Slight warming
            scene_note = f"warm scene ({scene_name})"
        elif scene_name in COOL_SCENES:
            scene_wb_warm = -0.02  # Slight cooling
            scene_note = f"cool scene ({scene_name})"
        if scene_name in DARK_SCENES:
            scene_shadow_bonus = 0.05
            scene_note += f"; dark interior"
        if scene_name in BRIGHT_SCENES:
            scene_highlight_bonus = 0.04
            scene_note += f"; bright scene"
        if scene_name in NATURE_SCENES and not is_monochrome:
            scene_sat_bonus = 0.04
            scene_note += f"; nature boost"
        if scene_name in HIGH_CONTRAST_SCENES:
            depth_contrast_bonus += 0.05
            scene_note += f"; high contrast scene"
    plan.scene_adjustment = scene_note

    # --- Vibe-aware adjustments ---
    vibe_note = ""
    vibe_brightness_shift = 0.0
    vibe_sat_mult = 1.0
    vibe_contrast_mult = 1.0

    if is_moody:
        vibe_brightness_shift = -0.02  # Slightly darker target
        vibe_contrast_mult = 1.15
        vibe_note = "moody: darker, more contrast"
    elif is_vibrant:
        vibe_sat_mult = 1.08
        vibe_note = "vibrant: saturation boost"
    elif is_warm_vibe:
        scene_wb_warm += 0.02
        vibe_note = "warm vibe: gentle warming"
    elif is_cool_vibe:
        scene_wb_warm -= 0.02
        vibe_note = "cool vibe: gentle cooling"

    if time_of_day in ("golden_hour", "golden hour", "sunset", "sunrise"):
        scene_wb_warm += 0.03
        vibe_note += "; golden hour warmth"
    elif time_of_day in ("blue_hour", "blue hour", "twilight"):
        scene_wb_warm -= 0.02
        vibe_note += "; blue hour cool"
    plan.vibe_adjustment = vibe_note

    # --- Face-aware adjustments ---
    face_note = ""
    face_exposure_conservative = 1.0
    face_sharpen_mult = 1.0

    if has_faces:
        face_exposure_conservative = 0.7  # Less aggressive exposure changes
        face_sharpen_mult = 0.8  # Gentler sharpening on faces
        face_note = f"{face_count} face(s): conservative exposure, gentle sharpen"
    plan.face_adjustment = face_note

    # --- Style annotation ---
    plan.style_adjustment = f"{style_name}: contrast={style_mults['contrast_mult']:.2f}x sat={style_mults['saturation_mult']:.2f}x sharp={style_mults['sharpen_mult']:.2f}x" if style_name else ""

    # ======================================================================
    # Step 1: White Balance (signal-enhanced)
    # ======================================================================
    wb_r = pixel_data.get("wb_shift_r", 0.0)
    wb_b = pixel_data.get("wb_shift_b", 0.0)

    if is_monochrome:
        plan.skip_wb = True
        plan.wb_reason = "Monochrome sensor"
    elif abs(wb_r) < 0.02 and abs(wb_b) < 0.02 and abs(scene_wb_warm) < 0.01:
        plan.skip_wb = True
        plan.wb_reason = "Negligible WB shift, no scene warmth needed"
    else:
        strength = profile.wb_strength
        # Apply pixel-measured correction
        plan.wb_correction_r = 1.0 - wb_r * strength
        plan.wb_correction_b = 1.0 - wb_b * strength
        # Layer scene/vibe warmth on top
        plan.wb_correction_r += scene_wb_warm
        plan.wb_correction_b -= scene_wb_warm * 0.7  # Blue inverse of warming
        # Clamp
        plan.wb_correction_r = max(0.80, min(1.25, plan.wb_correction_r))
        plan.wb_correction_b = max(0.80, min(1.25, plan.wb_correction_b))
        plan.wb_reason = (f"WB r={wb_r:+.3f} b={wb_b:+.3f} str={strength} "
                          f"scene_warm={scene_wb_warm:+.3f}")

    # ======================================================================
    # Step 2: Exposure (signal-enhanced)
    # ======================================================================
    brightness = pixel_data.get("mean_brightness", 110.0)
    is_low_key = pixel_data.get("is_low_key", 0)
    is_high_key = pixel_data.get("is_high_key", 0)

    # If Gemini says exposure is good, reduce correction strength
    exposure_confidence = 1.0
    if gemini_exposure:
        if "good" in gemini_exposure or "correct" in gemini_exposure or "well" in gemini_exposure:
            exposure_confidence = 0.5  # Gemini says it's fine — be conservative
        elif "over" in gemini_exposure:
            exposure_confidence = 1.2  # Gemini confirms overexposure — be aggressive
        elif "under" in gemini_exposure:
            exposure_confidence = 1.2  # Gemini confirms underexposure

    # Face-aware: reduce strength if faces present
    effective_exposure_strength = profile.exposure_strength * exposure_confidence * face_exposure_conservative

    # Moody shift: lower the target brightness
    target_mid = 110.0 + vibe_brightness_shift * 255.0

    if is_low_key and not (has_faces and brightness < 60):
        plan.skip_exposure = True
        plan.exposure_reason = "Intentional low-key"
    elif is_high_key:
        plan.skip_exposure = True
        plan.exposure_reason = "Intentional high-key"
    elif brightness < 70:
        deficit = (target_mid - brightness) / target_mid
        gamma_correction = 1.0 - deficit * 0.3 * effective_exposure_strength
        plan.gamma = max(0.70, min(0.95, gamma_correction))
        plan.exposure_reason = f"Underexposed ({brightness:.0f}), gamma={plan.gamma:.2f}"
    elif brightness > 150:
        excess = (brightness - 120) / 120
        gamma_correction = 1.0 + excess * 0.3 * effective_exposure_strength
        plan.gamma = max(1.05, min(1.30, gamma_correction))
        plan.exposure_reason = f"Overexposed ({brightness:.0f}), gamma={plan.gamma:.2f}"
    elif brightness < 90:
        deficit = (target_mid - brightness) / target_mid
        gamma_correction = 1.0 - deficit * 0.2 * effective_exposure_strength
        plan.gamma = max(0.85, min(0.98, gamma_correction))
        plan.exposure_reason = f"Slightly dark ({brightness:.0f}), gamma={plan.gamma:.2f}"
    elif brightness > 135:
        excess = (brightness - 120) / 120
        gamma_correction = 1.0 + excess * 0.15 * effective_exposure_strength
        plan.gamma = max(1.02, min(1.15, gamma_correction))
        plan.exposure_reason = f"Slightly bright ({brightness:.0f}), gamma={plan.gamma:.2f}"
    else:
        plan.skip_exposure = True
        plan.exposure_reason = f"Brightness OK ({brightness:.0f})"

    # ======================================================================
    # Step 3: Shadow & Highlight Recovery (depth + scene enhanced)
    # ======================================================================
    clip_low = pixel_data.get("clip_low_pct", 0.0)
    clip_high = pixel_data.get("clip_high_pct", 0.0)

    shadow_thresh = profile.shadow_threshold
    highlight_thresh = profile.highlight_threshold

    if clip_low > shadow_thresh:
        excess = clip_low - shadow_thresh
        plan.shadow_lift = min(0.45, excess * 0.03 + depth_shadow_bonus + scene_shadow_bonus)
        plan.sh_reason = f"Shadow clip {clip_low:.1f}%"
    elif depth_shadow_bonus > 0 or scene_shadow_bonus > 0:
        plan.shadow_lift = min(0.15, depth_shadow_bonus + scene_shadow_bonus)
        plan.sh_reason = f"Scene/depth shadow bonus"

    if clip_high > highlight_thresh:
        excess = clip_high - highlight_thresh
        plan.highlight_pull = min(0.35, excess * 0.02 + depth_highlight_bonus + scene_highlight_bonus)
        reason = f"Highlight clip {clip_high:.1f}%"
        plan.sh_reason = (plan.sh_reason + "; " + reason) if plan.sh_reason else reason
    elif depth_highlight_bonus > 0 or scene_highlight_bonus > 0:
        plan.highlight_pull = min(0.10, depth_highlight_bonus + scene_highlight_bonus)
        reason = "Scene/depth highlight protection"
        plan.sh_reason = (plan.sh_reason + "; " + reason) if plan.sh_reason else reason

    if not plan.sh_reason:
        plan.sh_reason = "No recovery needed"

    # ======================================================================
    # Step 4: Contrast (style + depth + vibe enhanced)
    # ======================================================================
    contrast = pixel_data.get("contrast_ratio", 0.85)
    style_contrast_mult = style_mults.get("contrast_mult", 1.0)

    base_contrast = 0.0
    if contrast < 0.55:
        base_contrast = 0.6
        plan.contrast_reason = f"Very low ({contrast:.2f})"
    elif contrast < 0.75:
        base_contrast = 0.4
        plan.contrast_reason = f"Low ({contrast:.2f})"
    elif contrast < 0.92:
        base_contrast = 0.15
        plan.contrast_reason = f"Adequate ({contrast:.2f})"
    else:
        plan.contrast_reason = f"Good ({contrast:.2f})"

    # Apply multipliers from style, depth, vibe
    total_contrast = base_contrast * style_contrast_mult * vibe_contrast_mult + depth_contrast_bonus
    total_contrast = max(0.0, min(0.8, total_contrast))

    if total_contrast > 0.02:
        plan.contrast_strength = total_contrast
        plan.contrast_reason += f" → {total_contrast:.2f} (style={style_contrast_mult:.2f}x)"
    else:
        plan.skip_contrast = True

    # ======================================================================
    # Step 5: Saturation (style + scene + vibe enhanced)
    # ======================================================================
    mean_sat = pixel_data.get("mean_saturation", 0.3)
    style_sat_mult = style_mults.get("saturation_mult", 1.0)

    if is_monochrome:
        plan.skip_saturation = True
        plan.saturation_reason = "Monochrome"
    else:
        base_sat = 1.0
        if mean_sat < 0.15:
            base_sat = min(profile.saturation_boost_cap, 1.15)
        elif mean_sat > 0.50:
            base_sat = 0.95
        elif mean_sat < 0.25:
            base_sat = min(profile.saturation_boost_cap, 1.08)

        # Layer scene + vibe + style modifiers
        total_sat = base_sat * style_sat_mult * vibe_sat_mult + scene_sat_bonus
        total_sat = max(0.85, min(1.30, total_sat))

        if abs(total_sat - 1.0) > 0.02:
            plan.saturation_scale = total_sat
            plan.saturation_reason = (f"sat={mean_sat:.2f}, base={base_sat:.2f}, "
                                       f"style={style_sat_mult:.2f}x, scene_bonus={scene_sat_bonus:+.2f}")
        else:
            plan.skip_saturation = True
            plan.saturation_reason = f"Saturation OK ({mean_sat:.2f})"

    # ======================================================================
    # Step 6: Sharpening (style + face + noise aware)
    # ======================================================================
    noise = pixel_data.get("noise_estimate", 1.5)
    style_sharpen_mult = style_mults.get("sharpen_mult", 1.0)
    total_sharpen_mult = style_sharpen_mult * face_sharpen_mult

    if profile.preserve_grain:
        plan.sharpen_radius = 0.8
        plan.sharpen_percent = 40.0 * total_sharpen_mult
        plan.sharpen_threshold = 5
        plan.sharpen_reason = f"Film grain (noise={noise:.1f})"
    elif is_monochrome:
        plan.sharpen_radius = 1.3
        plan.sharpen_percent = 70.0 * total_sharpen_mult
        plan.sharpen_threshold = 2
        plan.sharpen_reason = f"Monochrome crisp (noise={noise:.1f})"
    elif noise < 2.0:
        plan.sharpen_radius = 1.5
        plan.sharpen_percent = 80.0 * total_sharpen_mult
        plan.sharpen_threshold = 2
        plan.sharpen_reason = f"Clean digital (noise={noise:.1f})"
    elif noise < 3.0:
        plan.sharpen_radius = 1.2
        plan.sharpen_percent = 60.0 * total_sharpen_mult
        plan.sharpen_threshold = 3
        plan.sharpen_reason = f"Noisy (noise={noise:.1f})"
    else:
        plan.sharpen_radius = 0.8
        plan.sharpen_percent = 40.0 * total_sharpen_mult
        plan.sharpen_threshold = 5
        plan.sharpen_reason = f"High noise ({noise:.1f})"

    # Clamp sharpen_percent
    plan.sharpen_percent = max(20.0, min(150.0, plan.sharpen_percent))

    return plan


# ---------------------------------------------------------------------------
# Enhancement execution (same 6-step pipeline as v1)
# ---------------------------------------------------------------------------

def _correct_white_balance(arr: np.ndarray, plan: EnhancementPlanV2) -> np.ndarray:
    if plan.skip_wb:
        return arr
    result = arr.copy().astype(np.float64)
    result[:, :, 0] *= plan.wb_correction_r
    result[:, :, 2] *= plan.wb_correction_b
    return np.clip(result, 0, 255).astype(np.uint8)


def _correct_exposure(arr: np.ndarray, plan: EnhancementPlanV2) -> np.ndarray:
    if plan.skip_exposure:
        return arr
    result = arr.astype(np.float64) / 255.0
    result = np.power(result, plan.gamma)
    result = result * 255.0
    return np.clip(result, 0, 255).astype(np.uint8)


def _recover_shadows_highlights(arr: np.ndarray, plan: EnhancementPlanV2) -> np.ndarray:
    if plan.shadow_lift == 0 and plan.highlight_pull == 0:
        return arr
    result = arr.astype(np.float64)
    luma = 0.299 * result[:, :, 0] + 0.587 * result[:, :, 1] + 0.114 * result[:, :, 2]

    if plan.shadow_lift > 0:
        shadow_mask = luma < 64
        if np.any(shadow_mask):
            lift_amount = plan.shadow_lift * (64 - luma[shadow_mask]) / 64.0
            for ch in range(3):
                channel = result[:, :, ch]
                channel[shadow_mask] += channel[shadow_mask] * lift_amount
                result[:, :, ch] = channel

    if plan.highlight_pull > 0:
        highlight_mask = luma > 220
        if np.any(highlight_mask):
            pull_amount = plan.highlight_pull * (luma[highlight_mask] - 220) / 35.0
            for ch in range(3):
                channel = result[:, :, ch]
                channel[highlight_mask] -= channel[highlight_mask] * pull_amount
                result[:, :, ch] = channel

    return np.clip(result, 0, 255).astype(np.uint8)


def _enhance_contrast(arr: np.ndarray, plan: EnhancementPlanV2) -> np.ndarray:
    if plan.skip_contrast:
        return arr
    result = arr.astype(np.float64)
    luma = 0.299 * result[:, :, 0] + 0.587 * result[:, :, 1] + 0.114 * result[:, :, 2]

    strength = plan.contrast_strength
    normalized = luma / 255.0
    curved = normalized + strength * 0.15 * np.sin(np.pi * normalized * 2) / (np.pi * 2)
    curved = np.clip(curved, 0, 1) * 255.0

    ratio = np.ones_like(luma)
    safe_mask = luma > 1.0
    ratio[safe_mask] = curved[safe_mask] / luma[safe_mask]
    ratio = np.clip(ratio, 0.5, 2.0)

    for ch in range(3):
        result[:, :, ch] *= ratio

    return np.clip(result, 0, 255).astype(np.uint8)


def _adjust_saturation(arr: np.ndarray, plan: EnhancementPlanV2) -> np.ndarray:
    if plan.skip_saturation:
        return arr
    img = Image.fromarray(arr, "RGB")
    hsv = img.convert("HSV")
    hsv_arr = np.array(hsv, dtype=np.float64)
    hsv_arr[:, :, 1] *= plan.saturation_scale
    hsv_arr[:, :, 1] = np.clip(hsv_arr[:, :, 1], 0, 255)
    hsv_result = Image.fromarray(hsv_arr.astype(np.uint8), "HSV")
    return np.array(hsv_result.convert("RGB"))


def _sharpen(img: Image.Image, plan: EnhancementPlanV2) -> Image.Image:
    return img.filter(ImageFilter.UnsharpMask(
        radius=plan.sharpen_radius,
        percent=int(plan.sharpen_percent),
        threshold=plan.sharpen_threshold,
    ))


def execute_plan(plan: EnhancementPlanV2, source_path: str) -> Optional[Image.Image]:
    try:
        img = Image.open(source_path).convert("RGB")
        arr = np.array(img, dtype=np.uint8)

        arr = _correct_white_balance(arr, plan)
        arr = _correct_exposure(arr, plan)
        arr = _recover_shadows_highlights(arr, plan)
        arr = _enhance_contrast(arr, plan)
        arr = _adjust_saturation(arr, plan)

        img = Image.fromarray(arr, "RGB")
        img = _sharpen(img, plan)
        return img
    except Exception as e:
        print(f"  Error enhancing {plan.image_uuid}: {e}", file=sys.stderr)
        return None


def compute_post_metrics(img: Image.Image) -> Dict[str, float]:
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
# Worker
# ---------------------------------------------------------------------------

def _process_one(args: Tuple[str, str, str]) -> Optional[Dict[str, Any]]:
    plan_json, source_path, output_path = args
    plan_dict = json.loads(plan_json)
    plan = EnhancementPlanV2(**{k: v for k, v in plan_dict.items()
                                 if k in EnhancementPlanV2.__dataclass_fields__})

    enhanced = execute_plan(plan, source_path)
    if enhanced is None:
        return None

    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    enhanced.save(output_path, "JPEG", quality=JPEG_QUALITY, subsampling=0)

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
    parser = argparse.ArgumentParser(description="Signal-aware enhancement engine v2")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--camera", type=str, default=None)
    args = parser.parse_args()

    import sqlite3 as _sqlite3
    conn = db.get_connection()
    conn.execute("PRAGMA busy_timeout=120000")  # Wait up to 120s for locks
    now_str = datetime.now(timezone.utc).isoformat()

    # ---- Gather all signals ----
    camera_filter = ""
    params = [SOURCE_TIER, SOURCE_FORMAT]  # type: List[Any]
    if args.camera:
        camera_filter = "AND i.camera_body = ?"
        params.append(args.camera)

    skip_clause = ""
    if not args.force:
        skip_clause = """AND NOT EXISTS (
            SELECT 1 FROM enhancement_plans_v2 ep2
            WHERE ep2.image_uuid = i.uuid AND ep2.status IN ('enhanced', 'accepted')
        )"""

    rows = conn.execute(f"""
        SELECT
            i.uuid, i.camera_body, i.is_monochrome,
            -- Pixel metrics
            ia.mean_brightness, ia.std_brightness,
            ia.clip_low_pct, ia.clip_high_pct, ia.dynamic_range,
            ia.mean_saturation, ia.mean_r, ia.mean_g, ia.mean_b,
            ia.wb_shift_r, ia.wb_shift_b, ia.color_cast,
            ia.contrast_ratio, ia.noise_estimate,
            ia.is_low_key, ia.is_high_key,
            ia.shadow_pct, ia.midtone_pct, ia.highlight_pct,
            -- Depth
            de.near_pct, de.mid_pct, de.far_pct, de.depth_complexity,
            -- Scene
            sc.scene_1, sc.score_1, sc.scene_2, sc.environment,
            -- Style
            st.style, st.confidence as style_conf,
            -- Gemini
            ga.vibe, ga.time_of_day, ga.exposure, ga.setting,
            ga.lighting_fix, ga.color_fix,
            -- Source path
            t.local_path as source_path
        FROM images i
        JOIN image_analysis ia ON i.uuid = ia.image_uuid
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = ? AND t.format = ? AND t.variant_id IS NULL
        LEFT JOIN depth_estimation de ON i.uuid = de.image_uuid
        LEFT JOIN scene_classification sc ON i.uuid = sc.image_uuid
        LEFT JOIN style_classification st ON i.uuid = st.image_uuid
        LEFT JOIN gemini_analysis ga ON i.uuid = ga.image_uuid
        WHERE ia.mean_brightness IS NOT NULL
            {camera_filter}
            {skip_clause}
        ORDER BY i.uuid
    """, params).fetchall()

    work = [dict(r) for r in rows]
    if args.limit:
        work = work[:args.limit]

    # Pre-fetch face counts
    face_counts = {}
    fc_rows = conn.execute(
        "SELECT image_uuid, COUNT(*) as cnt FROM face_detections GROUP BY image_uuid"
    ).fetchall()
    for r in fc_rows:
        face_counts[r["image_uuid"]] = r["cnt"]

    total_images = conn.execute("SELECT COUNT(*) as c FROM images").fetchone()["c"]
    already_done = conn.execute(
        "SELECT COUNT(*) as c FROM enhancement_plans_v2 WHERE status = 'enhanced'"
    ).fetchone()["c"]

    print(f"Enhancement Engine V2 (Signal-Aware)")
    print(f"{'='*60}")
    print(f"Images: {total_images} total | {already_done} v2-enhanced | {len(work)} to process")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'FULL PROCESSING'}")
    print(f"Workers: {args.workers}")
    print(f"Signals: depth + scene + style + gemini + faces + pixels")
    print(f"{'='*60}")

    if not work:
        print("Nothing to process.")
        conn.close()
        return

    # ---- Phase 1: Compute plans ----
    print(f"\nPhase 1: Computing v2 plans for {len(work)} images...")
    plans_start = time.time()
    plans = []  # type: List[Tuple[EnhancementPlanV2, str]]

    for item in work:
        pixel_data = {k: item[k] for k in item if k not in
                      ("uuid", "camera_body", "is_monochrome", "source_path",
                       "near_pct", "mid_pct", "far_pct", "depth_complexity",
                       "scene_1", "score_1", "scene_2", "environment",
                       "style", "style_conf",
                       "vibe", "time_of_day", "exposure", "setting",
                       "lighting_fix", "color_fix")}

        depth_data = None
        if item.get("near_pct") is not None:
            depth_data = {
                "near_pct": item["near_pct"],
                "mid_pct": item["mid_pct"],
                "far_pct": item["far_pct"],
                "depth_complexity": item.get("depth_complexity"),
            }

        scene_data = None
        if item.get("scene_1"):
            scene_data = {
                "scene_1": item["scene_1"],
                "score_1": item["score_1"],
                "scene_2": item.get("scene_2"),
                "environment": item.get("environment"),
            }

        style_data = None
        if item.get("style"):
            style_data = {"style": item["style"], "confidence": item.get("style_conf")}

        gemini_data = None
        if item.get("vibe") or item.get("time_of_day") or item.get("exposure"):
            gemini_data = {
                "vibe": item.get("vibe"),
                "time_of_day": item.get("time_of_day"),
                "exposure": item.get("exposure"),
                "setting": item.get("setting"),
                "lighting_fix": item.get("lighting_fix"),
                "color_fix": item.get("color_fix"),
            }

        fc = face_counts.get(item["uuid"], 0)

        plan = compute_plan_v2(
            image_uuid=item["uuid"],
            pixel_data=pixel_data,
            camera_body=item["camera_body"],
            is_mono=bool(item["is_monochrome"]),
            depth_data=depth_data,
            scene_data=scene_data,
            style_data=style_data,
            gemini_data=gemini_data,
            face_count=fc,
        )
        plans.append((plan, item["source_path"]))

        # Save plan to DB with retry for locked DB
        output_path = str(ENHANCED_V2_DIR / f"{item['uuid']}.jpg")
        for attempt in range(10):
            try:
                conn.execute("""
                    INSERT INTO enhancement_plans_v2 (
                        image_uuid, camera_body, plan_json,
                        wb_correction_r, wb_correction_b, gamma,
                        shadow_lift, highlight_pull, contrast_strength,
                        saturation_scale, sharpen_radius, sharpen_percent,
                        depth_adjustment, scene_adjustment, style_adjustment,
                        vibe_adjustment, face_adjustment,
                        status, source_tier, output_path,
                        pre_brightness, pre_wb_shift_r, pre_contrast,
                        planned_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'planned',?,?,?,?,?,?)
                    ON CONFLICT(image_uuid) DO UPDATE SET
                        camera_body=excluded.camera_body, plan_json=excluded.plan_json,
                        wb_correction_r=excluded.wb_correction_r,
                        wb_correction_b=excluded.wb_correction_b,
                        gamma=excluded.gamma, shadow_lift=excluded.shadow_lift,
                        highlight_pull=excluded.highlight_pull,
                        contrast_strength=excluded.contrast_strength,
                        saturation_scale=excluded.saturation_scale,
                        sharpen_radius=excluded.sharpen_radius,
                        sharpen_percent=excluded.sharpen_percent,
                        depth_adjustment=excluded.depth_adjustment,
                        scene_adjustment=excluded.scene_adjustment,
                        style_adjustment=excluded.style_adjustment,
                        vibe_adjustment=excluded.vibe_adjustment,
                        face_adjustment=excluded.face_adjustment,
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
                    plan.depth_adjustment, plan.scene_adjustment, plan.style_adjustment,
                    plan.vibe_adjustment, plan.face_adjustment,
                    SOURCE_TIER, output_path,
                    plan.pre_brightness, plan.pre_wb_shift_r, plan.pre_contrast,
                    now_str,
                ))
                break
            except Exception as e:
                if "locked" in str(e) and attempt < 9:
                    time.sleep(2 * (attempt + 1))
                else:
                    raise

        # Batch commit every 200 plans
        if len(plans) % 200 == 0:
            for ca in range(10):
                try:
                    conn.commit()
                    break
                except Exception as e:
                    if "locked" in str(e) and ca < 9:
                        time.sleep(2 * (ca + 1))
                    else:
                        raise
            print(f"  {len(plans)} plans computed...")

    for attempt in range(10):
        try:
            conn.commit()
            break
        except Exception as e:
            if "locked" in str(e) and attempt < 9:
                time.sleep(3 * (attempt + 1))
            else:
                raise

    plans_elapsed = time.time() - plans_start
    print(f"  {len(plans)} v2 plans computed in {plans_elapsed:.1f}s")

    _print_plan_summary(plans)

    if args.dry_run:
        print("\n[DRY RUN] Plans saved. No images processed.")
        conn.close()
        return

    # ---- Phase 2: Execute ----
    print(f"\nPhase 2: Enhancing {len(plans)} images with {args.workers} workers...")
    ENHANCED_V2_DIR.mkdir(parents=True, exist_ok=True)
    enhance_start = time.time()
    completed = 0
    errors = 0

    pool_work = []
    for plan, source_path in plans:
        output_path = str(ENHANCED_V2_DIR / f"{plan.image_uuid}.jpg")
        pool_work.append((plan.to_json(), source_path, output_path))

    with Pool(processes=args.workers) as pool:
        for result in pool.imap_unordered(_process_one, pool_work):
            if result is None:
                errors += 1
                continue

            for attempt in range(10):
                try:
                    conn.execute("""
                        UPDATE enhancement_plans_v2 SET
                            status = 'enhanced', output_path = ?,
                            post_brightness = ?, post_wb_shift_r = ?,
                            post_contrast = ?, enhanced_at = ?
                        WHERE image_uuid = ?
                    """, (
                        result["output_path"],
                        result["post_brightness"],
                        result["post_wb_shift_r"],
                        result["post_contrast"],
                        now_str,
                        result["image_uuid"],
                    ))
                    break
                except Exception as e:
                    if "locked" in str(e) and attempt < 9:
                        time.sleep(2 * (attempt + 1))
                    else:
                        raise

            completed += 1
            if completed % 100 == 0:
                for attempt in range(10):
                    try:
                        conn.commit()
                        break
                    except Exception:
                        time.sleep(2 * (attempt + 1))
                elapsed = time.time() - enhance_start
                rate = completed / elapsed
                remaining = (len(plans) - completed - errors) / rate if rate > 0 else 0
                print(f"  {completed}/{len(plans)} enhanced "
                      f"({rate:.1f}/s, ~{remaining:.0f}s remaining)")

    for attempt in range(5):
        try:
            conn.commit()
            break
        except Exception:
            time.sleep(2 * (attempt + 1))

    elapsed = time.time() - enhance_start
    print(f"\n{'='*60}")
    print(f"V2 Enhancement Done in {elapsed:.1f}s")
    print(f"Enhanced: {completed} | Errors: {errors}")
    if completed > 0:
        print(f"Rate: {completed/elapsed:.1f} images/s")

    conn.close()


def _print_plan_summary(plans: List[Tuple[EnhancementPlanV2, str]]) -> None:
    camera_counts = {}  # type: Dict[str, int]
    step_counts = {"wb": 0, "exposure": 0, "shadows_highlights": 0,
                   "contrast": 0, "saturation": 0, "sharpen": 0}
    signal_usage = {"depth": 0, "scene": 0, "style": 0, "vibe": 0, "face": 0}

    for plan, _ in plans:
        cam = plan.camera_body
        camera_counts[cam] = camera_counts.get(cam, 0) + 1
        for step in plan.steps_applied:
            step_counts[step] += 1
        if plan.depth_adjustment:
            signal_usage["depth"] += 1
        if plan.scene_adjustment:
            signal_usage["scene"] += 1
        if plan.style_adjustment:
            signal_usage["style"] += 1
        if plan.vibe_adjustment:
            signal_usage["vibe"] += 1
        if plan.face_adjustment:
            signal_usage["face"] += 1

    total = len(plans)
    print(f"\n--- V2 Plan Summary ({total} images) ---")
    print(f"  By camera:")
    for cam, cnt in sorted(camera_counts.items(), key=lambda x: -x[1]):
        print(f"    {cam:20} {cnt:5} ({cnt/total*100:.0f}%)")
    print(f"  Steps applied:")
    for step, cnt in step_counts.items():
        print(f"    {step:25} {cnt:5} ({cnt/total*100:.0f}%)")
    print(f"  Signal influence:")
    for sig, cnt in signal_usage.items():
        print(f"    {sig:25} {cnt:5} ({cnt/total*100:.0f}%)")


if __name__ == "__main__":
    main()
