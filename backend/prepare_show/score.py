"""Phase 2 — Pre-compute visual_impact and crop_fitness scores.

Direct translation of BentoView.tsx visualImpact() and cropFitness().
"""
from __future__ import annotations

import json

from . import SCORES_JSON, BENTO_UNIT_RATIO
from backend.bento.ratios import ratio_to_crop_key as _bento_ratio_to_key


def visual_impact(p: dict) -> float:
    """Visual impact score — mirrors BentoView.tsx visualImpact()."""
    av2 = p.get("aesthetic_v2")
    if av2 is not None:
        s = (av2 - 17) / 3.1
    else:
        s = (p.get("aesthetic") or 5) * 1.5

    if (p.get("contrast") or 50) > 70:
        s += 1.5
    if (p.get("depth_complexity") or 0) > 3:
        s += 1
    sal = p.get("saliency")
    if sal and sal.get("spread", 1) < 0.3:
        s += 1.5
    gc_w = p.get("gc_weight")
    if gc_w is not None:
        s += (gc_w - 5) * 0.5
    if p.get("mono"):
        s += 0.5
    gs = p.get("gemma_sharpness")
    if gs == "sharp":
        s += 1
    elif gs == "motion_blur":
        s += 0.3
    if p.get("gemma_exposure") == "balanced":
        s += 0.5
    gc_e = p.get("gc_energy")
    if gc_e and gc_e != "static":
        s += 0.5
    return s


def crop_fitness(p: dict, ratio_key: str) -> float:
    """Crop fitness for a given aspect ratio key — mirrors BentoView.tsx cropFitness().

    ratio_key: '16:9', '3:2', '2:3', or '1:1'
    """
    crops = p.get("gemma_crops")
    if not crops:
        return 0.0
    crop = crops.get(ratio_key)
    if not crop:
        return 0.0
    coverage = crop.get("coverage", 50)
    return (coverage - 50) * 0.06


def ratio_to_key(ratio: float) -> str:
    """Map cell aspect ratio to crop key — delegates to bento.ratios."""
    return _bento_ratio_to_key(ratio)


def run(picks: list[dict], dry: bool = False) -> dict:
    """Compute scores for all picks. Returns the scores dict."""
    scores = {}
    for p in picks:
        pid = p.get("id") or p.get("uuid")
        if not pid:
            continue
        vi = visual_impact(p)
        # Crop fitness for all 4 standard ratios
        cf = {}
        for key in ("1:1", "2:3", "3:2", "16:9"):
            val = crop_fitness(p, key)
            if val != 0.0:
                cf[key] = round(val, 3)
        scores[pid] = {"vi": round(vi, 2)}
        if cf:
            scores[pid]["cf"] = cf

    result = {"scores": scores}
    print(f"  Computed scores for {len(scores)} picks")

    # Stats
    vi_values = [s["vi"] for s in scores.values()]
    if vi_values:
        print(f"  visual_impact: min={min(vi_values):.1f}, max={max(vi_values):.1f}, "
              f"mean={sum(vi_values) / len(vi_values):.1f}")

    if not dry:
        SCORES_JSON.write_text(json.dumps(result, separators=(",", ":")))
        size_kb = SCORES_JSON.stat().st_size / 1024
        print(f"  Wrote {SCORES_JSON.name} ({size_kb:.1f} KB)")
    else:
        print(f"  DRY: would write {SCORES_JSON.name}")

    return result
