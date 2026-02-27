"""Candidate selection and signal-based style matching."""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    CARTOON_STYLE_MAP,
    DEAD_MIN_REVIEWS,
    DEAD_THRESHOLD,
    EXPLORATION_BONUS,
    EXPLORE_MAX_REVIEWS,
    EXPLORE_RATE,
    FAMILIES,
    MOOD_STYLE_MAP,
    PERFORMANCE_CENTER,
    PERFORMANCE_MIN_TRUST,
    PERFORMANCE_SCALE,
    REJECTED_HUE_RANGES,
    STYLES,
)

# Module-level cache for style rates (loaded once per run)
_cached_style_rates: Optional[Dict[str, Dict]] = None


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


def get_style_rates(conn: sqlite3.Connection) -> Dict[str, Dict]:
    """Query historical acceptance rates per style from ai_variants.

    Returns {style_key: {accepted: N, rejected: N, total: N, rate: 0.0-1.0}}
    Only counts rows with a review_status (accepted or rejected).
    """
    rows = conn.execute("""
        SELECT style_key, review_status, COUNT(*) as cnt
        FROM ai_variants
        WHERE variant_type = 'smart_style'
          AND style_key IS NOT NULL
          AND review_status IN ('accepted', 'rejected')
        GROUP BY style_key, review_status
    """).fetchall()

    rates: Dict[str, Dict] = {}
    for r in rows:
        key = r["style_key"]
        if key not in rates:
            rates[key] = {"accepted": 0, "rejected": 0, "total": 0, "rate": 0.0}
        if r["review_status"] == "accepted":
            rates[key]["accepted"] = r["cnt"]
        else:
            rates[key]["rejected"] = r["cnt"]

    for data in rates.values():
        data["total"] = data["accepted"] + data["rejected"]
        data["rate"] = data["accepted"] / data["total"] if data["total"] > 0 else 0.0

    return rates


def _load_style_rates(conn: sqlite3.Connection) -> Dict[str, Dict]:
    """Load style rates, caching for the duration of the process."""
    global _cached_style_rates
    if _cached_style_rates is None:
        _cached_style_rates = get_style_rates(conn)
    return _cached_style_rates


