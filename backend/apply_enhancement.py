#!/usr/bin/env python3
"""
apply_enhancement.py — Deploy validated exposure enhancements to production.

Reads blind-test votes, copies approved exposure-enhanced JPEGs into the
canonical enhanced/ directory, renders serving tiers, uploads to GCS,
and marks the DB so export_gallery.py can swap URLs.

Usage:
    python3 backend/apply_enhancement.py              # Full pipeline
    python3 backend/apply_enhancement.py --dry-run    # Preview only
    python3 backend/apply_enhancement.py --skip-gcs   # Skip GCS upload
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import database as db

PROJECT_ROOT = db.PROJECT_ROOT
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
ENHANCED_EXPOSURE_DIR = RENDERED_DIR / "enhanced_exposure" / "jpeg"
ENHANCED_DIR = RENDERED_DIR / "enhanced"
ENHANCED_JPEG_DIR = ENHANCED_DIR / "jpeg"
VOTES_PATH = PROJECT_ROOT / "images" / "ai_variants" / "blind_test" / "votes.json"

GCS_BASE = "gs://myproject-public-assets/art/MADphotos/v/enhanced"

TIERS = ["display", "mobile", "thumb", "micro"]
FORMATS = ["jpeg", "webp"]


def load_approved_uuids() -> List[str]:
    """Read votes.json and return UUIDs where pickedEnhanced is true."""
    if not VOTES_PATH.exists():
        print(f"ERROR: {VOTES_PATH} not found")
        print("  Export votes from the Enhance page first.")
        sys.exit(1)

    votes = json.loads(VOTES_PATH.read_text())
    approved = [v["uuid"] for v in votes if v.get("pickedEnhanced") is True]
    print(f"Step A — Read votes: {len(votes)} total, {len(approved)} approved")
    return approved


def copy_exposure_to_enhanced(uuids: List[str], dry_run: bool) -> List[str]:
    """Copy exposure-enhanced JPEGs into the canonical enhanced/jpeg/ dir."""
    ENHANCED_JPEG_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    missing = []

    for uuid in uuids:
        src = ENHANCED_EXPOSURE_DIR / f"{uuid}.jpg"
        dst = ENHANCED_JPEG_DIR / f"{uuid}.jpg"
        if not src.exists():
            missing.append(uuid)
            continue
        if not dry_run:
            shutil.copy2(src, dst)
        copied.append(uuid)

    print(f"Step B — Copy exposure JPEGs: {len(copied)} copied, {len(missing)} missing")
    if missing:
        print(f"  Missing UUIDs (no exposure file): {missing[:5]}{'...' if len(missing) > 5 else ''}")
    return copied


def render_tiers(uuids: List[str], dry_run: bool) -> None:
    """Render serving tiers for approved UUIDs using render_enhanced.py logic."""
    from PIL import Image, ImageFilter

    tier_configs = [
        # (name, long_edge, jpeg_q, webp_q, progressive, subsampling, sharpen)
        ("display", 2048, 88, 82, True, 1, None),
        ("mobile", 1280, 85, 80, True, 1, (0.4, 50, 2)),
        ("thumb", 480, 82, 78, False, 2, (0.3, 60, 2)),
        ("micro", 64, 70, 68, False, 2, None),
    ]

    total = len(uuids)
    rendered = 0

    for i, uuid in enumerate(uuids):
        source = ENHANCED_JPEG_DIR / f"{uuid}.jpg"
        if not source.exists():
            continue

        if dry_run:
            rendered += 1
            continue

        img = Image.open(source)
        img.load()
        img = img.convert("RGB")
        w, h = img.size

        for name, long_edge, jpeg_q, webp_q, progressive, subsampling, sharpen in tier_configs:
            cur_long = max(w, h)
            if cur_long > long_edge:
                ratio = long_edge / cur_long
                tier_img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            else:
                tier_img = img.copy()

            if sharpen:
                tier_img = tier_img.filter(ImageFilter.UnsharpMask(*sharpen))

            # Delete existing files for this UUID to force re-render
            for fmt_ext, fmt_name in [("jpg", "jpeg"), ("webp", "webp")]:
                out_dir = ENHANCED_DIR / name / fmt_name
                existing = out_dir / f"{uuid}.{fmt_ext}"
                if existing.exists():
                    existing.unlink()

            # JPEG (skip display — the source IS the display JPEG)
            if name != "display":
                jpeg_dir = ENHANCED_DIR / name / "jpeg"
                jpeg_dir.mkdir(parents=True, exist_ok=True)
                tier_img.save(
                    jpeg_dir / f"{uuid}.jpg",
                    format="JPEG", quality=jpeg_q, optimize=True,
                    progressive=progressive, subsampling=subsampling,
                )

            # WebP for all tiers
            webp_dir = ENHANCED_DIR / name / "webp"
            webp_dir.mkdir(parents=True, exist_ok=True)
            tier_img.save(
                webp_dir / f"{uuid}.webp",
                format="WEBP", quality=webp_q, method=4, exact=False,
            )

        rendered += 1
        if (i + 1) % 20 == 0 or (i + 1) == total:
            print(f"  Rendered {i + 1}/{total}...")

    print(f"Step C — Render tiers: {rendered} images processed")


def upload_to_gcs(uuids: List[str], dry_run: bool) -> None:
    """Upload tier files for approved UUIDs to GCS."""
    uploaded = 0
    errors = 0

    for uuid in uuids:
        for tier in TIERS:
            for fmt, ext in [("jpeg", "jpg"), ("webp", "webp")]:
                # Display tier has no separate JPEG (source is the JPEG)
                if tier == "display" and fmt == "jpeg":
                    local = ENHANCED_JPEG_DIR / f"{uuid}.jpg"
                else:
                    local = ENHANCED_DIR / tier / fmt / f"{uuid}.{ext}"

                if not local.exists():
                    continue

                gcs_path = f"{GCS_BASE}/{tier}/{fmt}/{uuid}.{ext}"

                if dry_run:
                    uploaded += 1
                    continue

                result = subprocess.run(
                    [
                        "gcloud", "storage", "cp", str(local), gcs_path,
                        "--cache-control=public, max-age=31536000, immutable",
                        "--quiet",
                    ],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0:
                    uploaded += 1
                else:
                    errors += 1
                    if errors <= 3:
                        print(f"  GCS error: {result.stderr.strip()}")

    print(f"Step D — GCS upload: {uploaded} files uploaded, {errors} errors")


def mark_db(uuids: List[str], dry_run: bool) -> None:
    """Update enhancement_plans status to 'accepted' for approved UUIDs."""
    if dry_run:
        print(f"Step E — DB mark: would update {len(uuids)} rows (dry run)")
        return

    conn = db.get_connection()
    now = datetime.now(timezone.utc).isoformat()

    updated = 0
    for uuid in uuids:
        conn.execute(
            """UPDATE enhancement_plans
               SET status = 'accepted', reviewed_at = ?
               WHERE image_uuid = ?""",
            (now, uuid),
        )
        updated += conn.execute("SELECT changes()").fetchone()[0]

    conn.commit()
    conn.close()
    print(f"Step E — DB mark: {updated} rows updated to 'accepted'")


def print_summary(uuids: List[str]) -> None:
    """Print final summary with verification commands."""
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(uuids)} images deployed")
    print(f"{'='*60}")
    print(f"\nVerify GCS:")
    if uuids:
        sample = uuids[0]
        print(f"  gsutil ls {GCS_BASE}/display/webp/{sample}.webp")
    print(f"\nNext steps:")
    print(f"  1. python3 backend/export_gallery.py  # Regenerate photos.json with swapped URLs")
    print(f"  2. cd frontend/show && npx vite build  # Rebuild Show")
    print(f"  3. firebase deploy --only hosting:laeh-madphotos  # Deploy")


def main():
    parser = argparse.ArgumentParser(description="Deploy validated exposure enhancements")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--skip-gcs", action="store_true", help="Skip GCS upload step")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — no files will be modified\n")

    # Step A: Read votes
    approved = load_approved_uuids()
    if not approved:
        print("No approved images. Nothing to do.")
        return

    # Step B: Copy exposure-enhanced JPEGs
    copied = copy_exposure_to_enhanced(approved, args.dry_run)
    if not copied:
        print("No exposure files found for approved UUIDs. Nothing to do.")
        return

    # Step C: Render serving tiers
    render_tiers(copied, args.dry_run)

    # Step D: Upload to GCS
    if args.skip_gcs:
        print("Step D — GCS upload: SKIPPED (--skip-gcs)")
    else:
        upload_to_gcs(copied, args.dry_run)

    # Step E: Mark in DB
    mark_db(copied, args.dry_run)

    # Step F: Summary
    print_summary(copied)


if __name__ == "__main__":
    main()
