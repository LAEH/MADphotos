"""Phase 1 — Data freshness and signal coverage report."""
from __future__ import annotations


def run(all_photos: list[dict], picks: list[dict]) -> None:
    """Print signal coverage report. No files written."""
    total = len(all_photos)
    n_picks = len(picks)
    variants = [p for p in all_photos if p.get("parent")]

    portrait = sum(1 for p in picks if p.get("orientation") == "portrait")
    landscape = sum(1 for p in picks if p.get("orientation") in ("landscape", "square"))

    print(f"  Total photos:   {total}")
    print(f"  Picks:          {n_picks}")
    print(f"  Variants:       {len(variants)}")
    print(f"  Portrait:       {portrait} ({portrait * 100 // max(n_picks, 1)}%)")
    print(f"  Landscape:      {landscape} ({landscape * 100 // max(n_picks, 1)}%)")

    # Signal coverage on picks
    signals = {
        "gemma_crops":    lambda p: p.get("gemma_crops") is not None,
        "aesthetic_v2":   lambda p: p.get("aesthetic_v2") is not None,
        "gc_weight":      lambda p: p.get("gc_weight") is not None,
        "vibes":          lambda p: bool(p.get("vibes")),
        "gemma_vibes":    lambda p: bool(p.get("gemma_vibes")),
        "gemma_pops":     lambda p: bool(p.get("gemma_pops")),
        "saliency":       lambda p: p.get("saliency") is not None,
        "scene":          lambda p: bool(p.get("scene")),
        "gc_archetype":   lambda p: bool(p.get("gc_archetype")),
        "gc_energy":      lambda p: bool(p.get("gc_energy")),
        "gc_temp":        lambda p: bool(p.get("gc_temp")),
        "gemma_subject":  lambda p: bool(p.get("gemma_subject")),
        "gemma_sharpness": lambda p: bool(p.get("gemma_sharpness")),
        "print_worthy":   lambda p: p.get("print_worthy") is not None,
        "face_count":     lambda p: p.get("face_count") is not None,
        "objects":        lambda p: bool(p.get("objects")),
        "consensus":      lambda p: bool(p.get("consensus")),
        "palette":        lambda p: bool(p.get("palette")),
        "hue":            lambda p: p.get("hue") is not None,
        "depth_complexity": lambda p: p.get("depth_complexity") is not None,
        "brightness":     lambda p: p.get("brightness") is not None,
        "contrast":       lambda p: p.get("contrast") is not None,
        "mono":           lambda p: p.get("mono") is not None,
    }

    print(f"\n  Signal coverage ({n_picks} picks):")
    print(f"  {'Signal':<20} {'Count':>6} {'%':>6}")
    print(f"  {'─' * 34}")

    for name, test in signals.items():
        count = sum(1 for p in picks if test(p))
        pct = count * 100 // max(n_picks, 1)
        marker = "" if pct >= 90 else " ⚠" if pct >= 50 else " ✗"
        print(f"  {name:<20} {count:>6} {pct:>5}%{marker}")
