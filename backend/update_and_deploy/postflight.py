"""Phase 10: Post-flight — Finder tags, dev servers, git commit."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from . import AGENT_FOLDERS, PROJECT_ROOT


# ── Finder tags ──────────────────────────────────────────────────────────────

def set_finder_tags(dry: bool = False) -> dict:
    """Set yellow Finder label (index 3) on all agent folders."""
    results = []
    for folder in AGENT_FOLDERS:
        if not folder.exists():
            results.append({"path": str(folder), "ok": False, "reason": "not found"})
            continue

        if dry:
            print(f"    Would tag: {folder.name}/")
            results.append({"path": str(folder), "ok": True, "dry": True})
            continue

        try:
            posix_path = str(folder)
            subprocess.run(
                ["osascript", "-e",
                 f'tell application "Finder" to set label index of '
                 f'(POSIX file "{posix_path}" as alias) to 3'],
                capture_output=True, text=True, timeout=10,
            )
            print(f"    Tagged: {folder.name}/")
            results.append({"path": str(folder), "ok": True})
        except Exception as e:
            print(f"    FAILED: {folder.name}/ — {e}")
            results.append({"path": str(folder), "ok": False, "reason": str(e)})

    return {"results": results}


# ── Dev server management ────────────────────────────────────────────────────

def detect_dev_servers() -> list[dict]:
    """Find running dev servers."""
    try:
        out = subprocess.check_output(["ps", "aux"], text=True, timeout=5)
    except Exception:
        return []
    servers = []
    for line in out.strip().split("\n")[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        cmd = parts[10]
        if "MADphotos" not in cmd:
            continue
        if "serve_show" in cmd or "vite" in cmd.lower() or "dashboard.py" in cmd:
            servers.append({"pid": parts[1], "cmd": cmd.split("/")[-1][:60]})
    return servers


# ── Git commit ───────────────────────────────────────────────────────────────

def git_commit_deploy(dry: bool = False, no_git: bool = False) -> dict:
    """Stage, commit, and push deploy changes."""
    if no_git:
        print("  Git: skipped (--no-git)")
        return {"skipped": True, "reason": "no-git"}

    # Check for changes
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    if not status.stdout.strip():
        print("  Git: no changes to commit")
        return {"skipped": True, "reason": "clean"}

    if dry:
        lines = len(status.stdout.strip().split("\n"))
        print(f"  Would commit {lines} changed files")
        return {"skipped": False, "dry": True}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = f"deploy: auto-update data {now}"

    subprocess.run(["git", "add", "-A"], cwd=str(PROJECT_ROOT), check=True)
    result = subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  Git commit failed: {result.stderr[:200]}")
        return {"committed": False, "error": result.stderr[:200]}

    push = subprocess.run(
        ["git", "push"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    if push.returncode == 0:
        print(f"  Committed and pushed: {msg}")
        return {"committed": True, "pushed": True, "message": msg}
    else:
        print(f"  Committed but push failed: {push.stderr[:200]}")
        return {"committed": True, "pushed": False, "message": msg}


def run(dry: bool = False, no_git: bool = False) -> dict:
    """Run post-flight: tags + git."""
    print("\n  FINDER TAGS")
    tags = set_finder_tags(dry)

    servers = detect_dev_servers()
    if servers:
        print(f"\n  DEV SERVERS RUNNING ({len(servers)}):")
        for s in servers:
            print(f"    pid={s['pid']}  {s['cmd']}")

    print("\n  GIT")
    git = git_commit_deploy(dry, no_git)

    return {"tags": tags, "servers": servers, "git": git}
