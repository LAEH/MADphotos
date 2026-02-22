"""Phase 2: Server launch — start core dev servers via Popen."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from . import CORE_SERVERS, LOG_DIR


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


# ── Server launch ─────────────────────────────────────────────────────────────

def start_server(server: dict, dry: bool = False) -> dict:
    """Start a single server via Popen. Returns {ok, pid, log_path} or {ok: False, error}."""
    name = server["name"]
    log_path = LOG_DIR / f"madphotos_ignition_{name}.log"

    if dry:
        print(f"  (dry) Would start {server['label']}")
        print(f"         cmd: {' '.join(server['cmd'])}")
        print(f"         cwd: {server['cwd']}")
        print(f"         log: {log_path}")
        return {"ok": True, "pid": None, "log_path": str(log_path)}

    try:
        log_file = open(log_path, "w")
        proc = subprocess.Popen(
            server["cmd"],
            cwd=server["cwd"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        # Wait briefly and poll for immediate crash
        time.sleep(0.5)
        ret = proc.poll()
        if ret is not None:
            log_file.close()
            fail(f"{server['label']} exited immediately (code {ret})")
            # Read first few lines of log for diagnostics
            try:
                with open(log_path) as f:
                    lines = f.readlines()[:5]
                for line in lines:
                    print(f"    {line.rstrip()}")
            except Exception:
                pass
            return {"ok": False, "error": f"exit code {ret}", "log_path": str(log_path)}

        ok(f"{server['label']} started (pid {proc.pid})")
        return {"ok": True, "pid": proc.pid, "log_path": str(log_path)}

    except Exception as e:
        fail(f"{server['label']} failed to start: {e}")
        return {"ok": False, "error": str(e)}


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run(dry: bool = False, ports_to_skip: set[int] | None = None) -> dict:
    """Start all core servers, skipping ports already in use."""
    skip = ports_to_skip or set()
    results = {}

    for server in CORE_SERVERS:
        port = server["port"]
        if port in skip:
            ok(f"Skipping {server['label']} — port {port} already in use")
            results[server["name"]] = {"ok": True, "skipped": True}
            continue
        result = start_server(server, dry)
        results[server["name"]] = result

    return results
