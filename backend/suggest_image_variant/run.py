#!/usr/bin/env python3
"""
suggest_image_variant — Smart image generation pipeline.

Selects the best candidate photos using ALL available signals,
matches optimal styles per photo using learned acceptance patterns,
crafts photo-specific prompts using Gemma descriptions, and generates
via Imagen 3 with budget tracking.

Usage:
    python3 suggest_image_variant/run.py                    # Generate with $10 budget
    python3 suggest_image_variant/run.py --budget 5.00      # Custom budget
    python3 suggest_image_variant/run.py --count 50         # Limit to N source photos
    python3 suggest_image_variant/run.py --dry              # Preview selections only
    python3 suggest_image_variant/run.py --styles           # List all styles
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .config import (
    COST_PER_IMAGE,
    DB_PATH,
    DEAD_MIN_REVIEWS,
    DEAD_THRESHOLD,
    DEFAULT_BUDGET,
    DELAY_BETWEEN_CALLS,
    EXPLORE_MAX_REVIEWS,
    EXPLORE_RATE,
    GENERATED_DIR,
    PERFORMANCE_MIN_TRUST,
    STRUGGLING_MIN_REVIEWS,
    STRUGGLING_PENALTY,
    STRUGGLING_THRESHOLD,
    STYLES,
    STYLES_PER_PHOTO,
)
from .generate import (
    BudgetTracker,
    copy_original,
    create_client,
    db_upsert,
    generate_imagen,
    variant_id_for,
)
from .prompt import build_full_prompt
from .select import get_candidates, get_style_rates, parse_vibes, pick_styles


def cmd_styles() -> None:
    """Print all available styles."""
    print(f"\n{'Key':<12} {'Name':<25} {'Prompt (first 80 chars)'}")
    print("-" * 117)
    for key, style in STYLES.items():
        print(f"{key:<12} {style['name']:<25} {style['prompt'][:80]}...")
    print()


def cmd_dry(candidates: List[Dict], assignments: List[Tuple[Dict, List[str]]]) -> None:
    """Print candidate selection and style matching preview."""
    style_counts: Dict[str, int] = {}
    for _, styles in assignments:
        for s in styles:
            style_counts[s] = style_counts.get(s, 0) + 1

    total_variants = len(candidates) * STYLES_PER_PHOTO
    n_portrait = sum(1 for c in candidates if c.get("orientation") == "portrait")
    n_landscape = len(candidates) - n_portrait
    print(f"\nOrientation: {n_portrait} portrait + {n_landscape} landscape")
    print(f"Style distribution across {len(candidates)} photos ({total_variants} variants):")
    for key in sorted(style_counts, key=lambda k: -style_counts[k]):
        pct = style_counts[key] * 100 // max(total_variants, 1)
        print(f"  {STYLES[key]['name']:<25} {style_counts[key]:>4} ({pct}%)")

    est_cost = total_variants * COST_PER_IMAGE
    est_time = total_variants * DELAY_BETWEEN_CALLS / 60
    print(f"\nEstimated cost: ${est_cost:.2f}")
    print(f"Estimated time: ~{est_time:.0f} min")

    style_header = " → ".join(f"{'Style ' + str(i+1):<20}" for i in range(STYLES_PER_PHOTO))
    print(f"\n{'UUID':<38} {'Score':>5} {'Mono':>4} {'Faces':>5} {'Setting':<12} "
          f"{'Mood':<20} → {style_header}")
    print("-" * 145)
    for photo, styles in assignments[:40]:
        mood = (photo.get("gemma_mood") or "")[:18]
        setting = (photo.get("setting") or "")[:10]
        mono = "yes" if photo.get("is_monochrome") else ""
        style_names = " → ".join(f"{STYLES[s]['name']:<20}" for s in styles)
        print(f"{photo['uuid']:<38} {photo['_quality_score']:>5.0f} {mono:>4} "
              f"{photo.get('faces_count') or 0:>5} {setting:<12} "
              f"{mood:<20} → {style_names}")
    if len(assignments) > 40:
        print(f"  ... and {len(assignments) - 40} more")


def cmd_scorecard(conn: sqlite3.Connection) -> None:
    """Generate STYLES.md scorecard from DB review history."""
    rates = get_style_rates(conn)
    if not rates:
        print("No review data — nothing to score.")
        return

    # Classify each style
    entries = []
    for key, data in sorted(rates.items(), key=lambda x: -x[1]["rate"]):
        total = data["total"]
        rate = data["rate"]
        if total < PERFORMANCE_MIN_TRUST:
            status = "New"
        elif rate >= 0.60:
            status = "Star"
        elif rate >= 0.40:
            status = "Solid"
        elif rate >= 0.20:
            status = "Weak"
        elif total >= DEAD_MIN_REVIEWS and rate < DEAD_THRESHOLD:
            status = "Dead"
        elif total >= STRUGGLING_MIN_REVIEWS and rate < STRUGGLING_THRESHOLD:
            status = "Dying"
        else:
            status = "Poor"
        entries.append((key, data["accepted"], data["rejected"], total, rate, status))

    # Also list styles with no reviews at all
    for key in STYLES:
        if key not in rates:
            entries.append((key, 0, 0, 0, 0.0, "New"))

    today = datetime.now().strftime("%Y-%m-%d")
    total_reviews = sum(d["total"] for d in rates.values())
    total_accepted = sum(d["accepted"] for d in rates.values())

    lines = [
        f"# Style Transfer — Performance Scorecard",
        f"# Auto-generated from {total_reviews} reviews on {today}",
        f"# Overall acceptance: {total_accepted}/{total_reviews} "
        f"({total_accepted*100//max(total_reviews,1)}%)",
        "",
        f"| {'Style':<20} | {'Accept':>6} | {'Reject':>6} | {'Total':>5} | {'Rate':>6} | {'Status':<6} |",
        f"|{'-'*22}|{'-'*8}|{'-'*8}|{'-'*7}|{'-'*8}|{'-'*8}|",
    ]
    for key, accepted, rejected, total, rate, status in entries:
        name = STYLES.get(key, {}).get("name", key)
        rate_str = f"{rate*100:.0f}%" if total > 0 else "—"
        lines.append(
            f"| {name:<20} | {accepted:>6} | {rejected:>6} | {total:>5} | {rate_str:>6} | {status:<6} |"
        )

    lines.extend([
        "",
        "## Legend",
        f"- **Star**: ≥60% rate, ≥{PERFORMANCE_MIN_TRUST} reviews — top performer",
        f"- **Solid**: 40-59% rate, ≥{PERFORMANCE_MIN_TRUST} reviews — reliable",
        f"- **Weak**: 20-39% rate, ≥{PERFORMANCE_MIN_TRUST} reviews — underperforming",
        f"- **Poor**: <20% rate, ≥{PERFORMANCE_MIN_TRUST} reviews — struggling",
        f"- **Dying**: <{STRUGGLING_THRESHOLD*100:.0f}% rate, ≥{STRUGGLING_MIN_REVIEWS} reviews — heavy penalty ({STRUGGLING_PENALTY:+.0f} score)",
        f"- **Dead**: <{DEAD_THRESHOLD*100:.0f}% rate, ≥{DEAD_MIN_REVIEWS} reviews — auto-excluded from selection",
        f"- **New**: <{PERFORMANCE_MIN_TRUST} reviews — still being tested (gets exploration bonus)",
        "",
        "## Selection Config",
        f"- Explore rate: {EXPLORE_RATE*100:.0f}% (slot 2 picks undertested style)",
        f"- Undertested threshold: <{EXPLORE_MAX_REVIEWS} reviews",
        f"- Dead auto-exclusion: <{DEAD_THRESHOLD*100:.0f}% with ≥{DEAD_MIN_REVIEWS} reviews",
    ])

    scorecard_path = Path(__file__).resolve().parent / "STYLES.md"
    scorecard_path.write_text("\n".join(lines) + "\n")
    print(f"\nScorecard written to {scorecard_path}")

    # Also print to console
    for line in lines[:8 + len(entries)]:
        print(line)


def _check_auth() -> None:
    """Verify GCP credentials are valid before starting. Fail fast on auth issues."""
    import subprocess
    result = subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print("\n  ERROR: GCP auth expired. Run: gcloud auth application-default login")
        raise SystemExit(1)


def cmd_generate(candidates: List[Dict], assignments: List[Tuple[Dict, List[str]]],
                 budget: float) -> None:
    """Run Imagen 3 generation with budget tracking."""
    _check_auth()

    run_dir = GENERATED_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput: {run_dir}")

    tracker = BudgetTracker(budget)
    client = create_client()
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    start_time = time.time()

    try:
        for img_i, (photo, styles) in enumerate(assignments):
            if not tracker.can_continue:
                print(f"\n  Budget exhausted: {tracker.summary()}")
                break

            uid = photo["uuid"]
            source = photo["source_path"]
            img_dir = run_dir / uid
            vibes = parse_vibes(photo.get("vibe"))

            print(f"\n[{img_i+1}/{len(assignments)}] {uid}")
            print(f"  {photo['category']} {photo['orientation']} | "
                  f"{photo.get('setting', '?')} | faces={photo.get('faces_count', 0)} | "
                  f"mood={photo.get('gemma_mood', '?')} | "
                  f"score={photo['_quality_score']:.0f}")

            # Copy original for review UI
            copy_original(source, img_dir)

            for style_key in styles:
                if not tracker.can_continue:
                    print(f"\n  Budget exhausted: {tracker.summary()}")
                    break

                style = STYLES[style_key]
                vid = variant_id_for(uid, style_key)

                # Skip if already done
                row = conn.execute(
                    "SELECT generation_status FROM ai_variants WHERE variant_id=?", (vid,)
                ).fetchone()
                if row and row[0] in ("success", "filtered"):
                    print(f"  {style['name']:<25} — already done, skip")
                    continue

                prompt = build_full_prompt(style_key, photo)
                out_path = img_dir / f"imagen_smart_{style_key}.jpg"

                print(f"  {style['name']:<25} — generating...")

                t1 = time.time()
                success, error = generate_imagen(client, prompt, source, out_path)
                elapsed_ms = int((time.time() - t1) * 1000)

                if success:
                    tracker.record_success()
                    db_upsert(conn, vid, uid, style_key, prompt, "success", elapsed_ms)
                    print(f"  {style['name']:<25} — OK ({elapsed_ms/1000:.1f}s) [{tracker.summary()}]")
                elif error == "safety_filter":
                    tracker.record_filtered()
                    db_upsert(conn, vid, uid, style_key, prompt, "filtered", elapsed_ms,
                              rai_reason="safety")
                    print(f"  {style['name']:<25} — FILTERED [{tracker.summary()}]")
                else:
                    tracker.record_failed()
                    db_upsert(conn, vid, uid, style_key, prompt, "failed", elapsed_ms,
                              error=error)
                    print(f"  {style['name']:<25} — FAILED: {(error or '')[:60]}")

                # Rate limit
                wait = max(0, DELAY_BETWEEN_CALLS - (time.time() - t1))
                if wait > 0:
                    time.sleep(wait)
    finally:
        conn.close()

    elapsed_total = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Done in {elapsed_total/60:.1f} min")
    print(f"{tracker.summary()}")
    print(f"Output: {run_dir}")
    print(f"\nReview at: http://localhost:5173/system/experiments/generated")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart image generation pipeline using learned acceptance patterns"
    )
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET,
                        help=f"Max budget in USD (default: ${DEFAULT_BUDGET:.2f})")
    parser.add_argument("--count", type=int, default=0,
                        help="Limit to N source photos (default: fill budget)")
    parser.add_argument("--dry", action="store_true",
                        help="Preview selections and style matching only")
    parser.add_argument("--styles", action="store_true",
                        help="List all available styles")
    parser.add_argument("--scorecard", action="store_true",
                        help="Generate STYLES.md performance scorecard")
    parser.add_argument("--category", type=str, default=None,
                        help="Filter to a specific image category (e.g. Analog, Digital, Monochrome)")
    args = parser.parse_args()

    if args.styles:
        cmd_styles()
        return

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    if args.scorecard:
        cmd_scorecard(conn)
        conn.close()
        return

    # Load historical performance rates for style selection
    rates = get_style_rates(conn)
    if rates:
        reviewed = sum(d["total"] for d in rates.values())
        dead = [k for k, d in rates.items()
                if d["total"] >= DEAD_MIN_REVIEWS and d["rate"] < DEAD_THRESHOLD]
        struggling = [k for k, d in rates.items()
                      if d["total"] >= STRUGGLING_MIN_REVIEWS
                      and d["rate"] < STRUGGLING_THRESHOLD
                      and not (d["total"] >= DEAD_MIN_REVIEWS and d["rate"] < DEAD_THRESHOLD)]
        status_parts = [f"Loaded performance data: {len(rates)} styles, {reviewed} reviews"]
        if dead:
            status_parts.append(f"{len(dead)} dead ({', '.join(dead)})")
        if struggling:
            status_parts.append(f"{len(struggling)} struggling ({', '.join(struggling)})")
        print(", ".join(status_parts))

    # How many source photos can the budget support?
    max_photos = int(args.budget / (COST_PER_IMAGE * STYLES_PER_PHOTO))
    count = min(args.count, max_photos) if args.count > 0 else max_photos

    candidates = get_candidates(conn, count, category=args.category)

    cat_label = f" [{args.category}]" if args.category else ""
    print(f"Found {len(candidates)}{cat_label} candidate photos (budget supports {max_photos})")

    if not candidates:
        print("Nothing to do — all picked photos already have smart variants.")
        conn.close()
        return

    # Compute style assignments using performance data
    assignments = [(photo, pick_styles(photo, rates)) for photo in candidates]

    if args.dry:
        cmd_dry(candidates, assignments)
        conn.close()
        return

    cmd_generate(candidates, assignments, args.budget)

    # Auto-generate scorecard after generation
    print("\nUpdating style scorecard...")
    cmd_scorecard(conn)
    conn.close()


if __name__ == "__main__":
    main()