def get_candidates(conn: sqlite3.Connection, count: int) -> List[Dict]:
    """Select candidate picks with all signals, scored by composite quality.

    Skips photos that already have accepted or pending smart_style variants,
    and photos with dominant salmon/coral/khaki palettes.
    """
    rows = conn.execute("""
        SELECT i.uuid, i.category, i.subcategory, i.orientation, i.is_monochrome,
               gem.setting, gem.time_of_day, gem.grading_style, gem.vibe, gem.faces_count,
               a.score as aesthetic,
               ga.description as gemma_description, ga.mood as gemma_mood, ga.tags as gemma_tags,
               ga.raw_json as gemma_json, ga.print_worthy, ga.cartoon_style,
               ia.dominant_hue, ia.mean_saturation,
               MIN(t.local_path) as source_path
        FROM images i
        JOIN gemini_analysis gem ON i.uuid = gem.image_uuid
        LEFT JOIN aesthetic_scores a ON i.uuid = a.image_uuid
        LEFT JOIN gemma_analysis ga ON i.uuid = ga.uuid
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
        AND i.uuid NOT IN (
            SELECT image_uuid FROM ai_variants
            WHERE variant_type = 'smart_style' AND generation_status = 'failed'
            GROUP BY image_uuid
            HAVING COUNT(*) >= 3 AND SUM(CASE WHEN generation_status = 'success' THEN 1 ELSE 0 END) = 0
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


def score_style(style_key: str, photo: Dict,
                rates: Optional[Dict[str, Dict]] = None) -> float:
    """Score how well a style matches a photo's characteristics.

    Uses all available signals: Gemini analysis, Gemma mood/tags/cartoon_style,
    dominant_hue, image_analysis, plus historical acceptance rates.
    """
    style = STYLES[style_key]
    affinities = style["affinities"]
    penalties = style.get("penalties", {})
    score = 0.0

    # ── Dead style check ──
    if rates:
        style_data = rates.get(style_key)
        if (style_data
                and style_data["total"] >= DEAD_MIN_REVIEWS
                and style_data["rate"] < DEAD_THRESHOLD):
            return -999.0

    setting = (photo.get("setting") or "").lower()
    grading = (photo.get("grading_style") or "").lower()
    time_of_day = (photo.get("time_of_day") or "").lower()
    vibes = parse_vibes(photo.get("vibe"))
    faces = photo.get("faces_count") or 0
    is_mono = bool(photo.get("is_monochrome"))
    orientation = photo.get("orientation", "landscape")

    # ── Gemini signals ──

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

    # ── Gemma cartoon_style ──

    cartoon_style = (photo.get("cartoon_style") or "").lower()
    if cartoon_style:
        for keyword, mapped_style in CARTOON_STYLE_MAP.items():
            if keyword in cartoon_style and mapped_style == style_key:
                score += 5.0
                break

    # ── Gemma mood → style affinity ──

    mood = (photo.get("gemma_mood") or "").lower()
    if mood:
        for mood_word, style_boosts in MOOD_STYLE_MAP.items():
            if mood_word in mood:
                score += style_boosts.get(style_key, 0)

    # ── Gemma tags → style affinity ──

    tags_str = (photo.get("gemma_tags") or "").lower()
    if tags_str:
        for keyword in affinities:
            if keyword in tags_str:
                score += min(affinities[keyword], 2)  # cap tag boost at 2

    # ── Performance memory (from DB review history) ──

    if rates:
        style_data = rates.get(style_key)
        if style_data and style_data["total"] >= PERFORMANCE_MIN_TRUST:
            # Enough data — boost/penalize based on acceptance rate
            # rate 0.70 → +2.5, rate 0.45 → 0.0, rate 0.15 → -3.0
            score += (style_data["rate"] - PERFORMANCE_CENTER) * PERFORMANCE_SCALE
        elif style_data is None or style_data["total"] < 3:
            # New/undertested — exploration bonus
            score += EXPLORATION_BONUS

    return score


def pick_styles(photo: Dict,
                rates: Optional[Dict[str, Dict]] = None) -> List[str]:
    """Pick the 2 best-suited styles for a photo.

    Slot 1: always the best-scoring style.
    Slot 2: 80% exploit (next-best from different family),
            20% explore (random undertested style from different family).

    Dead styles (rate < DEAD_THRESHOLD with enough reviews) are auto-excluded
    via score_style returning -999.
    """
    scores = [(key, score_style(key, photo, rates)) for key in STYLES]
    scores.sort(key=lambda x: -x[1])

    # Filter out dead styles
    scores = [(k, s) for k, s in scores if s > -900]
    if not scores:
        # Fallback: all styles dead — just use top 2 by affinity alone
        scores = [(key, score_style(key, photo)) for key in STYLES]
        scores.sort(key=lambda x: -x[1])

    picked = [scores[0][0]]
    first_family = FAMILIES.get(picked[0])

    # Slot 2: explore/exploit
    if rates and random.random() < EXPLORE_RATE:
        # Explore: pick an undertested style from a different family
        undertested = [
            k for k, _ in scores[1:]
            if FAMILIES.get(k) != first_family
            and rates.get(k, {}).get("total", 0) < EXPLORE_MAX_REVIEWS
        ]
        if undertested:
            picked.append(random.choice(undertested))

    if len(picked) < 2:
        # Exploit: next-best from different family
        for key, sc in scores[1:]:
            if FAMILIES.get(key) != first_family:
                picked.append(key)
                break

    if len(picked) < 2 and len(scores) > 1:
        picked.append(scores[1][0])

    return picked[:2]
