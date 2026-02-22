#!/usr/bin/env python3
"""
run.py — MADphotos Ignition agent orchestrator.

4-phase startup: prechecks → servers → health → companions.

Usage:
    python3 -m backend.MADphotos_ignition.run              # full startup (phases 1-3)
    python3 -m backend.MADphotos_ignition.run --prechecks   # checks only
    python3 -m backend.MADphotos_ignition.run --health      # health check running servers
    python3 -m backend.MADphotos_ignition.run --status      # prechecks + health (no startup)
    python3 -m backend.MADphotos_ignition.run --shutdown     # graceful kill all
    python3 -m backend.MADphotos_ignition.run --monitor      # full startup + terminal monitor
    python3 -m backend.MADphotos_ignition.run --see          # full startup + native See app
    python3 -m backend.MADphotos_ignition.run --dry          # print without executing
    python3 -m backend.MADphotos_ignition.run --force        # start even with port conflicts
    python3 -m backend.MADphotos_ignition.run --tags         # set Finder yellow labels
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone

from . import BACKEND, PROJECT_ROOT


# ── ANSI ──────────────────────────────────────────────────────────────────────

R = "\033[0m"
B = "\033[1m"
GN = "\033[32m"
CY = "\033[36m"
DM = "\033[38;5;245m"


def banner(phase: int, total: int, title: str, dry: bool = False) -> None:
    tag = " (DRY)" if dry else ""
    print(f"\n{'=' * 60}")
    print(f"  [{phase}/{total}] {title}{tag}")
    print("=" * 60)


def elapsed(start: float) -> str:
    s = time.time() - start
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m{int(s % 60)}s"


# ── Finder tags ───────────────────────────────────────────────────────────────

AGENT_FOLDERS = [
    BACKEND / "update_and_deploy",
    BACKEND / "suggest_image_variant",
    BACKEND / "suggest_image_enhancement",
    BACKEND / "image_signals",
    BACKEND / "MADphotos_ignition",
]


def set_finder_tags(dry: bool = False) -> None:
    """Set yellow Finder label (index 3) on all agent folders."""
    for folder in AGENT_FOLDERS:
        if not folder.exists():
            print(f"  {DM}skip{R} {folder.name} (not found)")
            continue
        if dry:
            print(f"  (dry) Would tag {folder.name}")
            continue
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'tell application "Finder" to set label index of '
                 f'(POSIX file "{folder}" as alias) to 3'],
                capture_output=True, text=True, timeout=10,
            )
            print(f"  {GN}✓{R} {folder.name}")
        except Exception as e:
            print(f"  {DM}skip{R} {folder.name} ({e})")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MADphotos Ignition — dev environment startup agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Mode selectors
    parser.add_argument("--prechecks", action="store_true", help="Phase 1 only: pre-checks")
    parser.add_argument("--health", action="store_true", help="Phase 3 only: health check")
    parser.add_argument("--status", action="store_true", help="Prechecks + health (no startup)")
    parser.add_argument("--shutdown", action="store_true", help="Kill all managed processes")
    parser.add_argument("--tags", action="store_true", help="Set Finder yellow labels only")
    # Companion flags
    parser.add_argument("--monitor", action="store_true", help="Also open terminal monitor")
    parser.add_argument("--see", action="store_true", help="Also launch native See app")
    # Modifiers
    parser.add_argument("--dry", action="store_true", help="Dry run — print without executing")
    parser.add_argument("--force", action="store_true", help="Start despite port conflicts")

    args = parser.parse_args()
    dry = args.dry

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{B}MADphotos Ignition{R} — {now}")
    if dry:
        print(f"{DM}DRY RUN — nothing will be modified{R}")

    start = time.time()

    # ── Tags only ─────────────────────────────────────────────────────────
    if args.tags:
        print(f"\n  {B}FINDER TAGS{R}")
        set_finder_tags(dry)
        print(f"\n{DM}Done in {elapsed(start)}{R}")
        return

    # ── Shutdown ──────────────────────────────────────────────────────────
    if args.shutdown:
        from . import shutdown
        banner(1, 1, "SHUTDOWN", dry)
        result = shutdown.run(dry)
        print(f"\n{DM}Done in {elapsed(start)}{R}")
        return

    # ── Determine phases to run ───────────────────────────────────────────
    single = args.prechecks or args.health or args.status
    run_prechecks = not single or args.prechecks or args.status
    run_servers = not single
    run_health = not single or args.health or args.status
    run_companions = not single and (args.monitor or args.see)

    total = sum([run_prechecks, run_servers, run_health, run_companions])
    phase = 0

    # ── Phase 1: Prechecks ────────────────────────────────────────────────
    ports_to_skip: set[int] = set()
    if run_prechecks:
        from . import prechecks
        phase += 1
        banner(phase, total, "PRECHECKS", dry)
        result = prechecks.run(dry, args.force)
        ports_to_skip = result["ports_to_skip"]

        if result["has_conflicts"] and not args.force:
            print(f"\n  Port conflicts detected. Use --force to start anyway, "
                  f"or --shutdown first.")
            if not (args.status or args.health):
                sys.exit(1)

    # ── Phase 2: Servers ──────────────────────────────────────────────────
    if run_servers:
        from . import servers
        phase += 1
        banner(phase, total, "SERVERS", dry)
        servers.run(dry, ports_to_skip)

    # ── Phase 3: Health ───────────────────────────────────────────────────
    if run_health:
        from . import health
        phase += 1
        banner(phase, total, "HEALTH", dry)
        health.run(dry)

    # ── Phase 4: Companions ───────────────────────────────────────────────
    if run_companions:
        from . import companions
        phase += 1
        banner(phase, total, "COMPANIONS", dry)
        if args.monitor:
            print(f"\n  {B}MONITOR{R}")
            companions.start_monitor(dry)
        if args.see:
            print(f"\n  {B}SEE APP{R}")
            companions.start_see(dry)
        print(f"\n  {B}OLLAMA{R}")
        companions.report_ollama(dry)

    print(f"\n{DM}Done in {elapsed(start)}{R}")


if __name__ == "__main__":
    main()
