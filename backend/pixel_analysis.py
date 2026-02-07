#!/usr/bin/env python3
"""
image_analysis.py — Programmatic pixel-level analysis for auto-enhance profiling.

Computes histogram stats, white balance, contrast, noise, and correction
recommendations for every image. Uses the display-tier JPEG (2048px) for speed.

This data complements Gemini's semantic analysis: Gemini tells us *what's in
the photo*, this tells us *what's wrong with the pixels*.

Usage:
    python image_analysis.py                  # Analyze all unprocessed
    python image_analysis.py --test 50        # Only 50 images
    python image_analysis.py --workers 6      # Override parallelism
    python image_analysis.py --force          # Re-analyze everything
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import numpy as np
from PIL import Image

import database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = db.PROJECT_ROOT
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"

# Use full tier (3840px, q92) — closest to original color truth
ANALYSIS_TIER = "full"
ANALYSIS_FORMAT = "jpeg"


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------

def analyze_image(image_path: str) -> Optional[Dict[str, Any]]:
    """Run full pixel-level analysis on a single image.

    Returns a dict of metrics, or None on error.
    """
    try:
        img = Image.open(image_path)
        img = img.convert("RGB")
        arr = np.array(img, dtype=np.float64)

        result = {}

        # --- Brightness / Luminance ---
        # ITU-R BT.601 luma
        luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        result["mean_brightness"] = float(np.mean(luma))
        result["std_brightness"] = float(np.std(luma))

        # --- Histogram clipping ---
        total_pixels = luma.size
        result["clip_low_pct"] = float(np.sum(luma < 5) / total_pixels * 100)
        result["clip_high_pct"] = float(np.sum(luma > 250) / total_pixels * 100)

        # Dynamic range: 2nd-98th percentile spread
        p2, p98 = np.percentile(luma, [2, 98])
        result["dynamic_range"] = float(p98 - p2)

        # Low-key / high-key detection
        result["is_low_key"] = 1 if result["mean_brightness"] < 60 else 0
        result["is_high_key"] = 1 if result["mean_brightness"] > 190 else 0

        # --- Channel means (for white balance) ---
        mean_r = float(np.mean(arr[:, :, 0]))
        mean_g = float(np.mean(arr[:, :, 1]))
        mean_b = float(np.mean(arr[:, :, 2]))
        result["mean_r"] = mean_r
        result["mean_g"] = mean_g
        result["mean_b"] = mean_b

        # White balance shifts (relative to green as reference)
        grey_mean = (mean_r + mean_g + mean_b) / 3.0
        if grey_mean > 0:
            result["wb_shift_r"] = float((mean_r - grey_mean) / grey_mean)
            result["wb_shift_b"] = float((mean_b - grey_mean) / grey_mean)
        else:
            result["wb_shift_r"] = 0.0
            result["wb_shift_b"] = 0.0

        # Color cast detection
        result["color_cast"] = _detect_color_cast(
            result["wb_shift_r"], result["wb_shift_b"]
        )

        # --- Saturation (HSV) ---
        # Convert to HSV via numpy for speed
        hsv = _rgb_to_hsv_fast(arr)
        sat = hsv[:, :, 1]
        result["mean_saturation"] = float(np.mean(sat))
        result["std_saturation"] = float(np.std(sat))

        # Dominant hue (weighted by saturation)
        hue = hsv[:, :, 0]  # 0-360
        # Only consider pixels with meaningful saturation
        sat_mask = sat > 0.1
        if np.sum(sat_mask) > 100:
            weighted_hue = hue[sat_mask]
            weighted_sat = sat[sat_mask]
            # Circular mean for hue
            rad = np.deg2rad(weighted_hue)
            sin_sum = np.sum(np.sin(rad) * weighted_sat)
            cos_sum = np.sum(np.cos(rad) * weighted_sat)
            mean_hue = np.rad2deg(np.arctan2(sin_sum, cos_sum)) % 360
            result["dominant_hue"] = int(round(mean_hue))
        else:
            result["dominant_hue"] = -1  # achromatic

        # --- Contrast ---
        # Michelson contrast on luminance percentiles
        if p98 + p2 > 0:
            result["contrast_ratio"] = float((p98 - p2) / (p98 + p2))
        else:
            result["contrast_ratio"] = 0.0

        # --- Noise estimate ---
        # Laplacian variance on luminance (higher = sharper/noisier)
        result["noise_estimate"] = _estimate_noise(luma)

        # --- Zone analysis (shadows / midtones / highlights) ---
        shadows = luma[luma < 64]
        midtones = luma[(luma >= 64) & (luma < 192)]
        highlights = luma[luma >= 192]
        result["shadow_pct"] = float(shadows.size / total_pixels * 100)
        result["midtone_pct"] = float(midtones.size / total_pixels * 100)
        result["highlight_pct"] = float(highlights.size / total_pixels * 100)
        result["shadow_mean"] = float(np.mean(shadows)) if shadows.size > 0 else 0.0
        result["midtone_mean"] = float(np.mean(midtones)) if midtones.size > 0 else 0.0
        result["highlight_mean"] = float(np.mean(highlights)) if highlights.size > 0 else 0.0

        # --- Estimated color temperature (Kelvin, McCamy's approximation) ---
        # Based on chromaticity of the grey-world neutral point
        result["est_color_temp"] = _estimate_color_temp(mean_r, mean_g, mean_b)

        # --- Per-channel WB in shadows vs highlights ---
        # Important: WB can differ in shadows (warm) vs highlights (cool)
        if shadows.size > 100:
            shadow_mask = luma < 64
            sr = float(np.mean(arr[:, :, 0][shadow_mask]))
            sg = float(np.mean(arr[:, :, 1][shadow_mask]))
            sb = float(np.mean(arr[:, :, 2][shadow_mask]))
            sg_mean = (sr + sg + sb) / 3.0
            result["shadow_wb_r"] = float((sr - sg_mean) / sg_mean) if sg_mean > 0 else 0.0
            result["shadow_wb_b"] = float((sb - sg_mean) / sg_mean) if sg_mean > 0 else 0.0
        else:
            result["shadow_wb_r"] = 0.0
            result["shadow_wb_b"] = 0.0

        if highlights.size > 100:
            high_mask = luma >= 192
            hr = float(np.mean(arr[:, :, 0][high_mask]))
            hg = float(np.mean(arr[:, :, 1][high_mask]))
            hb = float(np.mean(arr[:, :, 2][high_mask]))
            hg_mean = (hr + hg + hb) / 3.0
            result["highlight_wb_r"] = float((hr - hg_mean) / hg_mean) if hg_mean > 0 else 0.0
            result["highlight_wb_b"] = float((hb - hg_mean) / hg_mean) if hg_mean > 0 else 0.0
        else:
            result["highlight_wb_r"] = 0.0
            result["highlight_wb_b"] = 0.0

        # --- Histogram summary (compact) ---
        # 16-bin histogram for each channel + luminance
        hist_r, _ = np.histogram(arr[:, :, 0], bins=16, range=(0, 256))
        hist_g, _ = np.histogram(arr[:, :, 1], bins=16, range=(0, 256))
        hist_b, _ = np.histogram(arr[:, :, 2], bins=16, range=(0, 256))
        hist_l, _ = np.histogram(luma, bins=16, range=(0, 256))
        # Normalize to percentages
        result["histogram_json"] = json.dumps({
            "r": (hist_r / total_pixels * 100).round(2).tolist(),
            "g": (hist_g / total_pixels * 100).round(2).tolist(),
            "b": (hist_b / total_pixels * 100).round(2).tolist(),
            "l": (hist_l / total_pixels * 100).round(2).tolist(),
        })

        return result

    except Exception as e:
        print(f"  Error analyzing {image_path}: {e}", file=sys.stderr)
        return None


def _detect_color_cast(wb_r: float, wb_b: float) -> str:
    """Classify color cast from WB shifts."""
    threshold = 0.05  # 5% deviation from grey
    if abs(wb_r) < threshold and abs(wb_b) < threshold:
        return "none"
    if wb_r > threshold and wb_b < -threshold:
        return "warm"      # red-shifted, blue-deficient
    if wb_r < -threshold and wb_b > threshold:
        return "cool"      # blue-shifted, red-deficient
    if wb_r > threshold and wb_b > threshold:
        return "magenta"   # both red and blue elevated (green-deficient)
    if wb_r < -threshold and wb_b < -threshold:
        return "green"     # green-dominant
    if wb_r > threshold:
        return "warm"
    if wb_b > threshold:
        return "cool"
    return "none"


def _estimate_color_temp(mean_r: float, mean_g: float, mean_b: float) -> int:
    """Estimate correlated color temperature from grey-world RGB means.

    Uses a simplified version of Robertson's method. Returns Kelvin.
    Range: ~2000K (very warm/tungsten) to ~10000K (very cool/shade).
    """
    if mean_r <= 0 or mean_g <= 0 or mean_b <= 0:
        return 6500  # default daylight

    # Normalize to approximate white point
    r_norm = mean_r / mean_g
    b_norm = mean_b / mean_g

    # Heuristic mapping based on R/B ratio
    # High R/B = warm (low Kelvin), Low R/B = cool (high Kelvin)
    if b_norm < 0.001:
        return 2000
    rb_ratio = r_norm / b_norm

    # Piecewise linear approximation calibrated to common light sources
    if rb_ratio > 2.0:
        temp = 2000
    elif rb_ratio > 1.5:
        temp = int(2000 + (2.0 - rb_ratio) * 3000)
    elif rb_ratio > 1.0:
        temp = int(3500 + (1.5 - rb_ratio) * 5000)
    elif rb_ratio > 0.7:
        temp = int(6000 + (1.0 - rb_ratio) * 6667)
    else:
        temp = 10000

    return max(2000, min(10000, temp))


def _rgb_to_hsv_fast(arr: np.ndarray) -> np.ndarray:
    """Convert RGB array (float64 0-255) to HSV (H:0-360, S:0-1, V:0-255)."""
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc

    # Hue
    hue = np.zeros_like(delta)
    mask = delta > 0
    rm = mask & (maxc == r)
    gm = mask & (maxc == g) & ~rm
    bm = mask & ~rm & ~gm

    hue[rm] = 60.0 * (((g[rm] - b[rm]) / delta[rm]) % 6)
    hue[gm] = 60.0 * (((b[gm] - r[gm]) / delta[gm]) + 2)
    hue[bm] = 60.0 * (((r[bm] - g[bm]) / delta[bm]) + 4)

    # Saturation
    sat = np.zeros_like(delta)
    sat[maxc > 0] = delta[maxc > 0] / maxc[maxc > 0]

    return np.stack([hue, sat, maxc], axis=-1)


def _estimate_noise(luma: np.ndarray) -> float:
    """Estimate noise via Laplacian variance on a downsampled patch.

    Uses the robust median estimator from Immerkaer (1996).
    """
    # Downsample for speed (512px max dimension)
    h, w = luma.shape
    scale = min(1.0, 512.0 / max(h, w))
    if scale < 1.0:
        sh, sw = int(h * scale), int(w * scale)
        # Simple stride-based downsample
        step_h = max(1, h // sh)
        step_w = max(1, w // sw)
        patch = luma[::step_h, ::step_w]
    else:
        patch = luma

    # Laplacian kernel convolution via numpy
    # [0,1,0; 1,-4,1; 0,1,0]
    lap = (
        -4.0 * patch[1:-1, 1:-1]
        + patch[:-2, 1:-1] + patch[2:, 1:-1]
        + patch[1:-1, :-2] + patch[1:-1, 2:]
    )
    # Robust noise estimate (sigma = sqrt(pi/2) * median(|laplacian|) / 6)
    sigma = float(np.sqrt(np.pi / 2.0) * np.median(np.abs(lap)) / 6.0)
    return round(sigma, 3)


# ---------------------------------------------------------------------------
# Worker process
# ---------------------------------------------------------------------------

def _process_one(args: Tuple[str, str]) -> Optional[Tuple[str, Dict]]:
    """Worker function: analyze one image."""
    image_uuid, image_path = args
    result = analyze_image(image_path)
    if result is None:
        return None
    return (image_uuid, result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Programmatic image analysis")
    parser.add_argument("--test", type=int, metavar="N", default=0,
                        help="Analyze only N images")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2),
                        help="Parallel workers (default: cpu_count - 2)")
    parser.add_argument("--force", action="store_true",
                        help="Re-analyze all images (overwrite existing)")
    args = parser.parse_args()

    conn = db.get_connection()

    # Find images to analyze
    if args.force:
        rows = conn.execute("""
            SELECT i.uuid, t.local_path
            FROM images i
            JOIN tiers t ON i.uuid = t.image_uuid
                AND t.tier_name = ? AND t.format = ? AND t.variant_id IS NULL
            ORDER BY i.uuid
        """, (ANALYSIS_TIER, ANALYSIS_FORMAT)).fetchall()
    else:
        rows = conn.execute("""
            SELECT i.uuid, t.local_path
            FROM images i
            JOIN tiers t ON i.uuid = t.image_uuid
                AND t.tier_name = ? AND t.format = ? AND t.variant_id IS NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM image_analysis ia WHERE ia.image_uuid = i.uuid
            )
            ORDER BY i.uuid
        """, (ANALYSIS_TIER, ANALYSIS_FORMAT)).fetchall()

    work = [(r["uuid"], r["local_path"]) for r in rows]

    if args.test:
        work = work[:args.test]

    already = conn.execute("SELECT COUNT(*) as c FROM image_analysis").fetchone()["c"]
    total = conn.execute("SELECT COUNT(*) as c FROM images").fetchone()["c"]
    print(f"Images: {total} total | {already} analyzed | {len(work)} to process | Workers: {args.workers}")

    if not work:
        print("Nothing to analyze.")
        conn.close()
        return

    run_id = db.start_run(conn, "image_analysis", {
        "workers": args.workers, "test": args.test, "force": args.force,
    })
    start_time = time.time()
    completed = 0
    errors = 0
    now_str = datetime.now(timezone.utc).isoformat()

    with Pool(processes=args.workers) as pool:
        for result in pool.imap_unordered(_process_one, work):
            if result is None:
                errors += 1
                continue

            image_uuid, metrics = result
            conn.execute("""
                INSERT INTO image_analysis (
                    image_uuid, mean_brightness, std_brightness,
                    clip_low_pct, clip_high_pct, dynamic_range,
                    mean_saturation, std_saturation,
                    mean_r, mean_g, mean_b,
                    wb_shift_r, wb_shift_b, color_cast,
                    contrast_ratio, noise_estimate, dominant_hue,
                    is_low_key, is_high_key,
                    shadow_pct, midtone_pct, highlight_pct,
                    shadow_mean, midtone_mean, highlight_mean,
                    est_color_temp,
                    shadow_wb_r, shadow_wb_b,
                    highlight_wb_r, highlight_wb_b,
                    histogram_json, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_uuid) DO UPDATE SET
                    mean_brightness=excluded.mean_brightness,
                    std_brightness=excluded.std_brightness,
                    clip_low_pct=excluded.clip_low_pct,
                    clip_high_pct=excluded.clip_high_pct,
                    dynamic_range=excluded.dynamic_range,
                    mean_saturation=excluded.mean_saturation,
                    std_saturation=excluded.std_saturation,
                    mean_r=excluded.mean_r, mean_g=excluded.mean_g,
                    mean_b=excluded.mean_b,
                    wb_shift_r=excluded.wb_shift_r,
                    wb_shift_b=excluded.wb_shift_b,
                    color_cast=excluded.color_cast,
                    contrast_ratio=excluded.contrast_ratio,
                    noise_estimate=excluded.noise_estimate,
                    dominant_hue=excluded.dominant_hue,
                    is_low_key=excluded.is_low_key,
                    is_high_key=excluded.is_high_key,
                    shadow_pct=excluded.shadow_pct,
                    midtone_pct=excluded.midtone_pct,
                    highlight_pct=excluded.highlight_pct,
                    shadow_mean=excluded.shadow_mean,
                    midtone_mean=excluded.midtone_mean,
                    highlight_mean=excluded.highlight_mean,
                    est_color_temp=excluded.est_color_temp,
                    shadow_wb_r=excluded.shadow_wb_r,
                    shadow_wb_b=excluded.shadow_wb_b,
                    highlight_wb_r=excluded.highlight_wb_r,
                    highlight_wb_b=excluded.highlight_wb_b,
                    histogram_json=excluded.histogram_json,
                    analyzed_at=excluded.analyzed_at
            """, (
                image_uuid,
                metrics["mean_brightness"], metrics["std_brightness"],
                metrics["clip_low_pct"], metrics["clip_high_pct"],
                metrics["dynamic_range"],
                metrics["mean_saturation"], metrics["std_saturation"],
                metrics["mean_r"], metrics["mean_g"], metrics["mean_b"],
                metrics["wb_shift_r"], metrics["wb_shift_b"],
                metrics["color_cast"],
                metrics["contrast_ratio"], metrics["noise_estimate"],
                metrics["dominant_hue"],
                metrics["is_low_key"], metrics["is_high_key"],
                metrics["shadow_pct"], metrics["midtone_pct"],
                metrics["highlight_pct"],
                metrics["shadow_mean"], metrics["midtone_mean"],
                metrics["highlight_mean"],
                metrics["est_color_temp"],
                metrics["shadow_wb_r"], metrics["shadow_wb_b"],
                metrics["highlight_wb_r"], metrics["highlight_wb_b"],
                metrics["histogram_json"], now_str,
            ))
            completed += 1

            if completed % 100 == 0:
                conn.commit()
                elapsed = time.time() - start_time
                rate = completed / elapsed
                remaining = (len(work) - completed - errors) / rate if rate > 0 else 0
                print(f"  {completed}/{len(work)} analyzed ({rate:.1f}/s, ~{remaining:.0f}s remaining)")

    conn.commit()
    db.finish_run(conn, run_id, images_processed=completed, images_failed=errors)
    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s. Analyzed: {completed} | Errors: {errors}")

    # Print summary stats by camera
    print("\n--- Summary by Camera ---")
    rows = conn.execute("""
        SELECT i.camera_body,
               COUNT(*) as cnt,
               AVG(ia.mean_brightness) as avg_bright,
               AVG(ia.mean_saturation) as avg_sat,
               AVG(ia.wb_shift_r) as avg_wb_r,
               AVG(ia.wb_shift_b) as avg_wb_b,
               SUM(CASE WHEN ia.color_cast != 'none' THEN 1 ELSE 0 END) as cast_count,
               AVG(ia.contrast_ratio) as avg_contrast,
               AVG(ia.noise_estimate) as avg_noise
        FROM image_analysis ia
        JOIN images i ON ia.image_uuid = i.uuid
        GROUP BY i.camera_body
        ORDER BY cnt DESC
    """).fetchall()
    for r in rows:
        pct_cast = r["cast_count"] / r["cnt"] * 100 if r["cnt"] else 0
        cam = r['camera_body'] or 'Unknown'
        print(f"  {cam:20} n={r['cnt']:5}  "
              f"bright={r['avg_bright']:.0f}  sat={r['avg_sat']:.2f}  "
              f"wb_r={r['avg_wb_r']:+.3f}  wb_b={r['avg_wb_b']:+.3f}  "
              f"cast={pct_cast:.0f}%  contrast={r['avg_contrast']:.2f}  "
              f"noise={r['avg_noise']:.1f}")

    conn.close()


if __name__ == "__main__":
    main()
