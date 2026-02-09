#!/usr/bin/env python3
"""
pipeline_lock.py — Shared file-based PID lock for pipeline scripts.

Prevents concurrent pipeline runs that could corrupt the database.
Stale locks (from dead processes) are auto-cleaned.
"""
from __future__ import annotations

import json
import os
import signal
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = PROJECT_ROOT / ".pipeline.lock"


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def acquire_lock(script_name: str) -> None:
    """Acquire the pipeline lock. Raises RuntimeError if another process holds it."""
    if LOCK_PATH.exists():
        try:
            info = json.loads(LOCK_PATH.read_text())
            pid = info.get("pid", 0)
            if _pid_alive(pid):
                raise RuntimeError(
                    f"Pipeline lock held by {info.get('script', '?')} "
                    f"(PID {pid}, started {info.get('started', '?')}). "
                    f"If this is stale, delete {LOCK_PATH}"
                )
            # PID is dead — stale lock, clean it up
            LOCK_PATH.unlink()
        except (json.JSONDecodeError, KeyError):
            # Corrupt lock file — remove it
            LOCK_PATH.unlink(missing_ok=True)

    lock_info = {
        "pid": os.getpid(),
        "script": script_name,
        "started": datetime.now().isoformat(timespec="seconds"),
    }
    LOCK_PATH.write_text(json.dumps(lock_info, indent=2))


def release_lock() -> None:
    """Release the pipeline lock if the current process owns it."""
    if not LOCK_PATH.exists():
        return
    try:
        info = json.loads(LOCK_PATH.read_text())
        if info.get("pid") == os.getpid():
            LOCK_PATH.unlink()
    except (json.JSONDecodeError, KeyError, OSError):
        pass


def lock_status() -> dict | None:
    """Return current lock info, or None if no lock is held."""
    if not LOCK_PATH.exists():
        return None
    try:
        info = json.loads(LOCK_PATH.read_text())
        info["alive"] = _pid_alive(info.get("pid", 0))
        return info
    except (json.JSONDecodeError, KeyError):
        return None
