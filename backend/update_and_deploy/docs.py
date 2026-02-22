"""Phase 3: Documentation health — journal, CLAUDE.md, READMEs."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from . import PROJECT_ROOT, BACKEND


def check_journal() -> dict:
    """Check journal.md freshness and last entry date."""
    journal = PROJECT_ROOT / "docs" / "journal.md"
    if not journal.exists():
        return {"exists": False, "message": "journal.md not found"}

    text = journal.read_text()
    lines = text.strip().split("\n")

    # Find the most recent date header (## YYYY-MM-DD)
    last_date = None
    for line in lines:
        line = line.strip()
        if line.startswith("## 20") and len(line) >= 13:
            try:
                last_date = line[3:13]  # "2026-02-21"
            except (ValueError, IndexError):
                pass

    days_stale = None
    if last_date:
        try:
            entry_date = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_stale = (datetime.now(timezone.utc) - entry_date).days
        except ValueError:
            pass

    return {
        "exists": True,
        "lines": len(lines),
        "last_date": last_date,
        "days_stale": days_stale,
    }


def check_claude_md() -> list[dict]:
    """Check CLAUDE.md files across the project."""
    results = []

    # Root CLAUDE.md
    root_claude = PROJECT_ROOT / "CLAUDE.md"
    if root_claude.exists():
        size = root_claude.stat().st_size
        results.append({"path": "CLAUDE.md", "exists": True, "size": size})
    else:
        results.append({"path": "CLAUDE.md", "exists": False})

    # Agent CLAUDE.md files
    agent_dirs = [
        BACKEND / "image_signals",
        BACKEND / "suggest_image_enhancement",
        BACKEND / "suggest_image_variant",
        BACKEND / "update_and_deploy",
    ]
    for d in agent_dirs:
        claude_file = d / "CLAUDE.md"
        name = d.name
        if claude_file.exists():
            size = claude_file.stat().st_size
            results.append({"path": f"backend/{name}/CLAUDE.md", "exists": True, "size": size})
        else:
            results.append({"path": f"backend/{name}/CLAUDE.md", "exists": False})

    return results


def check_readmes() -> list[dict]:
    """Check README files in agent directories."""
    results = []
    for d in [BACKEND / "image_signals", BACKEND / "api"]:
        readme = d / "README.md"
        if readme.exists():
            results.append({"path": str(readme.relative_to(PROJECT_ROOT)), "exists": True})
        else:
            results.append({"path": str(d.relative_to(PROJECT_ROOT)) + "/README.md", "exists": False})
    return results


def run(dry: bool = False) -> dict:
    """Run documentation health checks."""
    journal = check_journal()
    claude_files = check_claude_md()
    readmes = check_readmes()

    print("\n  JOURNAL")
    if journal["exists"]:
        print(f"    {journal['lines']} lines, last entry: {journal.get('last_date', '?')}")
        if journal.get("days_stale") is not None:
            if journal["days_stale"] == 0:
                print("    Fresh (today)")
            elif journal["days_stale"] <= 3:
                print(f"    {journal['days_stale']} days old (recent)")
            else:
                print(f"    {journal['days_stale']} days stale — consider updating before deploy")
    else:
        print("    MISSING — docs/journal.md not found")

    print("\n  CLAUDE.md FILES")
    for f in claude_files:
        if f["exists"]:
            print(f"    OK  {f['path']} ({f['size']:,} bytes)")
        else:
            print(f"    --  {f['path']} (missing)")

    print("\n  READMEs")
    for f in readmes:
        status = "OK" if f["exists"] else "--"
        print(f"    {status}  {f['path']}")

    return {"journal": journal, "claude_files": claude_files, "readmes": readmes}
