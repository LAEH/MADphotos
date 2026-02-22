"""Phase 2: Inspect — git changes since last deploy."""
from __future__ import annotations

import subprocess
from . import PROJECT_ROOT


def get_last_deploy_commit() -> str | None:
    """Find the most recent deploy commit hash."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--grep=deploy:", "-1", "--format=%H"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_changes_since(commit: str | None) -> str:
    """Get diff stat since a commit (or last 10 commits if no deploy found)."""
    try:
        if commit:
            cmd = ["git", "diff", "--stat", commit, "HEAD"]
        else:
            cmd = ["git", "log", "--oneline", "-10"]
        result = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else "(git error)"
    except Exception as e:
        return f"(error: {e})"


def get_unstaged() -> str:
    """Get unstaged/untracked changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_current_branch() -> str:
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def run(dry: bool = False) -> dict:
    """Inspect git state. Returns structured report."""
    branch = get_current_branch()
    last_deploy = get_last_deploy_commit()
    changes = get_changes_since(last_deploy)
    unstaged = get_unstaged()

    print(f"\n  BRANCH: {branch}")

    if last_deploy:
        # Show the deploy commit message
        try:
            msg = subprocess.run(
                ["git", "log", "--oneline", "-1", last_deploy],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            print(f"  LAST DEPLOY: {msg}")
        except Exception:
            print(f"  LAST DEPLOY: {last_deploy[:8]}")
    else:
        print("  LAST DEPLOY: (no deploy commit found)")

    print(f"\n  CHANGES SINCE LAST DEPLOY:")
    if changes:
        for line in changes.split("\n")[:20]:
            print(f"    {line}")
        lines = changes.split("\n")
        if len(lines) > 20:
            print(f"    ... and {len(lines) - 20} more lines")
    else:
        print("    (no changes)")

    if unstaged:
        print(f"\n  UNSTAGED/UNTRACKED:")
        for line in unstaged.split("\n")[:15]:
            print(f"    {line}")
        lines = unstaged.split("\n")
        if len(lines) > 15:
            print(f"    ... and {len(lines) - 15} more")
    else:
        print("\n  Working tree clean")

    return {
        "branch": branch,
        "last_deploy_commit": last_deploy,
        "changes": changes,
        "unstaged": unstaged,
    }
