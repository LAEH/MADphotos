"""Photo-to-cell assignment algorithm for bento layouts.

Extracted from prepare_show/curate.py. Assigns photos to cells based on
orientation match and crop fitness scoring.
"""
from __future__ import annotations

from . import UNIT_RATIO
from .ratios import ratio_to_crop_key


def orient_pools(photos: list[dict]) -> dict[str, list[dict]]:
    """Split photos by orientation into P (portrait) and L (landscape/square) pools."""
    return {
        "P": [p for p in photos if p.get("orientation") == "portrait"],
        "L": [p for p in photos if p.get("orientation") in ("landscape", "square")],
    }


def crop_fitness(photo: dict, ratio_key: str) -> float:
    """Score how well a photo fits a given crop ratio.

    ratio_key: '16:9', '3:2', '2:3', or '1:1'
    """
    crops = photo.get("gemma_crops")
    if not crops:
        return 0.0
    crop = crops.get(ratio_key)
    if not crop:
        return 0.0
    coverage = crop.get("coverage", 50)
    return (coverage - 50) * 0.06


def _pid(p: dict) -> str:
    return p.get("id") or p.get("uuid") or ""


def fill_cells(
    cells: list[dict],
    pools: dict[str, list[dict]],
    used_ids: set[str],
    score_fn,
) -> list[dict]:
    """Smart cell assignment — matches BentoView.tsx fillCells().

    Assigns photos to cells largest-first, preferring orientation match
    and crop fitness. Falls back to opposite orientation if primary pool
    is exhausted.
    """
    indexed = [(i, cell, cell["rs"] * cell["cs"]) for i, cell in enumerate(cells)]
    sorted_cells = sorted(indexed, key=lambda x: -x[2])

    result: list[dict | None] = [None] * len(cells)
    claimed: set[str] = set()

    for i, cell, _size in sorted_cells:
        primary = pools["P"] if cell["orient"] == "P" else pools["L"]
        fallback = pools["L"] if cell["orient"] == "P" else pools["P"]

        best = None
        best_score = float("-inf")

        ratio = (cell["cs"] * UNIT_RATIO) / cell["rs"]
        rkey = ratio_to_crop_key(ratio)

        for p in primary:
            pid = _pid(p)
            if pid in used_ids or pid in claimed:
                continue
            s = score_fn(p) + crop_fitness(p, rkey)
            if s > best_score:
                best_score = s
                best = p

        if not best:
            for p in fallback:
                pid = _pid(p)
                if pid in used_ids or pid in claimed:
                    continue
                s = score_fn(p) + crop_fitness(p, rkey)
                if s > best_score:
                    best_score = s
                    best = p

        if best:
            result[i] = best
            claimed.add(_pid(best))
            used_ids.add(_pid(best))

    # Second pass: fill empty slots from combined pool
    all_remaining = pools["P"] + pools["L"]
    for i in range(len(result)):
        if result[i] is not None:
            continue
        best = None
        best_score = float("-inf")
        for p in all_remaining:
            pid = _pid(p)
            if pid in used_ids or pid in claimed:
                continue
            s = score_fn(p)
            if s > best_score:
                best_score = s
                best = p
        if best:
            result[i] = best
            claimed.add(_pid(best))
            used_ids.add(_pid(best))

    return [p for p in result if p is not None]
