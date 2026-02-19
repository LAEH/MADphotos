"""Candidate selection and signal-based style matching."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    CARTOON_STYLE_MAP,
    FAMILIES,
    MOOD_STYLE_MAP,
    REJECTED_HUE_RANGES,
    STYLES,
)


def parse_vibes(vibe_json: Optional[str]) -> List[str]:
    if not vibe_json:
        return []
    try:
        v = json.loads(vibe_json)
        return [x.lower() for x in v] if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _hue_in_rejected_range(hue: Optional[int]) -> bool:
    """Check if a dominant hue falls in learned-rejection color ranges."""
    if hue is None:
        return False
    for lo, hi in REJECTED_HUE_RANGES:
        if lo <= hue <= hi:
            return True
    return False


def get_candidates(conn: sqlite3.Connection, count: int) -> List[Dict]:
    """Select candidate picks with all signals, scored by composite quality.

    Skips photos that already have accepted or pending smart_style variants,
    and photos with dominant salmon/coral/khaki palettes.
    """
    rows = conn.execute("""
        SELECT i.uuid, i.category, i.subcategory, i.orientation, i.is_monochrome,
               ga.setting, ga.time_of_day, ga.grading_style, ga.vibe, ga.faces_count,
               a.score as aesthetic,
               gp.gemma_description, gp.gemma_mood, gp.gemma_tags,
               gp.gemma_json, gp.print_worthy, gp.cartoon_style,
               ia.dominant_hue, ia.mean_saturation,
               MIN(t.local_path) as source_path
        FROM images i
        JOIN gemini_analysis ga ON i.uuid = ga.image_uuid
        LEFT JOIN aesthetic_scores a ON i.uuid = a.image_uuid
        LEFT JOIN gemma_picks gp ON i.uuid = gp.uuid
        LEFT JOIN image_analysis ia ON i.uuid = ia.image_uuid
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = 'mobile' AND t.format = 'jpeg' AND t.variant_id IS NULL
        WHERE i.uuid NOT IN (
            SELECT image_uuid FROM ai_variants
            WHERE review_status = 'accepted'
              AND variant_type = 'smart_style'
        )
        AND i.uuid NOT IN (
            SELECT image_uuid FROM ai_variants
            WHERE variant_type = 'smart_style'
              AND generation_status IN ('success', 'filtered')
        )
        GROUP BY i.uuid
        ORDER BY i.uuid
    """).fetchall()

    candidates = []
    for r in rows:
        photo = dict(r)

        # Skip photos with rejected dominant hues
        if _hue_in_rejected_range(photo.get("dominant_hue")):
            continue

        # Composite quality score for ranking
        score = 0.0
        if photo.get("print_worthy"):
            score += 3.0
        if (photo.get("faces_count") or 0) == 0:
            score += 2.0
        if photo.get("is_monochrome"):
            score += 2.0
        if (photo.get("aesthetic") or 0) > 7.0:
            score += 1.0
        if photo.get("gemma_description"):
            score += 1.0  # has complete Gemma data
        setting = (photo.get("setting") or "").lower()
        if "exterior" in setting:
            score += 1.0

        photo["_quality_score"] = score
        candidates.append(photo)

    # Sort by quality score descending, then uuid for stability
    candidates.sort(key=lambda p: (-p["_quality_score"], p["uuid"]))
    return candidates[:count]


def _parse_gemma_json(raw: Optional[str]) -> Dict[str, Any]:
    """Extract lighting and colors from the full Gemma JSON."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def score_style(style_key: str, photo: Dict) -> float:
    """Score how well a style matches a photo's characteristics.

    Uses all available signals: Gemini analysis, Gemma mood/tags/cartoon_style,
    dominant_hue, and image_analysis.
    """
    style = STYLES[style_key]
    affinities = style["affinities"]
    penalties = style.get("penalties", {})
    score = 0.0

    setting = (photo.get("setting") or "").lower()
    grading = (photo.get("grading_style") or "").lower()
    time_of_day = (photo.get("time_of_day") or "").lower()
    vibes = parse_vibes(photo.get("vibe"))
    faces = photo.get("faces_count") or 0
    is_mono = bool(photo.get("is_monochrome"))
    orientation = photo.get("orientation", "landscape")

    # ── Gemini signals (same as generate_smart_variants.py) ──

    if "exterior" in setting:
        score += affinities.get("exterior", 0) + penalties.get("exterior", 0)
    if "interior" in setting:
        score += affinities.get("interior", 0) + penalties.get("interior", 0)

    if "night" in time_of_day:
        score += affinities.get("night", 0)
    if "golden" in time_of_day:
        score += affinities.get("golden", 0)

    if "cinematic" in grading:
        score += affinities.get("cinematic", 0)
    if "monochrome" in grading or is_mono:
        score += affinities.get("monochrome", 0) + penalties.get("colorful", 0)

    for vibe in vibes:
        for keyword in ["moody", "gritty", "urban", "serene", "ethereal",
                         "nostalgic", "peaceful", "vast", "airy", "chaotic",
                         "dreamy", "dark", "bright", "cinematic"]:
            if keyword in vibe:
                score += affinities.get(keyword, 0) + penalties.get(keyword, 0)

    if faces == 0:
        score += affinities.get("no_faces", 0)
    elif faces >= 3:
        score += penalties.get("faces_many", 0)
    else:
        score += affinities.get("faces", 0)

    if orientation == "landscape":
        score += affinities.get("landscape_orient", 0)

    # Pixar baseline boost (proven 86% acceptance)
    if style_key == "pixar":
        score += 1.0

    # ── NEW: Gemma cartoon_style ──

    cartoon_style = (photo.get("cartoon_style") or "").lower()
    if cartoon_style:
        # Check if Gemma's recommendation maps to this style
        for keyword, mapped_style in CARTOON_STYLE_MAP.items():
            if keyword in cartoon_style and mapped_style == style_key:
                score += 5.0
                break

    # ── NEW: Gemma mood → style affinity ──

    mood = (photo.get("gemma_mood") or "").lower()
    if mood:
        for mood_word, style_boosts in MOOD_STYLE_MAP.items():
            if mood_word in mood:
                score += style_boosts.get(style_key, 0)

    # ── NEW: Gemma tags → style affinity ──

    tags_str = (photo.get("gemma_tags") or "").lower()
    if tags_str:
        for keyword in affinities:
            if keyword in tags_str:
                score += min(affinities[keyword], 2)  # cap tag boost at 2

    return score


def pick_styles(photo: Dict) -> List[str]:
    """Pick the 2 best-suited styles for a photo, ensuring family diversity."""
    scores = [(key, score_style(key, photo)) for key in STYLES]
    scores.sort(key=lambda x: -x[1])

    picked = [scores[0][0]]
    first_family = FAMILIES[picked[0]]

    for key, sc in scores[1:]:
        if FAMILIES[key] != first_family:
            picked.append(key)
            break

    if len(picked) < 2:
        picked.append(scores[1][0])

    return picked[:2]
