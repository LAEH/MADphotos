#!/usr/bin/env python3
"""
gcs_sync.py — Upload rendered assets to Google Cloud Storage and track in database.

Uses gsutil for efficient parallel transfers. Updates tiers table with GCS URLs.
Supports selective upload by phase, verification, and local cleanup after upload.

Usage:
    python gcs_sync.py --phase originals        # Upload original renders
    python gcs_sync.py --phase ai_variants      # Upload AI variant renders
    python gcs_sync.py --phase metadata          # Upload DB + reports
    python gcs_sync.py --verify                  # Verify all uploads exist
    python gcs_sync.py --cleanup originals       # Delete local files confirmed in GCS
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import mad_database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
RENDERED_DIR = BASE_DIR / "rendered"
AI_VARIANTS_DIR = BASE_DIR / "ai_variants"

GCS_BUCKET = "gs://myproject-public-assets/art/MADphotos"
PUBLIC_BASE = "https://storage.googleapis.com/myproject-public-assets/art/MADphotos"

# gsutil parallelism
GSUTIL_PARALLEL_THREADS = 10


# ---------------------------------------------------------------------------
# GCS operations
# ---------------------------------------------------------------------------

def gsutil_rsync(local_dir: str, gcs_dir: str, dry_run: bool = False) -> bool:
    """Run gsutil -m rsync -r with optional dry run. Returns True on success."""
    cmd = ["gsutil", "-m", "rsync", "-r"]
    if dry_run:
        cmd.append("-n")
    # Set cache-control for web serving
    cmd.extend([
        "-j", "jpg,webp",  # compress during transfer
        local_dir, gcs_dir,
    ])
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def gsutil_cp(local_path: str, gcs_path: str) -> bool:
    """Copy a single file to GCS."""
    cmd = ["gsutil", "cp", local_path, gcs_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def gsutil_ls(gcs_path: str) -> bool:
    """Check if a GCS path exists."""
    result = subprocess.run(["gsutil", "ls", gcs_path], capture_output=True, text=True)
    return result.returncode == 0


def set_cache_headers(gcs_dir: str) -> None:
    """Set Cache-Control headers for web serving."""
    cmd = [
        "gsutil", "-m", "setmeta",
        "-h", "Cache-Control:public, max-age=31536000, immutable",
        f"{gcs_dir}/**",
    ]
    print(f"  Setting cache headers on {gcs_dir}")
    subprocess.run(cmd, capture_output=True)


# ---------------------------------------------------------------------------
# Phase handlers
# ---------------------------------------------------------------------------

def sync_originals(conn, dry_run: bool = False) -> None:
    """Upload rendered/originals/ to GCS."""
    local_dir = str(RENDERED_DIR / "originals")
    gcs_dir = f"{GCS_BUCKET}/originals"

    if not Path(local_dir).exists():
        print("No rendered originals found. Run render_pipeline.py first.")
        return

    run_id = db.start_run(conn, "gcs_sync_originals")
    print(f"Syncing {local_dir} -> {gcs_dir}")

    success = gsutil_rsync(local_dir, gcs_dir, dry_run=dry_run)

    if success and not dry_run:
        # Update tier GCS URLs in database
        updated = _update_tier_urls(conn, "originals")
        set_cache_headers(gcs_dir)
        db.finish_run(conn, run_id, images_processed=updated)
        print(f"  Updated {updated} tier URLs in database")
    elif not success:
        db.finish_run(conn, run_id, status="failed", error_message="gsutil rsync failed")
        print("  Sync FAILED", file=sys.stderr)


def sync_ai_variants(conn, variant_type: Optional[str] = None, dry_run: bool = False) -> None:
    """Upload rendered AI variant tiers to GCS."""
    if variant_type:
        variant_types = [variant_type]
    else:
        # Upload all variant types that have rendered tiers
        rendered_variants = RENDERED_DIR / "ai_variants"
        if not rendered_variants.exists():
            print("No rendered AI variants found.")
            return
        variant_types = [d.name for d in rendered_variants.iterdir() if d.is_dir()]

    run_id = db.start_run(conn, "gcs_sync_ai_variants", {"variant_types": variant_types})
    total_updated = 0

    for vtype in variant_types:
        local_dir = str(RENDERED_DIR / "ai_variants" / vtype)
        gcs_dir = f"{GCS_BUCKET}/ai_variants/{vtype}"

        if not Path(local_dir).exists():
            print(f"  Skipping {vtype}: no rendered tiers found")
            continue

        print(f"Syncing {vtype}: {local_dir} -> {gcs_dir}")
        success = gsutil_rsync(local_dir, gcs_dir, dry_run=dry_run)

        if success and not dry_run:
            updated = _update_variant_tier_urls(conn, vtype)
            set_cache_headers(gcs_dir)
            total_updated += updated
            print(f"  Updated {updated} variant tier URLs")

    # Also upload the source variant images
    for vtype in variant_types:
        src_dir = str(AI_VARIANTS_DIR / vtype)
        gcs_src = f"{GCS_BUCKET}/ai_variants_source/{vtype}"
        if Path(src_dir).exists():
            print(f"Syncing variant sources: {vtype}")
            gsutil_rsync(src_dir, gcs_src, dry_run=dry_run)

    db.finish_run(conn, run_id, images_processed=total_updated)


def sync_metadata(conn, dry_run: bool = False) -> None:
    """Upload database and manifest to GCS."""
    gcs_meta = f"{GCS_BUCKET}/metadata"

    # Export DB as JSON
    json_export = BASE_DIR / "mad_photos_export.json"
    print("Exporting database to JSON...")
    db.export_json(conn, json_export)

    files_to_upload = [
        (str(db.DB_PATH), f"{gcs_meta}/mad_photos.db"),
        (str(json_export), f"{gcs_meta}/mad_photos_export.json"),
    ]
    if RENDERED_DIR.joinpath("manifest.json").exists():
        files_to_upload.append(
            (str(RENDERED_DIR / "manifest.json"), f"{gcs_meta}/manifest.json"))

    for local, gcs in files_to_upload:
        if dry_run:
            print(f"  DRY RUN: {local} -> {gcs}")
        else:
            print(f"  Uploading {Path(local).name} -> {gcs}")
            gsutil_cp(local, gcs)

    # Cleanup export
    if json_export.exists() and not dry_run:
        json_export.unlink()

    print("Metadata sync complete.")


def _update_tier_urls(conn, prefix: str) -> int:
    """Update GCS URLs for original tiers in the database."""
    rows = conn.execute(
        "SELECT id, image_uuid, tier_name, format, local_path FROM tiers WHERE variant_id IS NULL AND gcs_url IS NULL"
    ).fetchall()
    count = 0
    for row in rows:
        image_uuid = row["image_uuid"]
        # Get category/subcategory
        img_row = conn.execute(
            "SELECT category, subcategory FROM images WHERE uuid = ?",
            (image_uuid,)).fetchone()
        if not img_row:
            continue
        cat, sub = img_row["category"], img_row["subcategory"]
        tier = row["tier_name"]
        fmt = row["format"]
        ext = "jpg" if fmt == "jpeg" else "webp"

        gcs_path = f"{GCS_BUCKET}/{prefix}/{tier}/{fmt}/{cat}/{sub}/{image_uuid}.{ext}"
        public_path = f"{PUBLIC_BASE}/{prefix}/{tier}/{fmt}/{cat}/{sub}/{image_uuid}.{ext}"

        db.update_tier_gcs(conn, image_uuid, tier, fmt, gcs_path, public_path)
        db.record_upload(conn, row["local_path"] or "", gcs_path)
        count += 1

    conn.commit()
    return count


def _update_variant_tier_urls(conn, variant_type: str) -> int:
    """Update GCS URLs for variant tiers."""
    rows = conn.execute("""
        SELECT t.id, t.image_uuid, t.variant_id, t.tier_name, t.format
        FROM tiers t
        JOIN ai_variants v ON t.variant_id = v.variant_id
        WHERE v.variant_type = ? AND t.gcs_url IS NULL
    """, (variant_type,)).fetchall()

    count = 0
    for row in rows:
        image_uuid = row["image_uuid"]
        variant_id = row["variant_id"]
        img_row = conn.execute(
            "SELECT category, subcategory FROM images WHERE uuid = ?",
            (image_uuid,)).fetchone()
        if not img_row:
            continue
        cat, sub = img_row["category"], img_row["subcategory"]
        tier = row["tier_name"]
        fmt = row["format"]
        ext = "jpg" if fmt == "jpeg" else "webp"

        gcs_path = f"{GCS_BUCKET}/ai_variants/{variant_type}/{tier}/{fmt}/{cat}/{sub}/{variant_id}.{ext}"
        public_path = f"{PUBLIC_BASE}/ai_variants/{variant_type}/{tier}/{fmt}/{cat}/{sub}/{variant_id}.{ext}"

        db.update_tier_gcs(conn, image_uuid, tier, fmt, gcs_path, public_path, variant_id=variant_id)
        count += 1

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Verify & Cleanup
# ---------------------------------------------------------------------------

def verify_uploads(conn) -> None:
    """Check that all recorded GCS URLs actually exist."""
    rows = conn.execute("SELECT gcs_url FROM tiers WHERE gcs_url IS NOT NULL").fetchall()
    print(f"Verifying {len(rows)} GCS URLs...")

    # Sample verification (checking all 50k+ would be slow)
    import random
    sample = random.sample([dict(r) for r in rows], min(100, len(rows)))
    ok = 0
    missing = 0
    for row in sample:
        if gsutil_ls(row["gcs_url"]):
            ok += 1
        else:
            missing += 1
            print(f"  MISSING: {row['gcs_url']}")

    print(f"Verification sample: {ok}/{len(sample)} OK, {missing} missing")
    if missing > 0:
        print("Re-run sync to fix missing files.")


def cleanup_local(conn, phase: str) -> None:
    """Delete local rendered files that are confirmed uploaded to GCS."""
    if phase == "originals":
        target = RENDERED_DIR / "originals"
    elif phase == "ai_variants":
        target = RENDERED_DIR / "ai_variants"
    else:
        print(f"Unknown phase: {phase}")
        return

    if not target.exists():
        print(f"Nothing to clean up at {target}")
        return

    # Check that uploads exist first
    total_tiers = conn.execute(
        "SELECT COUNT(*) as c FROM tiers WHERE gcs_url IS NOT NULL").fetchone()["c"]
    if total_tiers == 0:
        print("No uploads recorded. Run sync first.")
        return

    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    size_gb = size / (1024 ** 3)
    print(f"Will delete {target} ({size_gb:.1f} GB)")
    print("Confirm? [y/N] ", end="")
    if input().strip().lower() != "y":
        print("Aborted.")
        return

    shutil.rmtree(target)
    print(f"Deleted {target}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync rendered assets to GCS")
    parser.add_argument("--phase", choices=["originals", "ai_variants", "metadata"],
                        help="Which assets to sync")
    parser.add_argument("--variant-type", type=str, default=None,
                        help="Specific AI variant type to sync")
    parser.add_argument("--verify", action="store_true",
                        help="Verify uploads exist in GCS")
    parser.add_argument("--cleanup", type=str, metavar="PHASE",
                        help="Delete local files confirmed in GCS (originals or ai_variants)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be uploaded without actually uploading")
    args = parser.parse_args()

    conn = db.get_connection()

    if args.verify:
        verify_uploads(conn)
    elif args.cleanup:
        cleanup_local(conn, args.cleanup)
    elif args.phase == "originals":
        sync_originals(conn, dry_run=args.dry_run)
    elif args.phase == "ai_variants":
        sync_ai_variants(conn, variant_type=args.variant_type, dry_run=args.dry_run)
    elif args.phase == "metadata":
        sync_metadata(conn, dry_run=args.dry_run)
    else:
        # Sync everything
        print("=== Syncing all phases ===\n")
        sync_originals(conn, dry_run=args.dry_run)
        print()
        sync_ai_variants(conn, dry_run=args.dry_run)
        print()
        sync_metadata(conn, dry_run=args.dry_run)

    conn.close()


if __name__ == "__main__":
    main()
