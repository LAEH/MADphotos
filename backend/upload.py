#!/usr/bin/env python3
"""
gcs_sync.py — Upload rendered assets to Google Cloud Storage.

Uses gsutil for efficient parallel transfers. Mirrors the local flat layout
into a versioned GCS structure.

Local layout:
    rendered/{tier}/{format}/{uuid}.ext          → original photo tiers
    rendered/enhanced/{tier}/{format}/{uuid}.ext  → enhanced v1 tiers
    rendered/enhanced_v2/{tier}/{format}/{uuid}.ext → enhanced v2 tiers

GCS layout:
    v/original/{tier}/{format}/{uuid}.ext
    v/enhanced/{tier}/{format}/{uuid}.ext
    v/enhanced_v2/{tier}/{format}/{uuid}.ext
    v/{variant_type}/{tier}/{format}/{id}.ext
    meta/photos.json
    meta/mad_photos.db

Usage:
    python gcs_sync.py                           # Sync all versions
    python gcs_sync.py --version original        # Only original tiers
    python gcs_sync.py --version enhanced        # Only enhanced v1 tiers
    python gcs_sync.py --version enhanced_v2     # Only enhanced v2 tiers
    python gcs_sync.py --version metadata        # Upload DB + JSON export
    python gcs_sync.py --dry-run                 # Show what would be synced
    python gcs_sync.py --verify                  # Spot-check GCS uploads
    python gcs_sync.py --tiers display,thumb     # Only specific tiers
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

import database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = db.PROJECT_ROOT
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
AI_VARIANTS_DIR = PROJECT_ROOT / "images" / "ai_variants"

GCS_BUCKET = "gs://myproject-public-assets/art/MADphotos"
PUBLIC_BASE = "https://storage.googleapis.com/myproject-public-assets/art/MADphotos"

# Serving tiers to upload (skip full/gemini — those are for internal pipelines)
SERVING_TIERS = ["display", "mobile", "thumb", "micro"]
FORMATS = ["jpeg", "webp"]

# Versions and their local base directories (relative to RENDERED_DIR)
# Each version contains {tier}/{format}/{uuid}.ext
VERSION_MAP = {
    "original": RENDERED_DIR,                      # rendered/{tier}/{format}/
    "enhanced": RENDERED_DIR / "enhanced",          # rendered/enhanced/{tier}/{format}/
    "enhanced_v2": RENDERED_DIR / "enhanced_v2",    # rendered/enhanced_v2/{tier}/{format}/
}


# ---------------------------------------------------------------------------
# GCS operations
# ---------------------------------------------------------------------------

def gsutil_rsync(local_dir: str, gcs_dir: str, dry_run: bool = False) -> bool:
    """Run gsutil -m rsync -r. Returns True on success."""
    cmd = ["gsutil", "-m", "rsync", "-r"]
    if dry_run:
        cmd.append("-n")
    cmd.extend([local_dir, gcs_dir])
    print(f"    {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def gsutil_cp(local_path: str, gcs_path: str) -> bool:
    """Copy a single file to GCS."""
    cmd = ["gsutil", "cp", local_path, gcs_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ERROR: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def set_cache_headers(gcs_dir: str) -> None:
    """Set immutable Cache-Control headers for web serving."""
    cmd = [
        "gsutil", "-m", "setmeta",
        "-h", "Cache-Control:public, max-age=31536000, immutable",
        f"{gcs_dir}/**",
    ]
    subprocess.run(cmd, capture_output=True)


# ---------------------------------------------------------------------------
# Version sync
# ---------------------------------------------------------------------------

def sync_version(version: str, local_base: Path, dry_run: bool = False,
                 tiers: Optional[list] = None) -> int:
    """Sync one version's serving tiers to GCS. Returns count of synced dirs."""
    target_tiers = tiers or SERVING_TIERS
    synced = 0

    print(f"\n  [{version}] local: {local_base}")

    for tier in target_tiers:
        for fmt in FORMATS:
            local_dir = local_base / tier / fmt
            if not local_dir.exists():
                continue

            file_count = len(list(local_dir.iterdir()))
            if file_count == 0:
                continue

            gcs_dir = f"{GCS_BUCKET}/v/{version}/{tier}/{fmt}"
            print(f"  {tier}/{fmt} ({file_count} files) → v/{version}/{tier}/{fmt}")

            success = gsutil_rsync(str(local_dir), gcs_dir, dry_run=dry_run)
            if success and not dry_run:
                set_cache_headers(gcs_dir)
                synced += 1

    return synced


