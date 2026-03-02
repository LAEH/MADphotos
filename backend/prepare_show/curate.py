"""Phase 4 — Pre-build experiences: bentos, boom sets, game pairs.

Direct translation of BentoView.tsx curators, BoomView.tsx BOOM_DEFS,
GameView.tsx strategies, and layoutRegistry.ts layouts.
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from typing import Any

from . import (
    BENTO_UNIT_RATIO, BENTOS_JSON, BOOM_JSON, PAIRS_JSON, DRIFT_JSON,
)
from .score import visual_impact, ratio_to_key
from backend.bento.assign import crop_fitness, fill_cells as _bento_fill_cells, orient_pools as _bento_orient_pools
from backend.bento.layouts import (
    DESKTOP_LAYOUTS as _BENTO_DESKTOP,
    DESKTOP_SMALL_LAYOUTS as _BENTO_DESKTOP_SMALL,
    MOBILE_LAYOUTS as _BENTO_MOBILE,
    MOBILE_SMALL_LAYOUTS as _BENTO_MOBILE_SMALL,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _pid(p: dict) -> str:
    return p.get("id") or p.get("uuid") or ""


def _hue_dist(a: float, b: float) -> float:
    d = abs(a - b)
    return d if d <= 180 else 360 - d


def _random_from(lst: list) -> Any:
    return lst[random.randint(0, len(lst) - 1)] if lst else None


def _shuffle(lst: list) -> list:
    out = lst[:]
    random.shuffle(out)
    return out


def _canon_key(a: str, b: str) -> str:
    return f"{a}|{b}" if a < b else f"{b}|{a}"


def _hex_to_hue(hex_str: str) -> float:
    if not hex_str or len(hex_str) < 7:
        return -1
    try:
        r = int(hex_str[1:3], 16) / 255
        g = int(hex_str[3:5], 16) / 255
        b = int(hex_str[5:7], 16) / 255
    except (ValueError, IndexError):
        return -1
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0
    d = mx - mn
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


# ═══════════════════════════════════════════════════════════════════════════════
# Layout definitions — imported from backend.bento.layouts (single source of truth)
# ═══════════════════════════════════════════════════════════════════════════════

DESKTOP_LAYOUTS = _BENTO_DESKTOP + _BENTO_DESKTOP_SMALL
MOBILE_LAYOUTS = _BENTO_MOBILE + _BENTO_MOBILE_SMALL


def P(r, c, rs, cs):
    """Portrait cell helper (for any remaining inline usage)."""
    return {"r": r, "c": c, "rs": rs, "cs": cs, "orient": "P"}


def L(r, c, rs, cs):
    """Landscape cell helper (for any remaining inline usage)."""
    return {"r": r, "c": c, "rs": rs, "cs": cs, "orient": "L"}


def _has_mixed_sizes(layout: dict) -> bool:
    """Returns true if layout has >= 2 different cell size classes."""
    sizes = set()
    for cell in layout["cells"]:
        sizes.add(f"{cell['rs']}x{cell['cs']}")
    return len(sizes) >= 2


def _pick_layout_for_count(target: int, device: str) -> dict:
    """Pick a layout for the target count, requiring mixed sizes."""
    layouts = DESKTOP_LAYOUTS if device == "desktop" else MOBILE_LAYOUTS
    need_mixed = target > 4

    # Exact match
    exact = [l for l in layouts if l["count"] == target]
    if need_mixed:
        exact = [l for l in exact if _has_mixed_sizes(l)]
    if exact:
        return _random_from(exact)

    # Close match
    tolerance = max(2, math.ceil(target * 0.3))
    close = [l for l in layouts if abs(l["count"] - target) <= tolerance and l["count"] != target]
    if need_mixed:
        close = [l for l in close if _has_mixed_sizes(l)]
    if close:
        close.sort(key=lambda l: abs(l["count"] - target))
        best_dist = abs(close[0]["count"] - target)
        best = [l for l in close if abs(l["count"] - target) == best_dist]
        return _random_from(best)

    # Fallback: just use D1
    return DESKTOP_LAYOUTS[0] if device == "desktop" else MOBILE_LAYOUTS[0]


# ═══════════════════════════════════════════════════════════════════════════════
# Bento helpers — from BentoView.tsx
# ═══════════════════════════════════════════════════════════════════════════════

def _orient_pools(photos: list[dict]) -> dict[str, list[dict]]:
    return _bento_orient_pools(photos)


def _color_warmth(p: dict) -> str:
    if p.get("mono"):
        return "mono"
    gc_temp = p.get("gc_temp")
    if gc_temp:
        if gc_temp in ("warm", "molten"):
            return "warm"
        if gc_temp in ("cool", "glacial"):
            return "cool"
        if gc_temp == "monochrome":
            return "mono"
        return "neutral"
    h = p.get("hue") or 0
    if h < 50 or h > 310:
        return "warm"
    if 160 < h < 260:
        return "cool"
    return "neutral"


def _fill_cells(
    cells: list[dict],
    pools: dict[str, list[dict]],
    used_ids: set[str],
    score_fn,
) -> list[dict]:
    """Smart cell assignment — delegates to backend.bento.assign.fill_cells()."""
    return _bento_fill_cells(cells, pools, used_ids, score_fn)


# ═══════════════════════════════════════════════════════════════════════════════
# 25 Curators — from BentoView.tsx
# ═══════════════════════════════════════════════════════════════════════════════

def _base_filter(photos: list[dict], extra=None) -> list[dict]:
    """Common pick filter: has thumb + display, not variant, aesthetic > 4."""
    result = [p for p in photos
              if p.get("thumb") and p.get("display") and not p.get("parent")
              and (p.get("aesthetic") or 0) > 4]
    if extra:
        result = [p for p in result if extra(p)]
    return result


def curate_hero_story(all_photos, cells):
    photos = _base_filter(all_photos)
    if len(photos) < len(cells):
        return []
    scored = sorted(photos, key=lambda p: -visual_impact(p))
    top_n = max(5, len(scored) // 5)
    hero = scored[random.randint(0, top_n - 1)]
    hero_vibes = set(hero.get("vibes") or [])
    hero_hue = hero.get("hue") or 0
    pools = _orient_pools(photos)
    used = set()
    hero_id = _pid(hero)
    def score(p):
        if _pid(p) == hero_id:
            return 999
        s = p.get("aesthetic") or 5
        shared = len([v for v in (p.get("vibes") or []) if v in hero_vibes])
        s += shared * 4
        hd = _hue_dist(p.get("hue") or 0, hero_hue)
        if hd < 40: s += 5
        elif hd > 140: s += 3
        if p.get("scene") == hero.get("scene") and hero.get("scene"): s += 3
        if p.get("time") == hero.get("time") and hero.get("time"): s += 2
        if p.get("grading") == hero.get("grading") and hero.get("grading"): s += 2
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_temperature_harmony(all_photos, cells):
    photos = _base_filter(all_photos)
    warm = [p for p in photos if _color_warmth(p) == "warm"]
    cool = [p for p in photos if _color_warmth(p) == "cool"]
    if len(warm) > len(cool) * 1.5:
        pool, temp = warm, "warm"
    elif len(cool) > len(warm) * 1.5:
        pool, temp = cool, "cool"
    else:
        temp = random.choice(["warm", "cool"])
        pool = warm if temp == "warm" else cool
    if len(pool) < len(cells):
        return []
    pools = _orient_pools(pool)
    used = set()
    target_hue = 30 if temp == "warm" else 210
    def score(p):
        s = visual_impact(p)
        gc = p.get("gc_temp")
        if gc:
            if temp == "warm" and gc in ("warm", "molten"): s += 3
            if temp == "cool" and gc in ("cool", "glacial"): s += 3
        s += (60 - _hue_dist(p.get("hue") or 0, target_hue)) / 6
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_depth_journey(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: p.get("depth_complexity") is not None)
    if len(photos) < len(cells):
        return []
    shallow = [p for p in photos if (p.get("depth_complexity") or 0) < 3]
    deep = [p for p in photos if (p.get("depth_complexity") or 0) >= 3]
    if len(shallow) < 2 or len(deep) < 2:
        return []
    pools = _orient_pools(photos)
    used = set()
    def score(p):
        s = visual_impact(p)
        s += (p.get("depth_complexity") or 2) * 0.5
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_mono_accent(all_photos, cells):
    mono = [p for p in all_photos if p.get("thumb") and p.get("display") and not p.get("parent")
            and p.get("mono") and (p.get("aesthetic") or 0) > 4]
    color = [p for p in all_photos if p.get("thumb") and p.get("display") and not p.get("parent")
             and not p.get("mono") and (p.get("aesthetic") or 0) > 5 and (p.get("contrast") or 50) > 60]
    if len(mono) < len(cells) - 2 or len(color) < 1:
        return []
    accent_count = 1 if len(cells) <= 6 else 2
    sorted_color = sorted(color, key=lambda p: -visual_impact(p))
    accents = sorted_color[:accent_count]
    mixed = accents + mono
    pools = _orient_pools(mixed)
    used = set()
    def score(p):
        s = visual_impact(p)
        if not p.get("mono"): s += 10
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_color_story(all_photos, cells):
    photos = [p for p in all_photos if p.get("thumb") and p.get("display") and not p.get("mono")
              and (p.get("aesthetic") or 0) > 4]
    hue_buckets = [[] for _ in range(12)]
    for p in photos:
        idx = min(int((p.get("hue") or 0) / 30), 11)
        hue_buckets[idx].append(p)
    best_start, best_count = 0, 0
    for i in range(12):
        count = len(hue_buckets[i]) + len(hue_buckets[(i+1)%12]) + len(hue_buckets[(i+2)%12])
        if count > best_count:
            best_count = count
            best_start = i
    target_hue = (best_start * 30 + 45) % 360
    in_range = [p for p in photos if _hue_dist(p.get("hue") or 0, target_hue) < 45]
    if len(in_range) < len(cells):
        return []
    pools = _orient_pools(in_range)
    used = set()
    def score(p):
        s = visual_impact(p)
        s += (45 - _hue_dist(p.get("hue") or 0, target_hue)) / 4
        if p.get("parent"): s -= 3
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_mood_board(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: p.get("vibes") and len(p["vibes"]) > 0)
    if not photos:
        return []
    vibe_counts: dict[str, int] = defaultdict(int)
    for p in photos:
        for v in p["vibes"]:
            vibe_counts[v] += 1
    good = [v for v, c in vibe_counts.items() if c >= len(cells) * 1.5]
    if not good:
        return []
    target = _random_from(good)
    matching = [p for p in photos if target in p["vibes"]]
    pools = _orient_pools(matching)
    used = set()
    def score(p):
        s = visual_impact(p)
        shared = sum(1 for v in p["vibes"] if vibe_counts.get(v, 0) >= 5)
        s += shared * 3
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_scene_story(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: bool(p.get("scene")))
    if not photos:
        return []
    scene_counts: dict[str, int] = defaultdict(int)
    for p in photos:
        scene_counts[p["scene"]] += 1
    good = [s for s, c in scene_counts.items() if c >= len(cells) * 1.5]
    if not good:
        return []
    target = _random_from(good)
    matching = [p for p in photos if p["scene"] == target]
    hues = [p.get("hue") or 0 for p in matching]
    avg_hue = sum(hues) / len(hues) if hues else 180
    pools = _orient_pools(matching)
    used = set()
    def score(p):
        s = visual_impact(p)
        s += (60 - _hue_dist(p.get("hue") or 0, avg_hue)) / 6
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_archetype_exhibition(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: bool(p.get("gc_archetype")))
    if len(photos) < len(cells):
        return []
    arch_counts: dict[str, int] = defaultdict(int)
    for p in photos:
        arch_counts[p["gc_archetype"]] += 1
    good = [a for a, c in arch_counts.items() if c >= len(cells)]
    if not good:
        return []
    target = _random_from(good)
    matching = [p for p in photos if p["gc_archetype"] == target]
    pools = _orient_pools(matching)
    used = set()
    def score(p):
        return visual_impact(p) + random.random() * 3
    return _fill_cells(cells, pools, used, score)


def curate_camera_story(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: bool(p.get("camera")))
    if not photos:
        return []
    cam_counts: dict[str, int] = defaultdict(int)
    for p in photos:
        cam_counts[p["camera"]] += 1
    min_count = math.ceil(len(cells) * 1.5)
    good = [c for c, n in cam_counts.items() if n >= min_count]
    if not good:
        return []
    target = _random_from(good)
    matching = [p for p in photos if p["camera"] == target]
    hues = [p.get("hue") or 0 for p in matching if p.get("hue") is not None]
    avg_hue = sum(hues) / len(hues) if hues else 180
    pools = _orient_pools(matching)
    used = set()
    def score(p):
        s = visual_impact(p)
        s += _hue_dist(p.get("hue") or 0, avg_hue) / 20
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_night_vision(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: p.get("time") == "night" or (p.get("brightness") is not None and p["brightness"] < 50))
    if len(photos) < len(cells):
        return []
    pools = _orient_pools(photos)
    used = set()
    def score(p):
        s = visual_impact(p)
        if (p.get("contrast") or 50) > 60: s += 3
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_golden_hour(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: p.get("time") == "golden hour")
    if len(photos) < len(cells):
        return []
    pools = _orient_pools(photos)
    used = set()
    def score(p):
        s = visual_impact(p)
        h = p.get("hue") or 0
        if 15 < h < 60: s += 4
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_face_gallery(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: (p.get("face_count") or 0) > 0)
    if len(photos) < len(cells):
        return []
    pools = _orient_pools(photos)
    used = set()
    def score(p):
        s = visual_impact(p)
        s += (p.get("face_count") or 0) * 2
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_style_contrast(all_photos, cells):
    analog = _base_filter(all_photos, lambda p: p.get("style") == "analog")
    digital = _base_filter(all_photos, lambda p: p.get("style") in ("street", "documentary"))
    if len(analog) < 2 or len(digital) < 2 or len(analog) + len(digital) < len(cells):
        return []
    mixed = analog + digital
    pools = _orient_pools(mixed)
    used = set()
    def score(p):
        s = visual_impact(p)
        if p.get("style") == "analog": s += 5
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_brightness_gradient(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: p.get("brightness") is not None)
    if len(photos) < len(cells):
        return []
    sorted_p = sorted(photos, key=lambda p: p.get("brightness") or 0)
    step = max(1, len(sorted_p) // (len(cells) * 2))
    sampled = [sorted_p[i] for i in range(0, len(sorted_p), step)][:len(cells) * 3]
    if len(sampled) < len(cells):
        return []
    brights = [p.get("brightness") or 0 for p in sampled]
    max_b, min_b = max(brights), min(brights)
    rng = max_b - min_b or 1
    pools = _orient_pools(sampled)
    used = set()
    def score(p):
        s = visual_impact(p)
        s += ((max_b - (p.get("brightness") or 0)) / rng) * 6
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_energy_flow(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: bool(p.get("gc_energy")))
    if len(photos) < len(cells):
        return []
    energy_counts: dict[str, int] = defaultdict(int)
    for p in photos:
        energy_counts[p["gc_energy"]] += 1
    dynamic = ["diagonal_down", "diagonal_up", "left_to_right", "right_to_left", "center_out"]
    good = [e for e in dynamic if energy_counts.get(e, 0) >= len(cells)]
    if not good:
        return []
    target = _random_from(good)
    matching = [p for p in photos if p["gc_energy"] == target]
    pools = _orient_pools(matching)
    used = set()
    def score(p):
        s = visual_impact(p)
        if p.get("gc_weight") and p["gc_weight"] >= 7: s += 3
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_semantic_pops(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: bool(p.get("gemma_pops")) and len(p["gemma_pops"]) > 0)
    if len(photos) < len(cells):
        return []
    pop_colors: dict[str, list[dict]] = defaultdict(list)
    for p in photos:
        for pop in p["gemma_pops"]:
            c = pop.get("color", "").lower()
            if c:
                pop_colors[c].append(p)
    good = [c for c, group in pop_colors.items() if len(group) >= len(cells)]
    if not good:
        return []
    target_color = _random_from(good)
    matching = pop_colors[target_color]
    seen = set()
    unique = []
    for p in matching:
        pid = _pid(p)
        if pid not in seen:
            seen.add(pid)
            unique.append(p)
    if len(unique) < len(cells):
        return []
    pools = _orient_pools(unique)
    used_ids = set()
    def score(p):
        s = visual_impact(p)
        pop = next((pp for pp in p["gemma_pops"] if pp.get("color", "").lower() == target_color), None)
        if pop and pop.get("impact") in ("high", "dominant"): s += 4
        return s + random.random() * 8
    return _fill_cells(cells, pools, used_ids, score)


def curate_print_worthy(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: p.get("print_worthy"))
    if len(photos) < len(cells):
        return []
    pools = _orient_pools(photos)
    used = set()
    def score(p):
        s = visual_impact(p)
        if p.get("gemma_sharpness") == "sharp": s += 3
        if p.get("gemma_exposure") == "balanced": s += 2
        if p.get("gc_weight") and p["gc_weight"] >= 8: s += 3
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_gemma_vibes(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: bool(p.get("gemma_vibes")) and len(p["gemma_vibes"]) > 0)
    if len(photos) < len(cells):
        return []
    vibe_counts: dict[str, int] = defaultdict(int)
    for p in photos:
        for v in p["gemma_vibes"]:
            vibe_counts[v] += 1
    good = [v for v, c in vibe_counts.items() if c >= len(cells) * 1.5]
    if not good:
        return []
    target = _random_from(good)
    matching = [p for p in photos if target in p["gemma_vibes"]]
    pools = _orient_pools(matching)
    used = set()
    def score(p):
        s = visual_impact(p)
        shared = sum(1 for v in p["gemma_vibes"] if vibe_counts.get(v, 0) >= 5)
        s += shared * 3
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def curate_subject_gallery(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: bool(p.get("gemma_subject")))
    if len(photos) < len(cells):
        return []
    stop = {"with", "from", "that", "this", "have", "been", "they", "them", "their"}
    subject_words: dict[str, list[dict]] = defaultdict(list)
    for p in photos:
        words = p["gemma_subject"].lower().split()
        for w in words:
            w = w.strip(".,;:!?\"'()[]")
            if len(w) > 3 and w not in stop:
                subject_words[w].append(p)
    good = [w for w, g in subject_words.items() if len(cells) <= len(g) <= 200]
    if not good:
        return []
    target = _random_from(good)
    matching = subject_words[target]
    seen = set()
    unique = []
    for p in matching:
        pid = _pid(p)
        if pid not in seen:
            seen.add(pid)
            unique.append(p)
    if len(unique) < len(cells):
        return []
    pools = _orient_pools(unique)
    used = set()
    def score(p):
        return visual_impact(p) + random.random() * 3
    return _fill_cells(cells, pools, used, score)


def curate_sharpness_showcase(all_photos, cells):
    photos = _base_filter(all_photos, lambda p: bool(p.get("gemma_sharpness")))
    if len(photos) < len(cells):
        return []
    categories = ["sharp", "soft", "motion_blur"]
    viable = []
    for cat in categories:
        group = [p for p in photos if p.get("gemma_sharpness") == cat]
        if len(group) >= len(cells):
            viable.append((cat, group))
    if not viable:
        return []
    target_sharpness, matching = _random_from(viable)
    pools = _orient_pools(matching)
    used = set()
    def score(p):
        s = visual_impact(p)
        if target_sharpness == "sharp" and p.get("gc_weight") and p["gc_weight"] >= 7: s += 3
        if target_sharpness == "soft" and any(v in ("dreamy", "ethereal", "serene") for v in (p.get("vibes") or [])): s += 3
        if target_sharpness == "motion_blur" and (p.get("contrast") or 50) > 60: s += 3
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


def _fill_bento_default(photos, cells):
    filtered = [p for p in photos if p.get("thumb") and p.get("display")]
    if not filtered:
        return []
    pools = _orient_pools(filtered)
    all_pool = pools["L"] + pools["P"]
    first_pool = pools["P"] if cells[0]["orient"] == "P" else pools["L"]
    seed = _random_from(first_pool if first_pool else all_pool)
    seed_hue = seed.get("hue") or 0 if seed else 0
    used = set()
    def score(p):
        s = visual_impact(p)
        hd = _hue_dist(seed_hue, p.get("hue") or 0)
        if hd < 40: s += 3
        elif hd > 140: s += 1.5
        if p.get("parent"): s -= 2
        return s + random.random() * 8
    return _fill_cells(cells, pools, used, score)


# Curator list with weights (double-weight entries appear twice) — matches TS
CURATORS = [
    ("hero_story", curate_hero_story),
    ("hero_story", curate_hero_story),
    ("temperature_harmony", curate_temperature_harmony),
    ("color_story", curate_color_story),
    ("color_story", curate_color_story),
    ("mood_board", curate_mood_board),
    ("scene_story", curate_scene_story),
    ("depth_journey", curate_depth_journey),
    ("mono_accent", curate_mono_accent),
    ("archetype_exhibition", curate_archetype_exhibition),
    ("camera_story", curate_camera_story),
    ("night_vision", curate_night_vision),
    ("golden_hour", curate_golden_hour),
    ("face_gallery", curate_face_gallery),
    ("style_contrast", curate_style_contrast),
    ("brightness_gradient", curate_brightness_gradient),
    ("energy_flow", curate_energy_flow),
    ("energy_flow", curate_energy_flow),
    ("semantic_pops", curate_semantic_pops),
    ("print_worthy", curate_print_worthy),
    ("print_worthy", curate_print_worthy),
    ("gemma_vibes", curate_gemma_vibes),
    ("gemma_vibes", curate_gemma_vibes),
    ("subject_gallery", curate_subject_gallery),
    ("sharpness_showcase", curate_sharpness_showcase),
]


def _fill_bento(all_photos, layout):
    cells = layout["cells"]
    shuffled = _shuffle(CURATORS)
    for name, fn in shuffled[:3]:
        result = fn(all_photos, cells)
        if len(result) >= len(cells):
            return result[:len(cells)], name
    return _fill_bento_default(all_photos, cells), "default"


# ═══════════════════════════════════════════════════════════════════════════════
# 4a. Bento compositions
# ═══════════════════════════════════════════════════════════════════════════════

def _filter_by_image_type(photos: list[dict], image_type: str) -> list[dict]:
    """Filter photos by image type — matches frontend filterByImageType()."""
    if image_type == "mixed":
        return photos
    if image_type == "photo":
        return [p for p in photos if not p.get("parent")]
    # "generated" — only AI variants
    return [p for p in photos if p.get("parent")]


def _build_bentos(picks: list[dict], count: int = 80) -> list[dict]:
    """Generate bento compositions for each (device, image_type) combo.

    Produces ~30 compositions per combo × 6 combos = ~180 total.
    For "generated" the pool is small (~270), so curators often fail —
    fillBentoDefault handles these gracefully.
    """
    compositions = []
    image_types = ["photo", "generated", "mixed"]
    devices = ["desktop", "mobile"]

    # Distribute count across combos — give "generated" fewer since pool is small
    per_combo = max(10, count // len(devices))

    for image_type in image_types:
        pool = _filter_by_image_type(picks, image_type)
        usable = [p for p in pool if p.get("thumb") and p.get("display")]
        if len(usable) < 3:
            continue

        for device in devices:
            layouts = DESKTOP_LAYOUTS if device == "desktop" else MOBILE_LAYOUTS
            mixed = [l for l in layouts if _has_mixed_sizes(l)]
            if not mixed:
                continue

            # Fewer attempts for small pools (generated ~270)
            target = per_combo if len(usable) >= 100 else min(per_combo, 20)
            built = 0

            for _ in range(target * 2):  # overshoot attempts, curators may fail
                if built >= target:
                    break
                layout = _random_from(mixed)
                photos, curator = _fill_bento(pool, layout)
                if not photos:
                    continue

                hero_id = None
                hero_vi = float("-inf")
                cell_assignments = {}
                for i, p in enumerate(photos):
                    pid = _pid(p)
                    cell_assignments[str(i)] = pid
                    vi = visual_impact(p)
                    if vi > hero_vi:
                        hero_vi = vi
                        hero_id = pid

                compositions.append({
                    "layout_id": layout["id"],
                    "device": device,
                    "image_type": image_type,
                    "curator": curator,
                    "cells": cell_assignments,
                    "hero": hero_id,
                })
                built += 1

    return compositions


# ═══════════════════════════════════════════════════════════════════════════════
# 4b. Boom sets — from BoomView.tsx BOOM_DEFS
# ═══════════════════════════════════════════════════════════════════════════════

def _hue_range(p, lo, hi):
    palette = p.get("palette") or []
    if not palette or not palette[0]:
        return False
    h = _hex_to_hue(palette[0])
    if h < 0:
        return False
    if lo <= hi:
        return lo <= h <= hi
    return h >= lo or h <= hi


def _obj_has(p, *labels):
    objects = p.get("objects") or []
    for o in objects:
        lower = o.lower()
        for l in labels:
            if lower == l or l in lower:
                return True
    return False


def _vibe_has(p, *vibes):
    pv = p.get("vibes") or []
    for v in pv:
        lower = v.lower()
        for t in vibes:
            if t in lower:
                return True
    return False


def _scene_in(p, *scenes):
    return p.get("scene") in scenes


def _consensus_has(p, *tags):
    return any(c in tags for c in (p.get("consensus") or []))


def _archetype_is(p, *archetypes):
    return p.get("gc_archetype") in archetypes


def _energy_is(p, *energies):
    return p.get("gc_energy") in energies


def _gemma_vibe_has(p, *vibes):
    gv = p.get("gemma_vibes") or []
    for v in gv:
        lower = v.lower()
        for t in vibes:
            if t in lower:
                return True
    return False


BOOM_DEFS = [
    # Color sets
    {"emoji": "\U0001F339", "label": "Rouge",     "pool": lambda p: _hue_range(p, 355, 25)},
    {"emoji": "\U0001F34A", "label": "Ambre",     "pool": lambda p: _hue_range(p, 20, 40)},
    {"emoji": "\U0001F34B", "label": "Or",        "pool": lambda p: _hue_range(p, 42, 62)},
    {"emoji": "\U0001F340", "label": "\u00C9meraude", "pool": lambda p: _hue_range(p, 100, 165)},
    {"emoji": "\U0001F98B", "label": "Azur",      "pool": lambda p: _hue_range(p, 195, 250)},
    {"emoji": "\U0001F52E", "label": "Am\u00E9thyste", "pool": lambda p: _hue_range(p, 260, 315)},
    # Time
    {"emoji": "\U0001F305", "label": "Dor\u00E9", "pool": lambda p: p.get("time") == "golden hour"},
    {"emoji": "\U0001F319", "label": "Nuit",      "pool": lambda p: p.get("time") == "night"},
    {"emoji": "\U0001F30A", "label": "Cr\u00E9puscule", "pool": lambda p: p.get("time") == "blue hour"},
    # Objects
    {"emoji": "\U0001F431", "label": "Chats",     "pool": lambda p: _obj_has(p, "cat")},
    {"emoji": "\U0001F415", "label": "Chiens",    "pool": lambda p: _obj_has(p, "dog")},
    {"emoji": "\U0001F697", "label": "Routes",    "pool": lambda p: _obj_has(p, "car", "truck", "bus", "motorcycle")},
    {"emoji": "\U0001F33F", "label": "Flore",     "pool": lambda p: _obj_has(p, "potted plant", "vase")},
    {"emoji": "\U0001F37D\uFE0F", "label": "Table", "pool": lambda p: _obj_has(p, "dining table", "bowl", "cup", "wine glass")},
    {"emoji": "\U0001F4DA", "label": "Int\u00E9rieur", "pool": lambda p: _obj_has(p, "book", "chair", "couch", "bed")},
    {"emoji": "\u2602\uFE0F", "label": "Pluie",   "pool": lambda p: _obj_has(p, "umbrella")},
    {"emoji": "\U0001F464", "label": "Portraits", "pool": lambda p: _obj_has(p, "person") and (p.get("style") == "portrait" or p.get("orientation") == "portrait")},
    # Vibes
    {"emoji": "\U0001F60C", "label": "Serein",    "pool": lambda p: _vibe_has(p, "serene", "calm", "peaceful", "tranquil")},
    {"emoji": "\U0001F525", "label": "Intense",   "pool": lambda p: _vibe_has(p, "dramatic", "intense", "powerful", "bold")},
    {"emoji": "\u2728",     "label": "Onirique",  "pool": lambda p: _vibe_has(p, "ethereal", "dreamy", "magical", "mystical")},
    {"emoji": "\U0001F5A4", "label": "Sombre",    "pool": lambda p: _vibe_has(p, "dark", "moody", "somber", "melancholic")},
    {"emoji": "\U0001F389", "label": "Vivace",    "pool": lambda p: _vibe_has(p, "vibrant", "lively", "energetic", "joyful")},
    {"emoji": "\U0001F33B", "label": "Nostalgique", "pool": lambda p: _vibe_has(p, "nostalgic", "vintage", "retro", "timeless")},
    # Cameras
    {"emoji": "\U0001F4F8", "label": "Leica M8",  "pool": lambda p: p.get("camera") == "Leica M8"},
    {"emoji": "\U0001F39E\uFE0F", "label": "Film", "pool": lambda p: p.get("camera") == "Leica MP"},
    {"emoji": "\u26AA",     "label": "Monochrom", "pool": lambda p: p.get("camera") == "Leica Monochrom"},
    {"emoji": "\U0001F3A5", "label": "Osmo",      "pool": lambda p: (p.get("camera") or "").startswith("DJI")},
    {"emoji": "\U0001F4F7", "label": "Canon",     "pool": lambda p: p.get("camera") == "Canon G12"},
    # Style / grading
    {"emoji": "\U0001F3AC", "label": "Cin\u00E9ma", "pool": lambda p: p.get("grading") == "Cinematic"},
    {"emoji": "\U0001F331", "label": "Naturel",   "pool": lambda p: p.get("grading") == "Natural"},
    {"emoji": "\U0001F3AD", "label": "Analogique", "pool": lambda p: p.get("style") == "analog"},
    {"emoji": "\U0001F3DB\uFE0F", "label": "Architecture", "pool": lambda p: p.get("style") == "architecture"},
    {"emoji": "\U0001F5BC\uFE0F", "label": "Documentaire", "pool": lambda p: p.get("style") == "documentary"},
    # Scene clusters
    {"emoji": "\U0001F303", "label": "Skyline",   "pool": lambda p: _scene_in(p, "skyscraper", "downtown", "highway", "bridge")},
    {"emoji": "\U0001F3E0", "label": "Dedans",    "pool": lambda p: _scene_in(p, "indoor", "pet shop", "music studio", "car interior", "discotheque")},
    {"emoji": "\U0001F319", "label": "Souterrain", "pool": lambda p: _scene_in(p, "catacomb", "elevator shaft", "jail cell", "loading dock")},
    {"emoji": "\U0001F33F", "label": "Dehors",    "pool": lambda p: _scene_in(p, "outdoor", "sky", "zen garden", "ice floe", "construction site")},
    # Brightness / mood
    {"emoji": "\U0001F56F\uFE0F", "label": "Clair-obscur", "pool": lambda p: (p.get("brightness") or 128) < 40},
    {"emoji": "\u2600\uFE0F", "label": "Lumi\u00E8re", "pool": lambda p: (p.get("brightness") or 128) > 140},
    {"emoji": "\u2B1B",     "label": "Monochrome", "pool": lambda p: p.get("mono") is True},
    # Consensus / semantic
    {"emoji": "\U0001FAA9", "label": "Reflets",   "pool": lambda p: _consensus_has(p, "reflection")},
    {"emoji": "\U0001F464", "label": "Silhouettes", "pool": lambda p: _consensus_has(p, "silhouette")},
    {"emoji": "\U0001F3A8", "label": "Mural",     "pool": lambda p: _consensus_has(p, "mural", "graffiti")},
    # Archetypes
    {"emoji": "\U0001F6AA", "label": "Portails",  "pool": lambda p: _archetype_is(p, "portal")},
    {"emoji": "\U0001F304", "label": "Horizons",  "pool": lambda p: _archetype_is(p, "horizon", "panorama")},
    {"emoji": "\U0001F9F1", "label": "Textures",  "pool": lambda p: _archetype_is(p, "texture")},
    {"emoji": "\U0001F464", "label": "Figures",   "pool": lambda p: _archetype_is(p, "figure", "silhouette")},
    {"emoji": "\u25B3",     "label": "G\u00E9om\u00E9trie", "pool": lambda p: _archetype_is(p, "geometry")},
    {"emoji": "\u26AB",     "label": "Vide",      "pool": lambda p: _archetype_is(p, "void")},
    {"emoji": "\U0001F31F", "label": "Clusters",  "pool": lambda p: _archetype_is(p, "cluster")},
    # Energy
    {"emoji": "\u2197\uFE0F", "label": "Diagonale", "pool": lambda p: _energy_is(p, "diagonal_down", "diagonal_up")},
    {"emoji": "\u27A1\uFE0F", "label": "Flux",    "pool": lambda p: _energy_is(p, "left_to_right", "right_to_left")},
    {"emoji": "\U0001F300", "label": "Rayonnant", "pool": lambda p: _energy_is(p, "center_out", "inward")},
    {"emoji": "\u23F8\uFE0F", "label": "Statique", "pool": lambda p: _energy_is(p, "static")},
    # Gemma vibes
    {"emoji": "\U0001F30C", "label": "Myst\u00E9rieux", "pool": lambda p: _gemma_vibe_has(p, "mysterious", "enigmatic", "cryptic")},
    {"emoji": "\U0001F342", "label": "M\u00E9lancolie", "pool": lambda p: _gemma_vibe_has(p, "melanchol", "wistful", "bittersweet")},
    {"emoji": "\u2728",     "label": "Cin\u00E9matique", "pool": lambda p: _gemma_vibe_has(p, "cinematic", "filmic", "dramatic")},
    {"emoji": "\U0001F33E", "label": "Bucolique", "pool": lambda p: _gemma_vibe_has(p, "pastoral", "rustic", "bucolic", "rural")},
    {"emoji": "\U0001F3D9\uFE0F", "label": "Urbain", "pool": lambda p: _gemma_vibe_has(p, "urban", "gritty", "industrial", "concrete")},
    {"emoji": "\U0001F5BC\uFE0F", "label": "Imprim\u00E9", "pool": lambda p: p.get("print_worthy") is True},
    # Temperature
    {"emoji": "\U0001F9CA", "label": "Glacial",   "pool": lambda p: p.get("gc_temp") in ("glacial", "cool")},
    {"emoji": "\U0001F30B", "label": "Br\u00FBl\u00E2nt", "pool": lambda p: p.get("gc_temp") in ("molten", "warm")},
    {"emoji": "\U0001F4A0", "label": "N\u00E9on", "pool": lambda p: p.get("gc_temp") in ("neon", "electric")},
    # AI variants
    {"emoji": "\U0001F3A8", "label": "Art IA",    "pool": lambda p: bool(p.get("variant_type"))},
]

BOOM_MIN = 25


def _diverse_sample(pool, count, neighbors):
    """Diversity sampling — mirrors BoomView.tsx diverseSample()."""
    if len(pool) <= count:
        return _shuffle(pool)

    sorted_pool = sorted(pool, key=lambda p: -(p.get("aesthetic") or 0))
    candidates = sorted_pool[:min(len(pool), count * 5)]
    neighbor_map = neighbors or {}

    neighbor_ids = {}
    for c in candidates:
        cid = _pid(c)
        n_list = neighbor_map.get(cid, [])
        neighbor_ids[cid] = set()
        for n in n_list:
            nid = n.get("uuid") or n.get("id") or (n if isinstance(n, str) else "")
            if nid:
                neighbor_ids[cid].add(nid)

    selected = []
    sel_ids = set()
    sel_scenes: dict[str, int] = {}
    sel_vibes: dict[str, int] = {}
    sel_hues = []

    def add(photo):
        selected.append(photo)
        pid = _pid(photo)
        sel_ids.add(pid)
        sc = photo.get("scene") or ""
        sel_scenes[sc] = sel_scenes.get(sc, 0) + 1
        for v in (photo.get("vibes") or []):
            sel_vibes[v] = sel_vibes.get(v, 0) + 1
        palette = photo.get("palette") or []
        if palette and palette[0]:
            h = _hex_to_hue(palette[0])
            if h >= 0:
                sel_hues.append(h)

    add(candidates[0])

    while len(selected) < count:
        best_idx = -1
        best_score = float("-inf")

        for i, c in enumerate(candidates):
            cid = _pid(c)
            if cid in sel_ids:
                continue

            score = 0
            c_neighbors = neighbor_ids.get(cid, set())
            neighbor_overlap = 0
            if c_neighbors:
                for s in selected:
                    sid = _pid(s)
                    if sid in c_neighbors:
                        neighbor_overlap += 1
                    if sid in neighbor_ids and cid in neighbor_ids[sid]:
                        neighbor_overlap += 1
            score -= neighbor_overlap * 50

            c_scene = c.get("scene") or ""
            score -= sel_scenes.get(c_scene, 0) * 8

            for v in (c.get("vibes") or []):
                score -= sel_vibes.get(v, 0) * 3

            palette = c.get("palette") or []
            if palette and palette[0]:
                h = _hex_to_hue(palette[0])
                if h >= 0 and sel_hues:
                    min_diff = 360
                    for sh in sel_hues:
                        diff = abs(h - sh)
                        min_diff = min(min_diff, diff, 360 - diff)
                    score += min(min_diff / 10, 5)

            score += (c.get("aesthetic") or 0) * 2

            if score > best_score:
                best_score = score
                best_idx = i

        if best_idx < 0:
            break
        add(candidates[best_idx])

    return selected


def _build_boom_sets(all_photos, neighbors):
    """Build boom sets — mirrors BoomView.tsx buildBoomSets()."""
    pool = [p for p in all_photos if p.get("thumb")]
    sets = []
    shuffled_defs = _shuffle(BOOM_DEFS)

    for defn in shuffled_defs:
        matches = [p for p in pool if defn["pool"](p)]
        if len(matches) < BOOM_MIN:
            continue

        # Adaptive target density
        if len(matches) >= 100:
            target_n = 70
        elif len(matches) >= 70:
            target_n = 54
        elif len(matches) >= 50:
            target_n = 40
        else:
            target_n = 24

        sampled = _diverse_sample(matches, target_n, neighbors)

        sets.append({
            "emoji": defn["emoji"],
            "label": defn["label"],
            "photos": [_pid(p) for p in sampled],
        })

        if len(sets) >= 24:
            break

    return sets


# ═══════════════════════════════════════════════════════════════════════════════
# 4c. Game pairs — from GameView.tsx 18 strategies
# ═══════════════════════════════════════════════════════════════════════════════

CAM_CAP = 1200
MAX_APPEARANCES = 3


def _hue_diff(a, b):
    d = abs(a - b)
    return d if d <= 180 else 360 - d


def _hue_label(hue):
    labels = ["Red", "Orange", "Yellow", "Chartreuse", "Green", "Spring",
              "Cyan", "Azure", "Blue", "Violet", "Magenta", "Rose"]
    return labels[int(hue / 30) % 12]


def _build_game_pairs(all_photos, photo_map, drift):
    """Build all game pairs — mirrors GameView.tsx buildAllPairs()."""
    all_p = [p for p in all_photos if p.get("thumb")]

    # Camera-diverse sampling
    by_cam: dict[str, list] = defaultdict(list)
    for p in all_p:
        by_cam[p.get("camera") or "unknown"].append(p)
    photos = []
    for group in by_cam.values():
        if len(group) <= CAM_CAP:
            photos.extend(group)
        else:
            photos.extend(_shuffle(group)[:CAM_CAP])

    all_pairs = []

    # Strategy implementations — each returns list of {a_id, b_id, reason, strategy}
    strategies = [
        _strat_twins, _strat_chromatic, _strat_texture, _strat_timewarp,
        _strat_solitude, _strat_moodring, _strat_complement, _strat_strangers,
        _strat_lightdark, _strat_doppelganger, _strat_monochrome, _strat_bento,
        _strat_focal, _strat_camera, _strat_grading, _strat_nightday,
        _strat_consensus, _strat_silhouette, _strat_archetype, _strat_energy,
        _strat_variant,
    ]

    for strat in strategies:
        pairs = strat(photos, photo_map, drift)
        all_pairs.extend(pairs)

    # Global dedup: cap each photo at MAX_APPEARANCES
    appearances: dict[str, int] = {}
    random.shuffle(all_pairs)
    deduped = []
    for pair in all_pairs:
        a_id = pair["a"]
        b_id = pair["b"]
        ca = appearances.get(a_id, 0) + 1
        cb = appearances.get(b_id, 0) + 1
        appearances[a_id] = ca
        appearances[b_id] = cb
        if ca <= MAX_APPEARANCES and cb <= MAX_APPEARANCES:
            deduped.append(pair)

    return deduped


def _make_pair(a, b, reason, strategy):
    return {"a": _pid(a), "b": _pid(b), "reason": reason, "strategy": strategy}


def _strat_twins(photos, photo_map, drift):
    pairs = []
    seen = set()
    if not drift:
        return pairs
    for pid, neighbors in drift.items():
        a = photo_map.get(pid)
        if not a or not a.get("thumb") or (a.get("aesthetic") or 0) < 9.5:
            continue
        for nb in neighbors[:3]:
            if not nb or nb.get("score", 0) < 0.60:
                continue
            nb_id = nb.get("id") or nb.get("uuid") or ""
            b = photo_map.get(nb_id)
            if not b or not b.get("thumb") or (b.get("aesthetic") or 0) < 9.5:
                continue
            key = _canon_key(_pid(a), _pid(b))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(_make_pair(a, b, f"drift {nb['score']:.2f}", "twins"))
    return pairs


def _strat_chromatic(photos, photo_map, drift):
    buckets: dict[int, list] = defaultdict(list)
    for p in photos:
        if p.get("mono") or p.get("hue") is None or (p.get("aesthetic") or 0) < 9.5:
            continue
        bucket = int(p["hue"] / 15) % 24
        buckets[bucket].append(p)
    pairs = []
    seen = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                if len(pairs) >= 500:
                    break
                b = shuffled[j]
                if a.get("scene") == b.get("scene"):
                    continue
                if abs((a.get("brightness") or 50) - (b.get("brightness") or 50)) > 20:
                    continue
                if abs((a.get("contrast") or 50) - (b.get("contrast") or 50)) > 15:
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{_hue_label(a['hue'])} ~{round(a['hue'])}\u00B0", "chromatic"))
                break
    return pairs


def _strat_texture(photos, photo_map, drift):
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        if not p.get("depth") or not p.get("composition") or not p.get("style") or (p.get("aesthetic") or 0) < 9.5:
            continue
        key = f"{p['depth']}|{p['composition']}|{p['style']}"
        buckets[key].append(p)
    pairs = []
    seen = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                if len(pairs) >= 500:
                    break
                b = shuffled[j]
                if abs((a.get("depth_complexity") or 0) - (b.get("depth_complexity") or 0)) > 0.3:
                    continue
                if a.get("scene") == b.get("scene"):
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{a['style']} \u2014 {a['depth']}, {a['composition']}", "texture"))
                break
    return pairs


def _strat_timewarp(photos, photo_map, drift):
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        if not p.get("date") or not p.get("scene") or not p.get("style") or (p.get("aesthetic") or 0) < 9.5:
            continue
        buckets[f"{p['scene']}|{p['style']}"].append(p)
    pairs = []
    seen = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        sorted_g = sorted(group, key=lambda p: p["date"])
        for i in range(len(sorted_g) - 1):
            if len(pairs) >= 500:
                break
            a = sorted_g[i]
            for j in range(len(sorted_g) - 1, i, -1):
                if len(pairs) >= 500:
                    break
                b = sorted_g[j]
                try:
                    ya = int(a["date"][:4])
                    yb = int(b["date"][:4])
                except (ValueError, IndexError):
                    continue
                if abs(yb - ya) < 3:
                    continue
                if abs((a.get("brightness") or 50) - (b.get("brightness") or 50)) > 25:
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{a['scene']}, {a['style']} \u2014 {ya} \u2194 {yb}", "timewarp"))
                break
    return pairs


def _strat_solitude(photos, photo_map, drift):
    lonely = [p for p in photos if (p.get("aesthetic") or 0) >= 9.5 and (p.get("face_count") or 0) == 0
              and "person" not in (p.get("objects") or [])
              and p.get("saliency") and p["saliency"].get("spread", 99) < 16
              and p.get("scene") and p.get("depth")]
    buckets: dict[str, list] = defaultdict(list)
    for p in lonely:
        buckets[p["scene"]].append(p)
    pairs = []
    seen = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                if len(pairs) >= 500:
                    break
                b = shuffled[j]
                if abs((a.get("brightness") or 50) - (b.get("brightness") or 50)) > 20:
                    continue
                if a.get("depth") != b.get("depth"):
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{a['scene']} \u2014 quiet, {a['depth']}", "solitude"))
                break
    return pairs


def _strat_moodring(photos, photo_map, drift):
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        if not p.get("emotion") or not p.get("scene") or (p.get("aesthetic") or 0) < 9.5:
            continue
        buckets[f"{p['emotion']}|{p['scene']}"].append(p)
    pairs = []
    seen = set()
    for bucket_key, group in buckets.items():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                if len(pairs) >= 500:
                    break
                b = shuffled[j]
                if a.get("camera") == b.get("camera") and a.get("style") == b.get("style"):
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                emotion, scene = bucket_key.split("|", 1)
                pairs.append(_make_pair(a, b, f"{emotion} \u2014 {scene}", "moodring"))
                break
    return pairs


def _strat_complement(photos, photo_map, drift):
    colored = [p for p in photos if not p.get("mono") and p.get("hue") is not None and (p.get("aesthetic") or 0) >= 9.5]
    pairs = []
    seen = set()
    shuffled = _shuffle(colored)
    for i in range(len(shuffled)):
        if len(pairs) >= 500:
            break
        a = shuffled[i]
        for j in range(i + 1, len(shuffled)):
            if len(pairs) >= 500:
                break
            b = shuffled[j]
            diff = _hue_diff(a["hue"], b["hue"])
            if diff < 150 or diff > 210:
                continue
            shared = next((v for v in (a.get("vibes") or []) if v in (b.get("vibes") or [])), None)
            if not shared:
                continue
            key = _canon_key(_pid(a), _pid(b))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(_make_pair(a, b, f"{_hue_label(a['hue'])} \u2194 {_hue_label(b['hue'])} \u2014 {shared}", "complement"))
            break
    return pairs


def _strat_strangers(photos, photo_map, drift):
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        if not p.get("scene") or not p.get("style") or not p.get("composition") or (p.get("aesthetic") or 0) < 9.5:
            continue
        buckets[p["scene"]].append(p)
    pairs = []
    seen = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                b = shuffled[j]
                diffs = sum([a.get("time") != b.get("time"), a.get("style") != b.get("style"), a.get("grading") != b.get("grading")])
                if diffs < 2:
                    continue
                if a.get("composition") != b.get("composition"):
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{a['scene']} \u2014 {a['style']} vs {b['style']}", "strangers"))
                break
    return pairs


def _strat_lightdark(photos, photo_map, drift):
    quality = [p for p in photos if p.get("brightness") is not None and (p.get("aesthetic") or 0) >= 9.5]
    sorted_q = sorted(quality, key=lambda p: p["brightness"])
    cut = len(sorted_q) // 7  # ~15%
    darks = _shuffle(sorted_q[:cut])
    lights = _shuffle(sorted_q[-cut:])
    pairs = []
    seen = set()
    for a in darks:
        if len(pairs) >= 500:
            break
        for b in lights:
            if len(pairs) >= 500:
                break
            shared_scene = a.get("scene") and a["scene"] == b.get("scene")
            shared_vibe = any(v in (b.get("vibes") or []) for v in (a.get("vibes") or []))
            shared_obj = any(o in (b.get("objects") or []) for o in (a.get("objects") or []))
            if not shared_scene and not (shared_vibe and shared_obj):
                continue
            key = _canon_key(_pid(a), _pid(b))
            if key in seen:
                continue
            seen.add(key)
            link = a["scene"] if shared_scene else ""
            suffix = " \u2014 " + link if link else ""
            pairs.append(_make_pair(a, b, f"{round(a['brightness'])} vs {round(b['brightness'])}{suffix}", "lightdark"))
            break
    return pairs


def _strat_doppelganger(photos, photo_map, drift):
    skip = {"person", "car", "tree", "building", "sky", "wall", "floor", "window", "traffic light", "truck", "couch", "chair", "tv", "bus", "bed"}
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        if (p.get("aesthetic") or 0) < 9.5 or not p.get("depth"):
            continue
        for obj in (p.get("objects") or []):
            if obj not in skip:
                buckets[obj].append(p)
    pairs = []
    seen = set()
    for obj, group in buckets.items():
        if len(group) < 2 or len(group) > 200:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                b = shuffled[j]
                if a.get("scene") == b.get("scene"):
                    continue
                if a.get("depth") != b.get("depth"):
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{obj} \u2014 {a.get('scene', '?')} vs {b.get('scene', '?')}", "doppelganger"))
                break
    return pairs


def _strat_monochrome(photos, photo_map, drift):
    monos = [p for p in photos if p.get("mono") and p.get("scene") and p.get("composition") and (p.get("aesthetic") or 0) >= 9.5]
    color_by_scene: dict[str, list] = defaultdict(list)
    for p in photos:
        if p.get("mono") or not p.get("scene") or not p.get("composition") or (p.get("aesthetic") or 0) < 9.5:
            continue
        color_by_scene[p["scene"]].append(p)
    pairs = []
    seen = set()
    for a in _shuffle(monos):
        candidates = color_by_scene.get(a["scene"], [])
        for b in _shuffle(candidates):
            if a.get("composition") != b.get("composition"):
                continue
            key = _canon_key(_pid(a), _pid(b))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(_make_pair(a, b, f"mono \u00D7 color \u2014 {a['scene']}, {a['composition']}", "monochrome"))
            break
        if len(pairs) >= 500:
            break
    return pairs


def _strat_bento(photos, photo_map, drift):
    portraits = [p for p in photos if p.get("orientation") == "portrait" and p.get("scene") and p.get("style") and (p.get("aesthetic") or 0) >= 9.5]
    ls_by: dict[str, list] = defaultdict(list)
    for p in photos:
        if p.get("orientation") != "landscape" or not p.get("scene") or not p.get("style") or (p.get("aesthetic") or 0) < 9.5:
            continue
        ls_by[f"{p['scene']}|{p['style']}"].append(p)
    pairs = []
    seen = set()
    for a in _shuffle(portraits):
        k = f"{a['scene']}|{a['style']}"
        candidates = ls_by.get(k, [])
        for b in _shuffle(candidates):
            key = _canon_key(_pid(a), _pid(b))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(_make_pair(a, b, f"portrait \u00D7 landscape \u2014 {a['scene']}, {a['style']}", "bento"))
            break
        if len(pairs) >= 500:
            break
    return pairs


def _strat_focal(photos, photo_map, drift):
    with_sal = [p for p in photos if (p.get("aesthetic") or 0) >= 9.5 and p.get("saliency") and p.get("depth") and p.get("scene")]
    buckets: dict[str, list] = defaultdict(list)
    for p in with_sal:
        sal = p["saliency"]
        qx = "L" if sal.get("px", 0.5) < 0.5 else "R"
        qy = "T" if sal.get("py", 0.5) < 0.5 else "B"
        buckets[f"{qx}{qy}|{p['depth']}"].append(p)
    pairs = []
    seen = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                if len(pairs) >= 500:
                    break
                b = shuffled[j]
                if a.get("scene") == b.get("scene"):
                    continue
                sp_dist = math.hypot(a["saliency"]["px"] - b["saliency"]["px"], a["saliency"]["py"] - b["saliency"]["py"])
                if sp_dist > 0.2:
                    continue
                if abs((a.get("brightness") or 50) - (b.get("brightness") or 50)) > 20:
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"focal match \u2014 {a['depth']}", "focal"))
                break
    return pairs


def _strat_camera(photos, photo_map, drift):
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        if not p.get("camera") or not p.get("scene") or (p.get("aesthetic") or 0) < 9.5:
            continue
        buckets[p["camera"]].append(p)
    pairs = []
    seen = set()
    for cam, group in buckets.items():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                if len(pairs) >= 500:
                    break
                b = shuffled[j]
                if a.get("scene") == b.get("scene"):
                    continue
                if a.get("time") == b.get("time") and a.get("grading") == b.get("grading"):
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{cam} \u2014 {a.get('scene', '?')} vs {b.get('scene', '?')}", "camera"))
                break
    return pairs


def _strat_grading(photos, photo_map, drift):
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        if not p.get("scene") or not p.get("grading") or (p.get("aesthetic") or 0) < 9.5:
            continue
        buckets[p["scene"]].append(p)
    pairs = []
    seen = set()
    for scene, group in buckets.items():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                if len(pairs) >= 500:
                    break
                b = shuffled[j]
                if a.get("grading") == b.get("grading"):
                    continue
                cin_nat = {a.get("grading"), b.get("grading")} == {"Cinematic", "Natural"}
                mono_any = (a.get("grading") == "Monochrome") != (b.get("grading") == "Monochrome")
                if not cin_nat and not mono_any:
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{scene} \u2014 {a['grading']} vs {b['grading']}", "grading"))
                break
    return pairs


def _strat_nightday(photos, photo_map, drift):
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        if not p.get("scene") or not p.get("time") or (p.get("aesthetic") or 0) < 9.5:
            continue
        buckets[p["scene"]].append(p)
    night_times = {"night"}
    day_times = {"midday", "golden hour"}
    pairs = []
    seen = set()
    for scene, group in buckets.items():
        nights = _shuffle([p for p in group if p.get("time") in night_times])
        days = _shuffle([p for p in group if p.get("time") in day_times])
        if not nights or not days:
            continue
        for a in nights:
            if len(pairs) >= 500:
                break
            for b in days:
                if len(pairs) >= 500:
                    break
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{scene} \u2014 {a['time']} vs {b['time']}", "nightday"))
                break
    return pairs


def _strat_consensus(photos, photo_map, drift):
    skip = {"car", "person", "night", "interior", "monochrome"}
    tagged = [p for p in photos if (p.get("aesthetic") or 0) >= 9.5 and p.get("consensus") and len(p["consensus"]) >= 2 and p.get("scene")]
    pairs = []
    seen = set()
    shuffled = _shuffle(tagged)
    for i in range(len(shuffled)):
        if len(pairs) >= 500:
            break
        a = shuffled[i]
        a_tags = [t for t in (a.get("consensus") or []) if t not in skip]
        for j in range(i + 1, len(shuffled)):
            if len(pairs) >= 500:
                break
            b = shuffled[j]
            if a.get("scene") == b.get("scene"):
                continue
            b_tags = set(t for t in (b.get("consensus") or []) if t not in skip)
            shared = [t for t in a_tags if t in b_tags]
            if len(shared) < 2:
                continue
            key = _canon_key(_pid(a), _pid(b))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(_make_pair(a, b, " + ".join(shared[:3]), "consensus"))
            break
    return pairs


def _strat_silhouette(photos, photo_map, drift):
    silhouettes = [p for p in photos if (p.get("aesthetic") or 0) >= 9.5 and "silhouette" in (p.get("consensus") or []) and p.get("scene")]
    faces = [p for p in photos if (p.get("aesthetic") or 0) >= 9.5 and (p.get("face_count") or 0) > 0 and p.get("scene")]
    if not silhouettes or not faces:
        return []
    pairs = []
    seen = set()
    for a in _shuffle(silhouettes):
        if len(pairs) >= 500:
            break
        for b in _shuffle(faces):
            if len(pairs) >= 500:
                break
            same_scene = a.get("scene") == b.get("scene")
            shared_vibe = any(v in (b.get("vibes") or []) for v in (a.get("vibes") or []))
            if not same_scene and not shared_vibe:
                continue
            key = _canon_key(_pid(a), _pid(b))
            if key in seen:
                continue
            seen.add(key)
            link = a["scene"] if same_scene else "shared vibe"
            pairs.append(_make_pair(a, b, f"silhouette \u00D7 portrait \u2014 {link}", "silhouette"))
            break
    return pairs


def _strat_archetype(photos, photo_map, drift):
    archetypes = ["portal", "horizon", "texture", "figure", "geometry", "void", "cluster", "reflection", "silhouette", "panorama"]
    buckets: dict[str, list] = defaultdict(list)
    for p in photos:
        arch = p.get("gc_archetype")
        if not arch or arch not in archetypes or (p.get("aesthetic") or 0) < 9.5:
            continue
        buckets[arch].append(p)
    pairs = []
    seen = set()
    for arch, group in buckets.items():
        if len(group) < 2:
            continue
        shuffled = _shuffle(group)
        for i in range(len(shuffled) - 1):
            if len(pairs) >= 500:
                break
            a = shuffled[i]
            for j in range(i + 1, len(shuffled)):
                if len(pairs) >= 500:
                    break
                b = shuffled[j]
                if a.get("scene") == b.get("scene"):
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{arch} \u2014 {a.get('scene', '?')} vs {b.get('scene', '?')}", "archetype"))
                break
    return pairs


def _strat_energy(photos, photo_map, drift):
    opposites = [("left_to_right", "right_to_left"), ("up", "down"), ("diagonal_down", "diagonal_up"), ("center_out", "inward")]
    by_energy: dict[str, list] = defaultdict(list)
    for p in photos:
        e = p.get("gc_energy")
        if not e or e == "static" or (p.get("aesthetic") or 0) < 9.5:
            continue
        by_energy[e].append(p)
    pairs = []
    seen = set()
    for ea, eb in opposites:
        group_a = _shuffle(by_energy.get(ea, []))
        group_b = _shuffle(by_energy.get(eb, []))
        if not group_a or not group_b:
            continue
        for a in group_a:
            if len(pairs) >= 500:
                break
            for b in group_b:
                if len(pairs) >= 500:
                    break
                same_scene = a.get("scene") and a["scene"] == b.get("scene")
                close_bright = abs((a.get("brightness") or 50) - (b.get("brightness") or 50)) < 25
                if not same_scene and not close_bright:
                    continue
                key = _canon_key(_pid(a), _pid(b))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(_make_pair(a, b, f"{ea} \u2194 {eb}", "energy"))
                break
    return pairs


def _strat_variant(photos, photo_map, drift):
    pairs = []
    seen = set()
    for p in photo_map.values():
        if not p.get("parent") or not p.get("variant_type") or not p.get("thumb"):
            continue
        original = photo_map.get(p["parent"])
        if not original or not original.get("thumb"):
            continue
        key = _canon_key(_pid(original), _pid(p))
        if key in seen:
            continue
        seen.add(key)
        label = p.get("style_name") or p.get("variant_type") or "variant"
        pairs.append(_make_pair(original, p, f"Original \u00D7 {label}", "variant"))
    random.shuffle(pairs)
    return pairs


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def run(picks: list[dict], all_photos: list[dict], dry: bool = False) -> None:
    """Build all experience data files."""
    # Build photo map
    photo_map = {}
    for p in all_photos:
        pid = _pid(p)
        if pid:
            photo_map[pid] = p

    # Load drift neighbors
    drift = {}
    if DRIFT_JSON.exists():
        try:
            drift = json.loads(DRIFT_JSON.read_text())
            print(f"  Loaded drift_neighbors.json ({len(drift)} entries)")
        except Exception:
            print(f"  Warning: could not load drift_neighbors.json")

    # 4a. Bento compositions (per device × image_type)
    print(f"\n  Building bento compositions...")
    bentos = _build_bentos(picks, count=80)
    print(f"  Generated {len(bentos)} bento compositions")
    # Breakdown by (device, image_type)
    combo_counts: dict[str, int] = defaultdict(int)
    for b in bentos:
        combo_counts[f"{b['device']}/{b.get('image_type', 'mixed')}"] += 1
    for combo, cnt in sorted(combo_counts.items()):
        print(f"    {combo}: {cnt}")
    curator_counts: dict[str, int] = defaultdict(int)
    for b in bentos:
        curator_counts[b["curator"]] += 1
    for name, count in sorted(curator_counts.items(), key=lambda x: -x[1]):
        print(f"    {name}: {count}")

    if not dry:
        BENTOS_JSON.write_text(json.dumps({"compositions": bentos}, separators=(",", ":")))
        print(f"  Wrote {BENTOS_JSON.name} ({BENTOS_JSON.stat().st_size / 1024:.1f} KB)")

    # 4b. Boom sets
    print(f"\n  Building boom sets...")
    boom_sets = _build_boom_sets(all_photos, drift)
    print(f"  Generated {len(boom_sets)} boom sets")
    total_photos = sum(len(s["photos"]) for s in boom_sets)
    print(f"  Total photos across sets: {total_photos}")

    if not dry:
        BOOM_JSON.write_text(json.dumps({"sets": boom_sets}, separators=(",", ":")))
        print(f"  Wrote {BOOM_JSON.name} ({BOOM_JSON.stat().st_size / 1024:.1f} KB)")

    # 4c. Game pairs
    print(f"\n  Building game pairs...")
    pairs = _build_game_pairs(all_photos, photo_map, drift)
    strat_counts: dict[str, int] = defaultdict(int)
    for pair in pairs:
        strat_counts[pair.get("strategy", "?")] += 1
    print(f"  Generated {len(pairs)} deduplicated pairs from {len(strat_counts)} strategies")
    for name, count in sorted(strat_counts.items(), key=lambda x: -x[1]):
        print(f"    {name}: {count}")

    if not dry:
        PAIRS_JSON.write_text(json.dumps({"pairs": pairs}, separators=(",", ":")))
        print(f"  Wrote {PAIRS_JSON.name} ({PAIRS_JSON.stat().st_size / 1024:.1f} KB)")
