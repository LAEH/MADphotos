#!/usr/bin/env python3
"""
deploy.py — Unified deploy pipeline for MADphotos.

Single entry point that ensures all data is fresh before deploying.

Usage:
    python3 scripts/deploy.py              # Standard: sync + picks + state + build + deploy
    python3 scripts/deploy.py --full       # + regenerate gallery (photos.json, ~27 MB)
    python3 scripts/deploy.py --dry        # Show what would run
    python3 scripts/deploy.py --no-git     # Skip git commit/push (default for launchd)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND = PROJECT_ROOT / "backend"
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
STATE_DIR = PROJECT_ROOT / "frontend" / "state"
STATE_DATA_DIR = STATE_DIR / "public" / "data"
SHOW_DIR = PROJECT_ROOT / "frontend" / "show"
SHOW_DATA_DIR = SHOW_DIR / "data"
FINGERPRINT_PATH = PROJECT_ROOT / ".gallery_fingerprint.json"

sys.path.insert(0, str(BACKEND))


# ── Helpers ──────────────────────────────────────────────────────────────────

def banner(phase: int, title: str, dry: bool = False) -> None:
    tag = " (DRY)" if dry else ""
    print(f"\n{'=' * 60}")
    print(f"[{phase}/6] {title}{tag}")
    print("=" * 60)


def elapsed(start: float) -> str:
    s = time.time() - start
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m{int(s % 60)}s"


# ── Phase 1: Firestore Sync ─────────────────────────────────────────────────

def phase_sync(dry: bool) -> None:
    banner(1, "FIRESTORE SYNC", dry)

    from firestore_sync import (
        get_access_token, sync_collection, generate_picks_json,
        COLLECTIONS, DB_PATH as FS_DB_PATH,
    )

    token = get_access_token()
    conn = sqlite3.connect(str(FS_DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")

    total_new = 0
    for col in COLLECTIONS:
        new = sync_collection(conn, col, token, dry)
        total_new += new
        if new:
            print(f"  {col['name']}: +{new} rows")

    print(f"  Sync total: {total_new} new rows")

    if not dry:
        generate_picks_json(conn)

    conn.close()


# ── Phase 2: Gallery Data ───────────────────────────────────────────────────

def get_gallery_fingerprint() -> dict:
    """Query DB for counts that determine gallery staleness."""
    conn = sqlite3.connect(str(DB_PATH))
    fp = {}
    for key, sql in [
        ("image_count", "SELECT COUNT(*) FROM images"),
        ("gemini_count", "SELECT COUNT(*) FROM gemini_analysis WHERE raw_json IS NOT NULL AND raw_json != ''"),
        ("face_count", "SELECT COUNT(*) FROM faces"),
        ("vote_count", "SELECT COUNT(*) FROM firestore_tinder_votes"),
    ]:
        try:
            fp[key] = conn.execute(sql).fetchone()[0]
        except sqlite3.OperationalError:
            fp[key] = 0
    conn.close()
    return fp


def gallery_needs_update() -> bool:
    """Compare current DB fingerprint to saved one."""
    current = get_gallery_fingerprint()
    if not FINGERPRINT_PATH.exists():
        return True
    try:
        saved = json.loads(FINGERPRINT_PATH.read_text())
        return current != saved
    except (json.JSONDecodeError, KeyError):
        return True


def save_gallery_fingerprint() -> None:
    fp = get_gallery_fingerprint()
    FINGERPRINT_PATH.write_text(json.dumps(fp, indent=2) + "\n")
    print(f"  Fingerprint saved: {fp}")


def phase_gallery(dry: bool, force: bool) -> None:
    banner(2, "GALLERY DATA", dry)

    needs_update = gallery_needs_update()
    if force:
        print("  --full flag: forcing gallery regeneration")
    elif needs_update:
        print("  Fingerprint changed: regenerating gallery")
    else:
        print("  Fingerprint unchanged — skipping gallery export")
        return

    if dry:
        print("  Would run: export_gallery.export()")
        return

    from export_gallery import export
    export()
    save_gallery_fingerprint()


# ── Phase 3: State Data ─────────────────────────────────────────────────────

def phase_state_data(dry: bool) -> None:
    banner(3, "STATE DATA", dry)

    if dry:
        print("  Would regenerate 8 JSON files → frontend/state/public/data/")
        return

    from dashboard import (
        get_stats, get_journal_html, get_instructions_html,
        get_mosaics_data, get_cartoon_data,
        generate_signal_inspector_data,
        generate_embedding_audit_data,
        generate_collection_coverage_data,
    )

    STATE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    files = [
        ("stats.json", lambda: get_stats()),
        ("journal.json", lambda: {"html": get_journal_html()}),
        ("instructions.json", lambda: {"html": get_instructions_html()}),
        ("mosaics.json", lambda: {"mosaics": get_mosaics_data()}),
        ("cartoon.json", lambda: {"pairs": get_cartoon_data()}),
        ("signal_inspector.json", lambda: generate_signal_inspector_data()),
        ("embedding_audit.json", lambda: generate_embedding_audit_data()),
        ("collection_coverage.json", lambda: generate_collection_coverage_data()),
    ]

    for name, fn in files:
        try:
            data = fn()
            (STATE_DATA_DIR / name).write_text(json.dumps(data))
            size = (STATE_DATA_DIR / name).stat().st_size
            print(f"  {name:<30s} {size:>10,} bytes")
        except Exception as e:
            print(f"  {name}: FAILED — {e}")

    # Copy stats.json → frontend/show/data/ for Show app
    src = STATE_DATA_DIR / "stats.json"
    if src.exists() and SHOW_DATA_DIR.exists():
        shutil.copy2(str(src), str(SHOW_DATA_DIR / "stats.json"))
        print(f"  Copied stats.json → show/data/")


# ── Phase 4: Build State ────────────────────────────────────────────────────

def phase_build(dry: bool) -> bool:
    """Build State app. Returns True on success."""
    banner(4, "BUILD STATE", dry)

    if dry:
        print("  Would run: npm run build")
        return True

    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(STATE_DIR),
        capture_output=True, text=True, timeout=120,
    )

    if result.returncode != 0:
        print(f"  BUILD FAILED — aborting deploy")
        print(f"  stderr: {result.stderr[:500]}")
        return False

    # Copy dist → frontend/show/state/
    show_state = SHOW_DIR / "state"
    if show_state.exists():
        shutil.rmtree(str(show_state))
    shutil.copytree(str(STATE_DIR / "dist"), str(show_state))
    print(f"  Built → frontend/show/state/")
    return True


# ── Phase 5: Firebase Deploy ────────────────────────────────────────────────

def phase_deploy(dry: bool) -> bool:
    """Deploy to Firebase. Returns True on success."""
    banner(5, "FIREBASE DEPLOY", dry)

    if dry:
        print("  Would run: firebase deploy --only hosting:madphotos")
        return True

    result = subprocess.run(
        ["firebase", "deploy", "--only", "hosting:madphotos"],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, timeout=180,
    )

    if result.returncode != 0:
        print(f"  DEPLOY FAILED")
        print(f"  stderr: {result.stderr[:500]}")
        return False

    print(f"  Deployed to Firebase (Show + State)")
    return True


# ── Phase 6: Git ─────────────────────────────────────────────────────────────

def phase_git(dry: bool) -> None:
    banner(6, "GIT COMMIT + PUSH", dry)

    if dry:
        print("  Would run: git add + commit + push")
        return

    # Check for changes
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    if not status.stdout.strip():
        print("  No changes to commit")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = f"deploy: auto-update data {now}"

    subprocess.run(["git", "add", "-A"], cwd=str(PROJECT_ROOT), check=True)
    subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True,
    )
    result = subprocess.run(
        ["git", "push"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  Committed and pushed: {msg}")
    else:
        print(f"  Committed but push failed: {result.stderr[:200]}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="MADphotos unified deploy pipeline")
    parser.add_argument("--full", action="store_true",
                        help="Force gallery regeneration (photos.json)")
    parser.add_argument("--dry", action="store_true",
                        help="Show what would run without executing")
    parser.add_argument("--no-git", action="store_true",
                        help="Skip git commit/push")
    args = parser.parse_args()

    start = time.time()
    print(f"MADphotos Deploy Pipeline — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if args.dry:
        print("DRY RUN — nothing will be modified")

    # Phase 1: Firestore sync
    try:
        phase_sync(args.dry)
    except Exception as e:
        print(f"  SYNC ERROR: {e}")

    # Phase 2: Gallery data
    try:
        phase_gallery(args.dry, args.full)
    except Exception as e:
        print(f"  GALLERY ERROR: {e}")

    # Phase 3: State data
    try:
        phase_state_data(args.dry)
    except Exception as e:
        print(f"  STATE DATA ERROR: {e}")

    # Phase 4: Build (failure stops pipeline)
    try:
        build_ok = phase_build(args.dry)
    except Exception as e:
        print(f"  BUILD ERROR: {e}")
        build_ok = False

    if not build_ok:
        print(f"\nPipeline aborted after build failure. ({elapsed(start)})")
        sys.exit(1)

    # Phase 5: Deploy (failure skips git)
    try:
        deploy_ok = phase_deploy(args.dry)
    except Exception as e:
        print(f"  DEPLOY ERROR: {e}")
        deploy_ok = False

    # Phase 6: Git (skip if deploy failed or --no-git)
    if args.no_git:
        print(f"\n[6/6] GIT — skipped (--no-git)")
    elif not deploy_ok:
        print(f"\n[6/6] GIT — skipped (deploy failed)")
    else:
        try:
            phase_git(args.dry)
        except Exception as e:
            print(f"  GIT ERROR: {e}")

    print(f"\nDone. ({elapsed(start)})")


if __name__ == "__main__":
    main()
