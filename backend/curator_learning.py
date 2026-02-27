#!/usr/bin/env python3
"""
curator_learning.py — Thompson Sampling for bento curator selection.

Each curator has Beta(alpha, beta) distribution parameters:
  - alpha += 1 per love
  - beta += 1 per skip (estimated from session data)

Exports weights to curator_weights.json for the frontend to use
in weighted random curator selection.

Usage:
    python3 -m backend.curator_learning                # update from votes + export
    python3 -m backend.curator_learning --export       # export only (no DB update)
    python3 -m backend.curator_learning --stats        # show current weights
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEIGHTS_PATH = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "curator_weights.json"
STATE_PATH = PROJECT_ROOT / "images" / "curator_learning_state.json"
LOVES_DIR = PROJECT_ROOT / "images" / "rendered" / "bentos"

# Default curators — these match the frontend CURATORS array names
DEFAULT_CURATORS = [
    "curateHeroStory",
    "curateTemperatureHarmony",
    "curateColorStory",
    "curateMoodBoard",
    "curateSceneStory",
    "curateDepthJourney",
    "curateMonoAccent",
    "curateArchetypeExhibition",
    "curateCameraStory",
    "curateNightVision",
    "curateGoldenHour",
    "curateFaceGallery",
    "curateStyleContrast",
    "curateBrightnessGradient",
    "curateEnergyFlow",
    "curateSemanticPops",
    "curatePrintWorthy",
    "curateGemmaVibes",
    "curateSubjectGallery",
    "curateSharpnessShowcase",
    "default",
]


def load_state() -> dict:
    """Load curator learning state (alpha/beta per curator)."""
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    # Initialize with uniform priors
    return {name: {"alpha": 1.0, "beta": 1.0} for name in DEFAULT_CURATORS}


def save_state(state: dict):
    """Persist learning state."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def update_from_loves(state: dict) -> int:
    """Scan rendered bentos for curator metadata, update alpha counts.
    Returns number of new loves processed."""
    if not LOVES_DIR.exists():
        return 0

    # Track which bentos we've already processed
    processed = set(state.get("_processed", []))
    new_count = 0

    for meta_file in LOVES_DIR.glob("*_meta.json"):
        bento_id = meta_file.stem.replace("_meta", "")
        if bento_id in processed:
            continue

        try:
            meta = json.loads(meta_file.read_text())
        except (json.JSONDecodeError, IOError):
            continue

        curator = meta.get("curator", "default")
        if curator not in state:
            state[curator] = {"alpha": 1.0, "beta": 1.0}
        state[curator]["alpha"] += 1.0
        processed.add(bento_id)
        new_count += 1

    state["_processed"] = list(processed)
    return new_count


def thompson_sample(state: dict) -> list[tuple[str, float]]:
    """Sample from each curator's Beta distribution, return sorted list."""
    samples = []
    for name, params in state.items():
        if name.startswith("_"):
            continue
        alpha = params.get("alpha", 1.0)
        beta_val = params.get("beta", 1.0)
        sample = random.betavariate(alpha, beta_val)
        samples.append((name, sample))
    samples.sort(key=lambda x: -x[1])
    return samples


def export_weights(state: dict):
    """Export curator weights for the frontend."""
    weights = {}
    for name, params in state.items():
        if name.startswith("_"):
            continue
        alpha = params.get("alpha", 1.0)
        beta_val = params.get("beta", 1.0)
        # Expected value of Beta distribution = alpha / (alpha + beta)
        weight = alpha / (alpha + beta_val)
        weights[name] = round(weight, 4)

    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_PATH.write_text(json.dumps(weights, indent=2))
    print(f"Exported {len(weights)} curator weights to {WEIGHTS_PATH}")
    return weights


def print_stats(state: dict):
    """Print current curator statistics."""
    print(f"\n{'Curator':<30} {'Alpha':>7} {'Beta':>7} {'Weight':>8} {'Loves':>7}")
    print("-" * 65)
    for name, params in sorted(state.items()):
        if name.startswith("_"):
            continue
        alpha = params.get("alpha", 1.0)
        beta_val = params.get("beta", 1.0)
        weight = alpha / (alpha + beta_val)
        loves = int(alpha - 1)  # subtract prior
        print(f"{name:<30} {alpha:>7.1f} {beta_val:>7.1f} {weight:>8.4f} {loves:>7}")
    total_loves = sum(int(p.get("alpha", 1) - 1) for n, p in state.items() if not n.startswith("_"))
    print(f"\nTotal loves: {total_loves}")


def main():
    parser = argparse.ArgumentParser(description="Curator learning via Thompson Sampling")
    parser.add_argument("--export", action="store_true", help="Export weights only")
    parser.add_argument("--stats", action="store_true", help="Show current weights")
    args = parser.parse_args()

    state = load_state()

    if args.stats:
        print_stats(state)
        return

    if not args.export:
        new = update_from_loves(state)
        if new > 0:
            print(f"Processed {new} new loves")
            save_state(state)
        else:
            print("No new loves to process")

    weights = export_weights(state)
    print_stats(state)


if __name__ == "__main__":
    main()
