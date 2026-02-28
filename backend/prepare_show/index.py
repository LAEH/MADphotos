"""Phase 3 — Build lookup indices for Show experiences.

Pre-builds color buckets, subject words, semantic pops, and categorical indices
that views currently rebuild on every call.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

from . import INDEX_JSON

NUM_BUCKETS = 24
STOP_WORDS = {
    "with", "from", "that", "this", "have", "been", "they", "them", "their",
    "into", "over", "under", "about", "some", "what", "when", "where", "which",
    "while", "after", "before", "between", "through", "against", "along",
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out",
}


def _hex_to_hue(hex_str: str) -> float:
    """Convert hex color to hue (0-360). Returns -1 if invalid."""
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


def _is_gray(palette: list[str]) -> bool:
    """Check if all palette entries are low-saturation (gray)."""
    if not palette:
        return False
    for hex_str in palette:
        if not hex_str or len(hex_str) < 7:
            continue
        try:
            r = int(hex_str[1:3], 16)
            g = int(hex_str[3:5], 16)
            b = int(hex_str[5:7], 16)
        except (ValueError, IndexError):
            continue
        if (max(r, g, b) - min(r, g, b)) >= 30:
            return False
    return True


def _build_color_buckets(picks: list[dict]) -> dict[str, list[str]]:
    """Build 24 hue buckets + 1 gray bucket → photo IDs."""
    bucket_size = 360 / NUM_BUCKETS
    buckets: dict[str, list[str]] = {}
    for i in range(NUM_BUCKETS):
        hue_start = i * bucket_size
        buckets[f"hue_{int(hue_start)}"] = []
    buckets["gray"] = []

    for p in picks:
        pid = p.get("id") or p.get("uuid")
        if not pid:
            continue
        if p.get("has_border"):
            continue
        palette = p.get("palette") or []
        if _is_gray(palette):
            buckets["gray"].append(pid)
            continue
        hue = p.get("hue", 0) or 0
        idx = min(int(hue / bucket_size), NUM_BUCKETS - 1)
        key = f"hue_{int(idx * bucket_size)}"
        buckets[key].append(pid)

    # Remove empty buckets
    return {k: v for k, v in buckets.items() if v}


def _build_subject_words(picks: list[dict]) -> dict[str, list[str]]:
    """Build word → photo IDs index from gemma_subject."""
    words: dict[str, list[str]] = defaultdict(list)
    for p in picks:
        pid = p.get("id") or p.get("uuid")
        subj = p.get("gemma_subject")
        if not pid or not subj:
            continue
        for w in subj.lower().split():
            w = w.strip(".,;:!?\"'()[]")
            if len(w) > 3 and w not in STOP_WORDS:
                words[w].append(pid)

    # Keep only words with 6-200 occurrences (meaningful clusters)
    return {w: ids for w, ids in words.items() if 6 <= len(ids) <= 200}


def _build_semantic_pops(picks: list[dict]) -> dict[str, list[str]]:
    """Build color → photo IDs from gemma_pops."""
    pops: dict[str, list[str]] = defaultdict(list)
    for p in picks:
        pid = p.get("id") or p.get("uuid")
        if not pid or not p.get("gemma_pops"):
            continue
        seen = set()
        for pop in p["gemma_pops"]:
            color = pop.get("color", "").lower()
            if color and pid not in seen:
                pops[color].append(pid)
                seen.add(pid)
    return {c: ids for c, ids in pops.items() if len(ids) >= 3}


def _build_categorical_index(picks: list[dict], field: str) -> dict[str, list[str]]:
    """Build category → photo IDs for a single-value field."""
    idx: dict[str, list[str]] = defaultdict(list)
    for p in picks:
        pid = p.get("id") or p.get("uuid")
        val = p.get(field)
        if pid and val:
            idx[val].append(pid)
    return {k: v for k, v in idx.items() if len(v) >= 3}


def _build_list_index(picks: list[dict], field: str) -> dict[str, list[str]]:
    """Build category → photo IDs for a list-valued field."""
    idx: dict[str, list[str]] = defaultdict(list)
    for p in picks:
        pid = p.get("id") or p.get("uuid")
        vals = p.get(field)
        if pid and vals and isinstance(vals, list):
            for v in vals:
                if v:
                    idx[v].append(pid)
    return {k: v for k, v in idx.items() if len(v) >= 3}


def run(picks: list[dict], all_photos: list[dict], dry: bool = False) -> dict:
    """Build all lookup indices. Returns the index dict."""
    result = {}

    # Color buckets
    color_buckets = _build_color_buckets(picks)
    result["color_buckets"] = color_buckets
    total_bucketed = sum(len(v) for v in color_buckets.values())
    print(f"  color_buckets: {len(color_buckets)} buckets, {total_bucketed} photos")

    # Subject words
    subject_words = _build_subject_words(picks)
    result["subject_words"] = subject_words
    print(f"  subject_words: {len(subject_words)} words")

    # Semantic pops
    semantic_pops = _build_semantic_pops(picks)
    result["semantic_pops"] = semantic_pops
    print(f"  semantic_pops: {len(semantic_pops)} colors")

    # Categorical indices
    for field in ("scene", "gc_archetype", "gc_energy", "gc_temp", "grading", "style", "time", "camera"):
        idx = _build_categorical_index(picks, field)
        result[f"{field}_index"] = idx
        print(f"  {field}_index: {len(idx)} categories")

    # List indices
    for field in ("vibes", "gemma_vibes"):
        idx = _build_list_index(picks, field)
        result[f"{field}_index"] = idx
        print(f"  {field}_index: {len(idx)} categories")

    # Mood index from emotion field
    mood_idx = _build_categorical_index(picks, "emotion")
    result["mood_index"] = mood_idx
    print(f"  mood_index: {len(mood_idx)} moods")

    if not dry:
        INDEX_JSON.write_text(json.dumps(result, separators=(",", ":")))
        size_kb = INDEX_JSON.stat().st_size / 1024
        print(f"  Wrote {INDEX_JSON.name} ({size_kb:.1f} KB)")
    else:
        size_est = len(json.dumps(result, separators=(",", ":"))) / 1024
        print(f"  DRY: would write {INDEX_JSON.name} (~{size_est:.1f} KB)")

    return result
