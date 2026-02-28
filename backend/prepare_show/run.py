#!/usr/bin/env python3
"""
run.py — Pre-compute everything the Show frontend needs.

5-phase pipeline: audit → score → index → curate → summary.

Usage:
    python3 -m backend.prepare_show.run              # full pipeline
    python3 -m backend.prepare_show.run --audit      # phase 1 only
    python3 -m backend.prepare_show.run --score      # phase 2 only
    python3 -m backend.prepare_show.run --index      # phase 3 only
    python3 -m backend.prepare_show.run --curate     # phase 4 only
    python3 -m backend.prepare_show.run --dry        # preview without writing
    python3 -m backend.prepare_show.run --force      # regenerate even if fresh
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

from . import PHOTOS_JSON, FINGERPRINT_PATH, ALL_OUTPUTS


def banner(phase: int, total: int, title: str, dry: bool = False) -> None:
    tag = " (DRY)" if dry else ""
    print(f"\n{'=' * 60}")
    print(f"[{phase}/{total}] {title}{tag}")
    print("=" * 60)


def elapsed(start: float) -> str:
    s = time.time() - start
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m{int(s % 60)}s"


def compute_fingerprint() -> str:
    """Hash of photos.json mtime + size."""
    if not PHOTOS_JSON.exists():
        return ""
    stat = PHOTOS_JSON.stat()
    raw = f"{stat.st_mtime:.6f}:{stat.st_size}"
    return hashlib.md5(raw.encode()).hexdigest()


def is_fresh() -> bool:
    """Check if outputs are up to date with photos.json."""
    if not FINGERPRINT_PATH.exists():
        return False
    try:
        saved = json.loads(FINGERPRINT_PATH.read_text())
        if saved.get("fingerprint") != compute_fingerprint():
            return False
        # Check all output files exist
        for path in ALL_OUTPUTS:
            if not path.exists():
                return False
        return True
    except Exception:
        return False


def save_fingerprint() -> None:
    FINGERPRINT_PATH.write_text(json.dumps({
        "fingerprint": compute_fingerprint(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def load_photos() -> list[dict]:
    """Load photos.json and return the photos array."""
    if not PHOTOS_JSON.exists():
        print(f"  ERROR: {PHOTOS_JSON} not found. Run export_gallery first.")
        sys.exit(1)
    data = json.loads(PHOTOS_JSON.read_text())
    return data.get("photos", data) if isinstance(data, dict) else data


def filter_picks(photos: list[dict]) -> list[dict]:
    """Filter to picks: has thumb + display, not a variant."""
    return [p for p in photos if p.get("thumb") and p.get("display") and not p.get("parent")]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MADphotos prepare_show — pre-compute Show data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--audit", action="store_true", help="Phase 1: data freshness report only")
    parser.add_argument("--score", action="store_true", help="Phase 2: compute scores only")
    parser.add_argument("--index", action="store_true", help="Phase 3: build indices only")
    parser.add_argument("--curate", action="store_true", help="Phase 4: build experiences only")
    parser.add_argument("--dry", action="store_true", help="Preview without writing files")
    parser.add_argument("--force", action="store_true", help="Regenerate even if fresh")
    args = parser.parse_args()

    single_phase = any([args.audit, args.score, args.index, args.curate])

    start = time.time()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"MADphotos prepare_show — {now}")
    if args.dry:
        print("DRY RUN — nothing will be written")

    # Freshness check
    if not args.force and not single_phase and is_fresh():
        print(f"\n  All outputs are fresh (photos.json unchanged). Use --force to regenerate.")
        print(f"Done. ({elapsed(start)})")
        return

    # Load data
    print(f"\n  Loading photos.json...")
    all_photos = load_photos()
    picks = filter_picks(all_photos)
    print(f"  {len(all_photos)} total photos, {len(picks)} picks")

    from . import audit, score, index, curate

    # Single-phase runs
    if args.audit:
        banner(1, 5, "AUDIT", args.dry)
        audit.run(all_photos, picks)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.score:
        banner(2, 5, "SCORES", args.dry)
        score.run(picks, args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.index:
        banner(3, 5, "INDICES", args.dry)
        index.run(picks, all_photos, args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.curate:
        banner(4, 5, "CURATE", args.dry)
        curate.run(picks, all_photos, args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    # Full pipeline
    banner(1, 5, "AUDIT", args.dry)
    audit.run(all_photos, picks)

    banner(2, 5, "SCORES", args.dry)
    score.run(picks, args.dry)

    banner(3, 5, "INDICES", args.dry)
    index.run(picks, all_photos, args.dry)

    banner(4, 5, "CURATE", args.dry)
    curate.run(picks, all_photos, args.dry)

    banner(5, 5, "SUMMARY", args.dry)
    _print_summary(args.dry)

    if not args.dry:
        save_fingerprint()

    print(f"\nDone. ({elapsed(start)})")


def _print_summary(dry: bool) -> None:
    """Print file sizes and coverage."""
    for path in ALL_OUTPUTS:
        if path.exists():
            size = path.stat().st_size
            if size < 1024:
                label = f"{size} B"
            else:
                label = f"{size / 1024:.1f} KB"
            # Count top-level entries
            try:
                data = json.loads(path.read_text())
                if isinstance(data, dict):
                    counts = {k: len(v) if isinstance(v, (list, dict)) else 1 for k, v in data.items()}
                    detail = ", ".join(f"{k}: {c}" for k, c in counts.items())
                elif isinstance(data, list):
                    detail = f"{len(data)} entries"
                else:
                    detail = ""
                print(f"  {path.name}: {label} — {detail}")
            except Exception:
                print(f"  {path.name}: {label}")
        else:
            status = "(would be created)" if dry else "(MISSING)"
            print(f"  {path.name}: {status}")


def main_pipeline(dry: bool = False, force: bool = False) -> None:
    """Called from update_and_deploy — run full pipeline without argparse."""
    if not force and is_fresh():
        print("  All outputs are fresh (photos.json unchanged). Skipping.")
        return

    print(f"  Loading photos.json...")
    all_photos = load_photos()
    picks = filter_picks(all_photos)
    print(f"  {len(all_photos)} total photos, {len(picks)} picks")

    from . import audit, score, index, curate

    audit.run(all_photos, picks)
    score.run(picks, dry)
    index.run(picks, all_photos, dry)
    curate.run(picks, all_photos, dry)

    if not dry:
        save_fingerprint()


if __name__ == "__main__":
    main()
