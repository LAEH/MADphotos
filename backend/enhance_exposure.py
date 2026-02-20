#!/usr/bin/env python3
"""
enhance_exposure.py — Exposure-only enhancement for dim analog images.

Applies ONLY brightness corrections (gamma + shadow lift) without touching
colors, white balance, contrast, saturation, or sharpening. This preserves
the original Portra film character while lifting dark/dim images.

Usage:
    python3 enhance_exposure.py                     # Process pre-selected 100 UUIDs
    python3 enhance_exposure.py --uuids-file /tmp/enhance_candidates.json
    python3 enhance_exposure.py --dry-run            # Preview gamma values only
    python3 enhance_exposure.py --target-brightness 115  # Custom target
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

# Add parent to path for database import
sys.path.insert(0, str(Path(__file__).resolve().parent))
import database as db

PROJECT_ROOT = db.PROJECT_ROOT
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
DISPLAY_DIR = RENDERED_DIR / "display" / "jpeg"
OUTPUT_DIR = RENDERED_DIR / "enhanced_exposure" / "jpeg"
BLIND_TEST_DIR = PROJECT_ROOT / "images" / "ai_variants" / "blind_test"
JPEG_QUALITY = 92

# Target brightness — images below this get lifted
TARGET_BRIGHTNESS = 110.0


@dataclass
class ExposurePlan:
    """Minimal plan: gamma + shadow lift + mild contrast."""
    image_uuid: str
    pre_brightness: float
    gamma: float = 1.0
    shadow_lift: float = 0.0
    contrast_strength: float = 0.0
    skip: bool = False
    reason: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def compute_exposure_plan(
    image_uuid: str,
    mean_brightness: float,
    shadow_pct: float,
    clip_low_pct: float,
    contrast_ratio: float,
    is_low_key: bool,
    target: float = TARGET_BRIGHTNESS,
) -> ExposurePlan:
    """Compute exposure + contrast correction. No color/saturation/WB changes."""
    plan = ExposurePlan(image_uuid=image_uuid, pre_brightness=mean_brightness)

    if is_low_key:
        plan.skip = True
        plan.reason = "Intentional low-key — preserving mood"
        return plan

    if mean_brightness >= target:
        plan.skip = True
        plan.reason = f"Already bright enough ({mean_brightness:.0f} >= {target:.0f})"
        return plan

    # Gamma correction: lift brightness towards target
    # gamma < 1.0 brightens, > 1.0 darkens
    # More aggressive: 55% of deficit (was 35%)
    deficit = (target - mean_brightness) / target
    gamma = 1.0 - deficit * 0.55
    gamma = max(0.65, min(0.95, gamma))
    plan.gamma = round(gamma, 4)
    plan.reason = f"Brightness {mean_brightness:.0f} → target ~{target:.0f}, gamma={plan.gamma:.3f}"

    # Shadow lift: if significant shadow clipping (>8%)
    if clip_low_pct > 8.0:
        excess = clip_low_pct - 8.0
        plan.shadow_lift = round(min(0.35, excess * 0.03), 4)
        plan.reason += f", shadow_lift={plan.shadow_lift:.3f} (clip={clip_low_pct:.1f}%)"

    # Mild contrast S-curve for flat/dim images
    if contrast_ratio < 0.95:
        if contrast_ratio < 0.75:
            plan.contrast_strength = 0.35
        elif contrast_ratio < 0.85:
            plan.contrast_strength = 0.25
        else:
            plan.contrast_strength = 0.15
        plan.reason += f", contrast={plan.contrast_strength:.2f} (ratio={contrast_ratio:.2f})"

    return plan


def apply_exposure(source_path: str, plan: ExposurePlan) -> Optional[Image.Image]:
    """Apply exposure + contrast enhancement. No color/saturation/WB changes."""
    try:
        img = Image.open(source_path).convert("RGB")
        arr = np.array(img, dtype=np.float64)

        # Step 1: Gamma correction (brightness lift)
        if plan.gamma != 1.0:
            arr = arr / 255.0
            arr = np.power(arr, plan.gamma)
            arr = arr * 255.0

        # Step 2: Shadow lift (selective brightening of dark pixels)
        if plan.shadow_lift > 0:
            luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
            shadow_mask = luma < 64
            if np.any(shadow_mask):
                lift_amount = plan.shadow_lift * (64 - luma[shadow_mask]) / 64.0
                for ch in range(3):
                    channel = arr[:, :, ch]
                    channel[shadow_mask] += channel[shadow_mask] * lift_amount
                    arr[:, :, ch] = channel

        # Step 3: Contrast S-curve in luminance space (preserves color)
        if plan.contrast_strength > 0:
            luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
            normalized = luma / 255.0
            curved = normalized + plan.contrast_strength * 0.15 * np.sin(np.pi * normalized * 2) / (np.pi * 2)
            curved = np.clip(curved, 0, 1) * 255.0
            ratio = np.ones_like(luma)
            safe_mask = luma > 1.0
            ratio[safe_mask] = curved[safe_mask] / luma[safe_mask]
            ratio = np.clip(ratio, 0.5, 2.0)
            for ch in range(3):
                arr[:, :, ch] *= ratio

        arr = np.clip(arr, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, "RGB")

    except Exception as e:
        print(f"  Error enhancing {plan.image_uuid}: {e}", file=sys.stderr)
        return None


def compute_post_brightness(img: Image.Image) -> float:
    """Measure brightness of enhanced image."""
    arr = np.array(img, dtype=np.float64)
    luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    return float(np.mean(luma))


def _process_one(args: Tuple[str, str, str]) -> Optional[Dict[str, Any]]:
    """Worker: enhance one image."""
    plan_json, source_path, output_path = args
    plan = ExposurePlan(**json.loads(plan_json))

    if plan.skip:
        return None

    enhanced = apply_exposure(source_path, plan)
    if enhanced is None:
        return None

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    enhanced.save(output_path, "JPEG", quality=JPEG_QUALITY, subsampling=0)

    post_brightness = compute_post_brightness(enhanced)

    return {
        "image_uuid": plan.image_uuid,
        "output_path": output_path,
        "pre_brightness": plan.pre_brightness,
        "post_brightness": post_brightness,
        "gamma": plan.gamma,
        "shadow_lift": plan.shadow_lift,
        "file_size": Path(output_path).stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exposure-only enhancement for dim analog images")
    parser.add_argument("--uuids-file", type=str, default="/tmp/enhance_candidates.json",
                        help="JSON file with list of UUIDs to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview plans only")
    parser.add_argument("--target-brightness", type=float, default=TARGET_BRIGHTNESS,
                        help=f"Target brightness (default: {TARGET_BRIGHTNESS})")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    parser.add_argument("--prep-blind-test", action="store_true",
                        help="Also prepare blind test pairs")
    args = parser.parse_args()

    # Load target UUIDs
    uuids_path = Path(args.uuids_file)
    if not uuids_path.exists():
        print(f"UUIDs file not found: {uuids_path}")
        sys.exit(1)
    uuids = json.loads(uuids_path.read_text())
    print(f"Loaded {len(uuids)} UUIDs from {uuids_path}")

    conn = db.get_connection()

    # Fetch pixel data for these images
    placeholders = ",".join("?" * len(uuids))
    rows = conn.execute(f"""
        SELECT
            i.uuid, i.filename,
            ia.mean_brightness, ia.shadow_pct, ia.clip_low_pct, ia.is_low_key,
            ia.contrast_ratio,
            t.local_path as display_path
        FROM images i
        JOIN image_analysis ia ON i.uuid = ia.image_uuid
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = 'display' AND t.format = 'jpeg' AND t.variant_id IS NULL
        WHERE i.uuid IN ({placeholders})
        ORDER BY ia.mean_brightness ASC
    """, uuids).fetchall()

    work = [dict(r) for r in rows]
    print(f"Found {len(work)} images in DB")
    print(f"Target brightness: {args.target_brightness}")
    print()

    # Compute plans
    plans: List[Tuple[ExposurePlan, str]] = []
    for item in work:
        plan = compute_exposure_plan(
            image_uuid=item["uuid"],
            mean_brightness=item["mean_brightness"],
            shadow_pct=item["shadow_pct"],
            clip_low_pct=item["clip_low_pct"],
            contrast_ratio=item["contrast_ratio"],
            is_low_key=bool(item["is_low_key"]),
            target=args.target_brightness,
        )
        if not plan.skip:
            plans.append((plan, item["display_path"]))

    print(f"Plans computed: {len(plans)} to enhance ({len(work) - len(plans)} skipped)")

    # Show plan summary
    gammas = [p.gamma for p, _ in plans]
    if gammas:
        print(f"  Gamma range: {min(gammas):.3f} - {max(gammas):.3f} (mean={sum(gammas)/len(gammas):.3f})")
        brightnesses = [p.pre_brightness for p, _ in plans]
        print(f"  Brightness range: {min(brightnesses):.0f} - {max(brightnesses):.0f}")
        shadows = [p.shadow_lift for p, _ in plans if p.shadow_lift > 0]
        if shadows:
            print(f"  Shadow lift: {len(shadows)} images, range {min(shadows):.3f} - {max(shadows):.3f}")
        contrasts = [p.contrast_strength for p, _ in plans if p.contrast_strength > 0]
        if contrasts:
            print(f"  Contrast boost: {len(contrasts)} images, range {min(contrasts):.2f} - {max(contrasts):.2f}")

    if args.dry_run:
        print("\n[DRY RUN] Plans computed. No images processed.")
        for plan, src in plans[:10]:
            print(f"  {plan.image_uuid[:8]}... brightness={plan.pre_brightness:.0f} gamma={plan.gamma:.3f} shadow={plan.shadow_lift:.3f} contrast={plan.contrast_strength:.2f}")
        if len(plans) > 10:
            print(f"  ... and {len(plans) - 10} more")
        conn.close()
        return

    # Execute
    print(f"\nEnhancing {len(plans)} images with {args.workers} workers...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()

    pool_work = []
    for plan, source_path in plans:
        output_path = str(OUTPUT_DIR / f"{plan.image_uuid}.jpg")
        pool_work.append((plan.to_json(), source_path, output_path))

    results = []
    completed = 0
    errors = 0

    with Pool(processes=args.workers) as pool:
        for result in pool.imap_unordered(_process_one, pool_work):
            if result is None:
                errors += 1
                continue
            results.append(result)
            completed += 1
            if completed % 20 == 0:
                elapsed = time.time() - start
                print(f"  {completed}/{len(plans)} ({completed/elapsed:.1f}/s)")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s — {completed} enhanced, {errors} errors")

    # Summary
    if results:
        pre_avg = sum(r["pre_brightness"] for r in results) / len(results)
        post_avg = sum(r["post_brightness"] for r in results) / len(results)
        print(f"  Average brightness: {pre_avg:.1f} → {post_avg:.1f} (+{post_avg - pre_avg:.1f})")

    # Prepare blind test
    if args.prep_blind_test or True:  # Always prep blind test
        print(f"\nPreparing blind test pairs...")
        import shutil
        BLIND_TEST_DIR.mkdir(parents=True, exist_ok=True)

        # Clean old exposure blind test files
        for f in BLIND_TEST_DIR.glob("*_exposure_*.jpg"):
            f.unlink()
        for f in BLIND_TEST_DIR.glob("*_original.jpg"):
            f.unlink()

        blind_pairs = []
        for result in results:
            uuid = result["image_uuid"]
            orig_path = DISPLAY_DIR / f"{uuid}.jpg"
            enhanced_path = OUTPUT_DIR / f"{uuid}.jpg"

            if not orig_path.exists() or not enhanced_path.exists():
                continue

            shutil.copy2(str(orig_path), str(BLIND_TEST_DIR / f"{uuid}_original.jpg"))
            shutil.copy2(str(enhanced_path), str(BLIND_TEST_DIR / f"{uuid}_enhanced_v1.jpg"))

            blind_pairs.append({
                "uuid": uuid,
                "pre_brightness": round(result["pre_brightness"], 1),
                "post_brightness": round(result["post_brightness"], 1),
                "gamma": result["gamma"],
            })

        # Write blind test JSON for the React frontend
        blind_test_json = {"pairs": [{"uuid": p["uuid"]} for p in blind_pairs]}
        blind_test_path = Path(PROJECT_ROOT) / "frontend" / "system" / "public" / "data" / "blind_test.json"
        blind_test_path.parent.mkdir(parents=True, exist_ok=True)
        blind_test_path.write_text(json.dumps(blind_test_json, indent=2))

        # Also write detailed manifest
        manifest_path = BLIND_TEST_DIR / "manifest.json"
        manifest_path.write_text(json.dumps(blind_pairs, indent=2))

        print(f"  {len(blind_pairs)} blind test pairs prepared")
        print(f"  Images: {BLIND_TEST_DIR}")
        print(f"  Frontend data: {blind_test_path}")
        print(f"  Manifest: {manifest_path}")

    conn.close()
    print("\nAll done!")


if __name__ == "__main__":
    main()
