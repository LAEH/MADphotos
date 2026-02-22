"""Shutdown — graceful SIGTERM → SIGKILL of all managed MADphotos processes."""
from __future__ import annotations

import os
import signal
import subprocess
import time

from . import PROCESS_SIGNATURES


# ── ANSI ──────────────────────────────────────────────────────────────────────

R = "\033[0m"
B = "\033[1m"
GN = "\033[32m"
YL = "\033[33m"
RD = "\033[31m"


def ok(msg: str) -> None:
    print(f"  {GN}✓{R} {msg}")


def warn(msg: str) -> None:
    print(f"  {YL}⚠{R} {msg}")


def fail(msg: str) -> None:
    print(f"  {RD}✗{R} {msg}")


# ── Process discovery ─────────────────────────────────────────────────────────

def find_managed_processes() -> list[dict]:
    """Find MADphotos-related processes via ps aux."""
    try:
        out = subprocess.check_output(["ps", "aux"], text=True, timeout=5)
    except Exception:
        return []

    my_pid = os.getpid()
    procs = []

    for line in out.strip().split("\n")[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        pid = int(parts[1])
        cmd = parts[10]

        # Skip self
        if pid == my_pid:
            continue
        # Skip grep/ps themselves
        if "grep" in cmd or "ps aux" in cmd:
            continue

        # Match against signatures
        if any(sig in cmd for sig in PROCESS_SIGNATURES):
            # Skip this ignition script itself
            if "MADphotos_ignition" in cmd:
                continue
            procs.append({
                "pid": pid,
                "cmd": cmd,
                "short": cmd.split("/")[-1][:50] if "/" in cmd else cmd[:50],
            })

    return procs


# ── Kill ──────────────────────────────────────────────────────────────────────

def kill_process(pid: int, name: str, dry: bool = False) -> bool:
    """SIGTERM a process, wait 3s, SIGKILL if still alive."""
    if dry:
        print(f"  (dry) Would kill pid {pid} — {name}")
        return True

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        ok(f"pid {pid} already gone — {name}")
        return True
    except PermissionError:
        fail(f"pid {pid} permission denied — {name}")
        return False

    # Wait for graceful exit
    for _ in range(6):
        time.sleep(0.5)
        try:
            os.kill(pid, 0)  # Check if alive
        except ProcessLookupError:
            ok(f"pid {pid} terminated — {name}")
            return True

    # Force kill
    try:
        os.kill(pid, signal.SIGKILL)
        ok(f"pid {pid} force killed — {name}")
        return True
    except ProcessLookupError:
        ok(f"pid {pid} terminated — {name}")
        return True
    except PermissionError:
        fail(f"pid {pid} force kill denied — {name}")
        return False


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run(dry: bool = False) -> dict:
    """Find and kill all managed MADphotos processes."""
    procs = find_managed_processes()

    if not procs:
        ok("No MADphotos processes running")
        return {"killed": 0, "processes": []}

    print(f"  Found {len(procs)} process{'es' if len(procs) != 1 else ''}:")
    for p in procs:
        print(f"    pid {p['pid']} — {p['short']}")

    print()
    killed = 0
    for p in procs:
        if kill_process(p["pid"], p["short"], dry):
            killed += 1

    return {"killed": killed, "total": len(procs), "processes": procs}
