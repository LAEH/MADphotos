#!/usr/bin/env python3
"""
mad_pipeline.py — Top-level orchestrator for the MADphotos pipeline.

Runs all phases in sequence: render originals -> upload to GCS -> Gemini analysis
-> Imagen AI variants -> render variant tiers -> upload variants -> finalize.

Each phase is idempotent and resumable. Safe to Ctrl-C and re-run.

Usage:
    python mad_pipeline.py                          # Run all phases
    python mad_pipeline.py --phase render            # Only render originals
    python mad_pipeline.py --phase upload            # Only upload to GCS
    python mad_pipeline.py --phase gemini            # Only Gemini analysis
    python mad_pipeline.py --phase imagen            # Only AI variant generation
    python mad_pipeline.py --phase render-variants   # Only render variant tiers
    python mad_pipeline.py --phase upload-variants   # Only upload variants
    python mad_pipeline.py --phase finalize          # Export DB, sync metadata
    python mad_pipeline.py --test 10                 # Test with 10 images
    python mad_pipeline.py --status                  # Show pipeline status
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

import mad_database as db

BASE_DIR = Path(__file__).resolve().parent

PHASES = [
    "render",
    "upload",
    "gemini",
    "imagen",
    "render-variants",
    "upload-variants",
    "finalize",
]

VARIANT_TYPES = ["light_enhance", "nano_feel", "cartoon", "cinematic", "dreamscape"]

MIN_DISK_GB = 15  # Abort if less than this free


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_disk_space() -> float:
    """Return free disk space in GB."""
    usage = shutil.disk_usage(str(BASE_DIR))
    return usage.free / (1024 ** 3)


def run_script(script: str, args: list, description: str) -> bool:
    """Run a Python script as a subprocess. Returns True on success."""
    cmd = [sys.executable, str(BASE_DIR / script)] + args
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd)
    return result.returncode == 0


def check_gcloud_auth() -> bool:
    """Check if gcloud is authenticated."""
    result = subprocess.run(["gcloud", "auth", "print-access-token"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("gcloud not authenticated. Run:")
        print("  gcloud auth login")
        print("  gcloud auth application-default login")
        return False
    return True


def show_status(conn) -> None:
    """Display current pipeline status."""
    stats = db.get_stats(conn)
    print("\n=== MADphotos Pipeline Status ===\n")
    print(f"  Images registered:     {stats['images']}")
    print(f"  Tier files rendered:   {stats['tier_files']}")
    print(f"  AI variants generated: {stats['ai_variants_generated']}")
    print(f"  Gemini analyzed:       {stats['gemini_analyzed']}")
    print(f"  GCS uploaded:          {stats['gcs_uploaded']}")
    print(f"  Disk free:             {check_disk_space():.1f} GB")

    # Per-variant breakdown
    for vtype in VARIANT_TYPES:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM ai_variants WHERE variant_type=? AND generation_status='success'",
            (vtype,)).fetchone()
        total = conn.execute(
            "SELECT COUNT(*) as c FROM ai_variants WHERE variant_type=?",
            (vtype,)).fetchone()
        print(f"  Variant {vtype:15s}: {row['c']}/{total['c']} success")

    # Recent pipeline runs
    runs = conn.execute(
        "SELECT phase, status, images_processed, images_failed, started_at, completed_at "
        "FROM pipeline_runs ORDER BY run_id DESC LIMIT 10"
    ).fetchall()
    if runs:
        print("\n  Recent runs:")
        for r in runs:
            elapsed = ""
            if r["completed_at"] and r["started_at"]:
                elapsed = f" ({r['completed_at'][:19]})"
            print(f"    {r['phase']:25s} {r['status']:10s} "
                  f"ok={r['images_processed']} fail={r['images_failed']}{elapsed}")
    print()


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------

def phase_render(test: int, workers: int) -> bool:
    """Phase 1: Render originals into 6-tier pyramid."""
    free = check_disk_space()
    print(f"Disk free: {free:.1f} GB")
    if free < MIN_DISK_GB:
        print(f"Not enough disk space (need {MIN_DISK_GB}GB, have {free:.1f}GB)")
        return False

    args = ["--source", "originals"]
    if test:
        args.extend(["--test", str(test)])
    args.extend(["--workers", str(workers)])
    return run_script("render_pipeline.py", args, "Phase 1: Render Originals")


def phase_upload() -> bool:
    """Phase 2: Upload original renders to GCS."""
    if not check_gcloud_auth():
        return False
    return run_script("gcs_sync.py", ["--phase", "originals"],
                      "Phase 2: Upload Originals to GCS")


def phase_gemini(test: int, concurrent: int, max_retries: int) -> bool:
    """Phase 3: Gemini analysis."""
    args = ["--concurrent", str(concurrent), "--max-retries", str(max_retries)]
    if test:
        args.extend(["--test", str(test)])
    return run_script("photography_engine.py", args,
                      "Phase 3: Gemini Photography Analysis")


def phase_imagen(test: int, batch_size: int, concurrent: int) -> bool:
    """Phase 4: Generate AI variants with Imagen 3."""
    if not check_gcloud_auth():
        return False

    args = ["--batch-size", str(batch_size), "--concurrent", str(concurrent)]
    if test:
        args.extend(["--test", str(test)])
    return run_script("imagen_engine.py", args,
                      "Phase 4: Generate AI Variants (Imagen 3)")


def phase_render_variants(test: int, workers: int) -> bool:
    """Phase 5: Render tier pyramids for AI variant source images."""
    free = check_disk_space()
    if free < MIN_DISK_GB:
        print(f"Not enough disk space (need {MIN_DISK_GB}GB, have {free:.1f}GB)")
        return False

    all_ok = True
    for vtype in VARIANT_TYPES:
        variant_dir = BASE_DIR / "ai_variants" / vtype
        if not variant_dir.exists():
            print(f"  Skipping {vtype}: no source images")
            continue

        args = ["--source", "ai_variants", "--variant-type", vtype,
                "--tiers", "variant", "--workers", str(workers)]
        if test:
            args.extend(["--test", str(test)])

        ok = run_script("render_pipeline.py", args,
                        f"Phase 5: Render {vtype} variant tiers")
        if not ok:
            all_ok = False

    return all_ok


def phase_upload_variants() -> bool:
    """Phase 6: Upload AI variant renders to GCS."""
    if not check_gcloud_auth():
        return False
    return run_script("gcs_sync.py", ["--phase", "ai_variants"],
                      "Phase 6: Upload AI Variants to GCS")


def phase_finalize(conn) -> bool:
    """Phase 7: Export database, upload metadata, generate report."""
    # Export comprehensive JSON
    export_path = BASE_DIR / "mad_photos_export.json"
    print("Exporting database to JSON...")
    db.export_json(conn, export_path)
    print(f"  Exported to {export_path}")

    # Upload metadata
    ok = run_script("gcs_sync.py", ["--phase", "metadata"],
                    "Phase 7: Upload Metadata to GCS")

    # Print final stats
    show_status(conn)
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MADphotos Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Phases: {', '.join(PHASES)}")
    parser.add_argument("--phase", choices=PHASES,
                        help="Run a specific phase only")
    parser.add_argument("--test", type=int, metavar="N", default=0,
                        help="Limit to N images (for testing)")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2),
                        help="Parallel workers for rendering")
    parser.add_argument("--concurrent", type=int, default=5,
                        help="Concurrent API calls (Gemini/Imagen)")
    parser.add_argument("--max-retries", type=int, default=5,
                        help="Max retries for API calls")
    parser.add_argument("--batch-size", type=int, default=200,
                        help="Imagen batch size")
    parser.add_argument("--status", action="store_true",
                        help="Show pipeline status and exit")
    args = parser.parse_args()

    conn = db.get_connection()

    if args.status:
        show_status(conn)
        conn.close()
        return

    start = datetime.now()
    print(f"MADphotos Pipeline — {start.strftime('%Y-%m-%d %H:%M')}")
    print(f"Disk free: {check_disk_space():.1f} GB")

    phase = args.phase

    if phase is None or phase == "render":
        if not phase_render(args.test, args.workers):
            print("\nRender phase failed. Fix errors and re-run.")
            if phase:
                sys.exit(1)
        if phase:
            conn.close()
            return

    if phase is None or phase == "upload":
        if not phase_upload():
            print("\nUpload phase failed. Check gcloud auth and re-run.")
            if phase:
                sys.exit(1)
        if phase:
            conn.close()
            return

    if phase is None or phase == "gemini":
        if not phase_gemini(args.test, args.concurrent, args.max_retries):
            print("\nGemini phase had failures. Re-run to retry.")
            # Don't abort — continue to next phase
        if phase:
            conn.close()
            return

    if phase is None or phase == "imagen":
        if not phase_imagen(args.test, args.batch_size, args.concurrent):
            print("\nImagen phase had failures. Re-run to retry.")
        if phase:
            conn.close()
            return

    if phase is None or phase == "render-variants":
        if not phase_render_variants(args.test, args.workers):
            print("\nVariant rendering had failures.")
        if phase:
            conn.close()
            return

    if phase is None or phase == "upload-variants":
        if not phase_upload_variants():
            print("\nVariant upload failed. Check gcloud auth and re-run.")
        if phase:
            conn.close()
            return

    if phase is None or phase == "finalize":
        phase_finalize(conn)

    elapsed = datetime.now() - start
    print(f"\nPipeline complete in {elapsed}.")
    conn.close()


if __name__ == "__main__":
    main()