def sync_metadata(dry_run: bool = False) -> None:
    """Upload database and gallery data to GCS."""
    gcs_meta = f"{GCS_BUCKET}/meta"
    print(f"\n  [metadata] → {gcs_meta}")

    files_to_upload = []

    # Database
    if db.DB_PATH.exists():
        files_to_upload.append((str(db.DB_PATH), f"{gcs_meta}/mad_photos.db"))

    # Gallery JSON
    gallery_json = PROJECT_ROOT / "frontend" / "show" / "data" / "photos.json"
    if gallery_json.exists():
        files_to_upload.append((str(gallery_json), f"{gcs_meta}/photos.json"))

    # Manifest
    manifest = RENDERED_DIR / "manifest.json"
    if manifest.exists():
        files_to_upload.append((str(manifest), f"{gcs_meta}/manifest.json"))

    for local, gcs in files_to_upload:
        if dry_run:
            print(f"    DRY RUN: {Path(local).name} → {gcs}")
        else:
            print(f"    {Path(local).name} → {gcs}")
            gsutil_cp(local, gcs)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify(sample_size: int = 50) -> None:
    """Spot-check that GCS files exist for each version."""
    import random

    print("\nVerifying GCS uploads...")
    for version, local_base in VERSION_MAP.items():
        # Find a tier/format dir with files
        for tier in SERVING_TIERS:
            local_dir = local_base / tier / "jpeg"
            if local_dir.exists():
                files = list(local_dir.glob("*.jpg"))
                if not files:
                    continue
                sample = random.sample(files, min(sample_size, len(files)))
                ok = 0
                for f in sample:
                    gcs_url = f"{GCS_BUCKET}/v/{version}/{tier}/jpeg/{f.name}"
                    result = subprocess.run(
                        ["gsutil", "ls", gcs_url],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        ok += 1
                print(f"  {version}/{tier}/jpeg: {ok}/{len(sample)} OK")
                break


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync rendered assets to GCS")
    parser.add_argument("--version", type=str, default=None,
                        help="Which version to sync: original, enhanced, enhanced_v2, metadata, or all")
    parser.add_argument("--tiers", type=str, default=None,
                        help="Comma-separated tiers to sync (default: display,mobile,thumb,micro)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be uploaded")
    parser.add_argument("--verify", action="store_true",
                        help="Spot-check GCS uploads exist")
    args = parser.parse_args()

    if args.verify:
        verify()
        return

    tiers = args.tiers.split(",") if args.tiers else None

    if args.version and args.version != "all":
        if args.version == "metadata":
            sync_metadata(dry_run=args.dry_run)
        elif args.version in VERSION_MAP:
            sync_version(args.version, VERSION_MAP[args.version],
                         dry_run=args.dry_run, tiers=tiers)
        else:
            print(f"Unknown version: {args.version}")
            print(f"Available: {', '.join(VERSION_MAP.keys())}, metadata")
            sys.exit(1)
    else:
        # Sync all versions + metadata
        print("=== GCS Sync — All Versions ===")
        for version, local_base in VERSION_MAP.items():
            sync_version(version, local_base, dry_run=args.dry_run, tiers=tiers)
        sync_metadata(dry_run=args.dry_run)

    print("\nDone.")
    if not args.dry_run:
        print(f"Public URL root: {PUBLIC_BASE}/v/")


if __name__ == "__main__":
    main()
