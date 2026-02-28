#!/usr/bin/env python3
"""
run.py — Unified deploy pipeline orchestrator for MADphotos.

10-phase pipeline with per-phase flags for surgical runs.

Usage:
    python3 -m backend.update_and_deploy.run            # full pipeline
    python3 -m backend.update_and_deploy.run --preflight # safety check only
    python3 -m backend.update_and_deploy.run --inspect   # code changes only
    python3 -m backend.update_and_deploy.run --docs      # doc health only
    python3 -m backend.update_and_deploy.run --data      # regen System JSON only
    python3 -m backend.update_and_deploy.run --assets    # GCS check only
    python3 -m backend.update_and_deploy.run --build     # build only
    python3 -m backend.update_and_deploy.run --deploy    # Firebase only
    python3 -m backend.update_and_deploy.run --verify    # post-deploy checks only
    python3 -m backend.update_and_deploy.run --tags      # set Finder tags only
    python3 -m backend.update_and_deploy.run --dry       # dry run all phases
    python3 -m backend.update_and_deploy.run --wait      # poll until blocking processes clear
    python3 -m backend.update_and_deploy.run --force     # deploy despite blockers
    python3 -m backend.update_and_deploy.run --no-git    # skip git commit/push
    python3 -m backend.update_and_deploy.run --full      # force gallery re-export
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone


def banner(phase: int, total: int, title: str, dry: bool = False) -> None:
    tag = " (DRY)" if dry else ""
    print(f"\n{'=' * 60}")
    print(f"[{phase}/{total}] {title}{tag}")
    print("=" * 60)


def elapsed(start: float) -> str:
    s = time.time() - start
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m{int(s % 60)}s"


def wait_for_clear(timeout: int = 300) -> bool:
    """Poll until no blocking processes remain, or timeout."""
    from . import preflight
    print(f"Waiting up to {timeout}s for blocking processes to clear...")
    start = time.time()
    while time.time() - start < timeout:
        procs = preflight.get_processes()
        blocking, _ = preflight.classify_processes(procs)
        if not blocking:
            print("  Clear — no blocking processes")
            return True
        names = [p["cmd"].split("/")[-1][:40] for p in blocking]
        print(f"  Waiting... ({', '.join(names)})")
        time.sleep(10)
    print(f"  Timeout after {timeout}s — blocking processes still running")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MADphotos unified deploy pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Phase selectors
    parser.add_argument("--preflight", action="store_true", help="Phase 1: safety checks only")
    parser.add_argument("--inspect", action="store_true", help="Phase 2: git changes only")
    parser.add_argument("--docs", action="store_true", help="Phase 3: doc health only")
    parser.add_argument("--data", action="store_true", help="Phase 6: regen System JSON only")
    parser.add_argument("--assets", action="store_true", help="Phase 7: GCS check only")
    parser.add_argument("--build", action="store_true", help="Phase 7: build only")
    parser.add_argument("--deploy", action="store_true", help="Phase 8: Firebase deploy only")
    parser.add_argument("--verify", action="store_true", help="Phase 9: post-deploy checks only")
    parser.add_argument("--tags", action="store_true", help="Set Finder tags only")
    # Modifiers
    parser.add_argument("--dry", action="store_true", help="Dry run — print without executing")
    parser.add_argument("--wait", action="store_true", help="Wait for blocking processes to clear")
    parser.add_argument("--force", action="store_true", help="Deploy despite blockers")
    parser.add_argument("--no-git", action="store_true", help="Skip git commit/push")
    parser.add_argument("--full", action="store_true", help="Force gallery re-export")
    args = parser.parse_args()

    # Determine if a specific phase was requested
    single_phase = any([
        args.preflight, args.inspect, args.docs, args.data,
        args.assets, args.build, args.deploy, args.verify, args.tags,
    ])

    start = time.time()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"MADphotos Deploy Pipeline — {now}")
    if args.dry:
        print("DRY RUN — nothing will be modified")

    # Import phase modules
    from . import preflight, inspect, docs, deploy as deploy_mod
    from . import data, assets, build, postflight

    # ── Single-phase runs ────────────────────────────────────────────────────

    if args.tags:
        banner(10, 10, "FINDER TAGS", args.dry)
        postflight.set_finder_tags(args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.preflight:
        banner(1, 10, "PREFLIGHT", args.dry)
        preflight.run(args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.inspect:
        banner(2, 10, "INSPECT", args.dry)
        inspect.run(args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.docs:
        banner(3, 10, "DOCS", args.dry)
        docs.run(args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.data:
        banner(6, 10, "SYSTEM DATA", args.dry)
        data.run(args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.assets:
        banner(7, 10, "GCS ASSETS", args.dry)
        assets.run(args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.build:
        banner(7, 10, "BUILD", args.dry)
        result = build.run(args.dry, args.full)
        if not result["ok"] and not args.dry:
            print(f"\nBuild failed at {result.get('stage', '?')}. ({elapsed(start)})")
            sys.exit(1)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.deploy:
        banner(8, 10, "DEPLOY", args.dry)
        deploy_mod.deploy_firebase(args.dry)
        banner(9, 10, "VERIFY", args.dry)
        deploy_mod.verify_deploy(args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    if args.verify:
        banner(9, 10, "VERIFY", args.dry)
        deploy_mod.verify_deploy(args.dry)
        print(f"\nDone. ({elapsed(start)})")
        return

    # ── Full pipeline ────────────────────────────────────────────────────────

    # Phase 1: Preflight
    banner(1, 10, "PREFLIGHT", args.dry)
    try:
        report = preflight.run(args.dry)
        if not report["safe_to_deploy"] and not args.force and not args.dry:
            if args.wait:
                if not wait_for_clear():
                    print(f"\nAborted — blocking processes did not clear. ({elapsed(start)})")
                    sys.exit(1)
            else:
                print(f"\nAborted — not safe to deploy. Use --force to override or --wait to poll. ({elapsed(start)})")
                sys.exit(1)
    except Exception as e:
        print(f"  PREFLIGHT ERROR: {e}")
        if not args.force and not args.dry:
            sys.exit(1)

    # Phase 2: Inspect
    banner(2, 10, "INSPECT", args.dry)
    try:
        inspect.run(args.dry)
    except Exception as e:
        print(f"  INSPECT ERROR: {e}")

    # Phase 3: Docs
    banner(3, 10, "DOCS", args.dry)
    try:
        docs.run(args.dry)
    except Exception as e:
        print(f"  DOCS ERROR: {e}")

    # Phase 4: Firestore sync
    banner(4, 10, "FIRESTORE SYNC", args.dry)
    try:
        deploy_mod.sync_firestore(args.dry)
    except Exception as e:
        print(f"  SYNC ERROR: {e}")

    # Phase 5: Gallery export
    banner(5, 10, "GALLERY EXPORT", args.dry)
    try:
        build.export_gallery(args.dry, args.full)
    except Exception as e:
        print(f"  EXPORT ERROR: {e}")

    # Phase 5.5: Prepare Show data
    banner(5, 10, "PREPARE SHOW", args.dry)
    try:
        from backend.prepare_show import run as prepare_show
        prepare_show.main_pipeline(args.dry, args.force or args.full)
    except Exception as e:
        print(f"  PREPARE SHOW ERROR: {e}")

    # Phase 6: System data
    banner(6, 10, "SYSTEM DATA", args.dry)
    try:
        data.run(args.dry)
    except Exception as e:
        print(f"  DATA ERROR: {e}")

    # Phase 7: Build
    banner(7, 10, "BUILD", args.dry)
    try:
        show_ok = build.build_show(args.dry)
    except Exception as e:
        print(f"  SHOW BUILD ERROR: {e}")
        show_ok = False

    if not show_ok and not args.dry:
        print(f"\nPipeline aborted after Show build failure. ({elapsed(start)})")
        sys.exit(1)

    try:
        system_ok = build.build_system(args.dry)
    except Exception as e:
        print(f"  SYSTEM BUILD ERROR: {e}")
        system_ok = False

    if not system_ok and not args.dry:
        print(f"\nPipeline aborted after System build failure. ({elapsed(start)})")
        sys.exit(1)

    # Phase 8: Deploy
    banner(8, 10, "FIREBASE DEPLOY", args.dry)
    try:
        deploy_ok = deploy_mod.deploy_firebase(args.dry)
    except Exception as e:
        print(f"  DEPLOY ERROR: {e}")
        deploy_ok = False

    # Phase 9: Verify
    if deploy_ok or args.dry:
        banner(9, 10, "VERIFY", args.dry)
        try:
            deploy_mod.verify_deploy(args.dry)
        except Exception as e:
            print(f"  VERIFY ERROR: {e}")
    else:
        print(f"\n[9/10] VERIFY — skipped (deploy failed)")

    # Phase 10: Postflight
    banner(10, 10, "POSTFLIGHT", args.dry)
    try:
        postflight.run(args.dry, args.no_git)
    except Exception as e:
        print(f"  POSTFLIGHT ERROR: {e}")

    print(f"\nDone. ({elapsed(start)})")


if __name__ == "__main__":
    main()
