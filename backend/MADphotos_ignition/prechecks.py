"""Phase 1: Pre-checks — git state, port scan, node_modules, DB, Ollama."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

from . import CORE_SERVERS, DB_PATH, OLLAMA_URL, PROJECT_ROOT, SHOW_DIR, SYSTEM_DIR


# ── ANSI ──────────────────────────────────────────────────────────────────────

R = "\033[0m"
B = "\033[1m"
GN = "\033[32m"
YL = "\033[33m"
RD = "\033[31m"
DM = "\033[38;5;245m"


def ok(msg: str) -> None:
    print(f"  {GN}✓{R} {msg}")


def warn(msg: str) -> None:
    print(f"  {YL}⚠{R} {msg}")


def fail(msg: str) -> None:
    print(f"  {RD}✗{R} {msg}")


# ── Git ───────────────────────────────────────────────────────────────────────

def get_git_state(dry: bool = False) -> dict:
    """Return branch, short status, and recent log."""
    if dry:
        print("  (dry) Would check git state")
        return {"branch": "?", "status": [], "log": []}

    result = {}
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=PROJECT_ROOT, text=True, timeout=5,
        ).strip()
        result["branch"] = branch
        ok(f"Branch: {B}{branch}{R}")
    except Exception:
        result["branch"] = "unknown"
        warn("Could not determine git branch")

    try:
        status = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=PROJECT_ROOT, text=True, timeout=5,
        ).strip()
        lines = [l for l in status.split("\n") if l.strip()] if status else []
        result["status"] = lines
        if lines:
            warn(f"{len(lines)} uncommitted change{'s' if len(lines) != 1 else ''}")
        else:
            ok("Working tree clean")
    except Exception:
        result["status"] = []
        warn("Could not read git status")

    try:
        log = subprocess.check_output(
            ["git", "log", "--oneline", "-5"],
            cwd=PROJECT_ROOT, text=True, timeout=5,
        ).strip()
        result["log"] = log.split("\n") if log else []
        for entry in result["log"][:3]:
            print(f"    {DM}{entry}{R}")
    except Exception:
        result["log"] = []

    return result


# ── Ports ─────────────────────────────────────────────────────────────────────

def check_port(port: int) -> dict:
    """Check if a port is in use via lsof. Returns {in_use, process, pid, is_madphotos}."""
    try:
        out = subprocess.check_output(
            ["lsof", "-iTCP:" + str(port), "-sTCP:LISTEN", "-P", "-n"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
        for line in out.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 2:
                process = parts[0]
                pid = int(parts[1])
                cmd_line = ""
                try:
                    cmd_line = subprocess.check_output(
                        ["ps", "-p", str(pid), "-o", "command="],
                        text=True, timeout=5,
                    ).strip()
                except Exception:
                    pass
                is_mad = any(sig in cmd_line for sig in [
                    "MADphotos", "serve_show", "frontend/show", "frontend/system",
                ])
                return {"in_use": True, "process": process, "pid": pid,
                        "cmd": cmd_line, "is_madphotos": is_mad}
        return {"in_use": False}
    except subprocess.CalledProcessError:
        return {"in_use": False}
    except Exception:
        return {"in_use": False}


def scan_ports(dry: bool = False, force: bool = False) -> dict:
    """Scan all core server ports. Returns {ports_to_skip, conflicts, already_running}."""
    if dry:
        print("  (dry) Would scan ports 3000, 5173, 5174")
        return {"ports_to_skip": set(), "conflicts": [], "already_running": []}

    ports_to_skip: set[int] = set()
    conflicts: list[dict] = []
    already_running: list[dict] = []

    for server in CORE_SERVERS:
        port = server["port"]
        info = check_port(port)
        if not info["in_use"]:
            ok(f"Port {port} available — {server['label']}")
        elif info["is_madphotos"]:
            ports_to_skip.add(port)
            already_running.append({**info, "port": port, "server": server["name"]})
            ok(f"Port {port} already running — {server['label']} (pid {info['pid']})")
        else:
            if force:
                warn(f"Port {port} occupied by {info['process']} (pid {info['pid']}) — --force, skipping")
                ports_to_skip.add(port)
            else:
                fail(f"Port {port} occupied by {info['process']} (pid {info['pid']})")
                conflicts.append({**info, "port": port})

    return {
        "ports_to_skip": ports_to_skip,
        "conflicts": conflicts,
        "already_running": already_running,
    }


# ── Node modules ──────────────────────────────────────────────────────────────

def check_node_modules(dry: bool = False) -> dict:
    """Check node_modules exist for Show and System. Install if missing."""
    results = {}
    for name, dir_path in [("Show", SHOW_DIR), ("System", SYSTEM_DIR)]:
        nm = dir_path / "node_modules"
        if nm.exists():
            ok(f"{name} node_modules present")
            results[name] = "present"
        elif dry:
            print(f"  (dry) Would run npm install in {dir_path}")
            results[name] = "dry"
        else:
            warn(f"{name} node_modules missing — installing...")
            try:
                subprocess.run(
                    ["npm", "install"],
                    cwd=dir_path, timeout=120,
                    capture_output=True, text=True,
                )
                ok(f"{name} npm install complete")
                results[name] = "installed"
            except Exception as e:
                fail(f"{name} npm install failed: {e}")
                results[name] = "error"
    return results


# ── Database ──────────────────────────────────────────────────────────────────

def check_db(dry: bool = False) -> dict:
    """Verify the SQLite database exists and is readable."""
    if dry:
        print(f"  (dry) Would check {DB_PATH}")
        return {"ok": True}

    if not DB_PATH.exists():
        fail(f"Database not found: {DB_PATH}")
        return {"ok": False, "error": "not found"}

    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        count = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        conn.close()
        ok(f"Database OK — {count:,} images")
        return {"ok": True, "count": count}
    except Exception as e:
        fail(f"Database error: {e}")
        return {"ok": False, "error": str(e)}


# ── Ollama ────────────────────────────────────────────────────────────────────

def check_ollama(dry: bool = False) -> dict:
    """Check if Ollama is running and report loaded models."""
    if dry:
        print("  (dry) Would check Ollama at localhost:11434")
        return {"running": False}

    try:
        req = urllib.request.Request(OLLAMA_URL, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            models = data.get("models", [])
            if models:
                names = [m.get("name", "?") for m in models]
                ok(f"Ollama running — loaded: {', '.join(names)}")
            else:
                ok("Ollama running — no models loaded")
            return {"running": True, "models": models}
    except Exception:
        warn("Ollama not running")
        return {"running": False}


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run(dry: bool = False, force: bool = False) -> dict:
    """Run all pre-checks. Returns results dict with ports_to_skip for servers phase."""
    print(f"\n  {B}GIT{R}")
    git = get_git_state(dry)

    print(f"\n  {B}PORTS{R}")
    ports = scan_ports(dry, force)

    print(f"\n  {B}DEPENDENCIES{R}")
    deps = check_node_modules(dry)

    print(f"\n  {B}DATABASE{R}")
    db = check_db(dry)

    print(f"\n  {B}OLLAMA{R}")
    ollama = check_ollama(dry)

    return {
        "git": git,
        "ports": ports,
        "deps": deps,
        "db": db,
        "ollama": ollama,
        "ports_to_skip": ports["ports_to_skip"],
        "has_conflicts": len(ports["conflicts"]) > 0,
    }
