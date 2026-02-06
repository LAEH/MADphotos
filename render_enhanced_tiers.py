#!/usr/bin/env python3
"""
render_enhanced_tiers.py — Render serving tiers for enhanced v1 images.

Source: rendered/enhanced/jpeg/{uuid}.jpg (2048px)
Output: rendered/enhanced/{tier}/{format}/{uuid}.ext

Tiers: display (already exists), mobile (1280), thumb (480), micro (64)
Formats: jpeg always, webp for all tiers
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter

BASE_DIR = Path(__file__).resolve().parent
ENHANCED_DIR = BASE_DIR / "rendered" / "enhanced"
SOURCE_DIR = ENHANCED_DIR / "jpeg"  # existing 2048px jpegs


@dataclass
class TierConfig:
    name: str
    long_edge: int
    jpeg_quality: int
    webp_quality: Optional[int]
    progressive: bool
    subsampling: int
    sharpen: Optional[tuple]


# Serving tiers for enhanced images (source is 2048px)
TIERS = [
    TierConfig("display", 2048, 88, 82, True,  1, None),       # webp only (jpeg exists)
    TierConfig("mobile",  1280, 85, 80, True,  1, (0.4, 50, 2)),
    TierConfig("thumb",    480, 82, 78, False, 2, (0.3, 60, 2)),
    TierConfig("micro",     64, 70, 68, False, 2, None),
]


def render_one(source_path_str: str) -> Optional[str]:
    """Process one enhanced image into all tiers."""
    source_path = Path(source_path_str)
    uuid_stem = source_path.stem  # e.g. "abc-def-123"

    try:
        img = Image.open(source_path)
        img.load()
        img = img.convert("RGB")
        w, h = img.size
        created = 0

        for tier in TIERS:
            long_edge = max(w, h)

            if long_edge > tier.long_edge:
                ratio = tier.long_edge / long_edge
                new_size = (int(w * ratio), int(h * ratio))
                tier_img = img.resize(new_size, Image.LANCZOS)
            else:
                tier_img = img.copy()

            if tier.sharpen:
                tier_img = tier_img.filter(ImageFilter.UnsharpMask(*tier.sharpen))

            # JPEG (skip display — already exists as source)
            if tier.name != "display":
                jpeg_dir = ENHANCED_DIR / tier.name / "jpeg"
                jpeg_dir.mkdir(parents=True, exist_ok=True)
                jpeg_path = jpeg_dir / f"{uuid_stem}.jpg"
                if not jpeg_path.exists():
                    tier_img.save(jpeg_path, format="JPEG",
                                  quality=tier.jpeg_quality, optimize=True,
                                  progressive=tier.progressive,
                                  subsampling=tier.subsampling)
                    created += 1

            # WebP for all tiers
            if tier.webp_quality is not None:
                webp_dir = ENHANCED_DIR / tier.name / "webp"
                webp_dir.mkdir(parents=True, exist_ok=True)
                webp_path = webp_dir / f"{uuid_stem}.webp"
                if not webp_path.exists():
                    tier_img.save(webp_path, format="WEBP",
                                  quality=tier.webp_quality,
                                  method=4, exact=False)
                    created += 1

        return f"{uuid_stem}: {created} new" if created > 0 else None

    except Exception as e:
        return f"ERROR {uuid_stem}: {e}"


def main():
    sources = sorted(SOURCE_DIR.glob("*.jpg"))
    total = len(sources)
    print(f"Enhanced v1 tier rendering — {total} source images")
    print(f"Tiers: display(webp), mobile, thumb, micro")

    # Check what's already done
    existing_mobile = len(list((ENHANCED_DIR / "mobile" / "jpeg").glob("*.jpg"))) if (ENHANCED_DIR / "mobile" / "jpeg").exists() else 0
    remaining = total - existing_mobile
    print(f"Already rendered: {existing_mobile}, remaining: ~{remaining}")

    if remaining == 0:
        print("All tiers already rendered!")
        return

    workers = min(cpu_count(), 8)
    print(f"Using {workers} workers\n")

    source_paths = [str(p) for p in sources]
    done = 0
    errors = 0

    with Pool(workers) as pool:
        for result in pool.imap_unordered(render_one, source_paths, chunksize=20):
            done += 1
            if result and "ERROR" in result:
                errors += 1
                print(f"  {result}")
            if done % 500 == 0 or done == total:
                print(f"  {done}/{total} processed ({errors} errors)")

    # Summary
    for tier in TIERS:
        for fmt in ["jpeg", "webp"]:
            d = ENHANCED_DIR / tier.name / fmt
            if d.exists():
                count = len(list(d.iterdir()))
                print(f"  {tier.name}/{fmt}: {count} files")


if __name__ == "__main__":
    main()
