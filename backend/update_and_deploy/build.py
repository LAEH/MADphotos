"""Phase 7: Build — gallery export + Vite builds (Show + System)."""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from . import BACKEND, DB_PATH, FINGERPRINT_PATH, SHOW_DIR, SYSTEM_DIR


# ── Gallery fingerprint ─────────────────────────────────────────────────────

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
    print(f"    Fingerprint saved: {fp}")


# ── Export ───────────────────────────────────────────────────────────────────

def export_gallery(dry: bool = False, force: bool = False) -> bool:
    """Run gallery export if data has changed. Returns True if export ran."""
    needs_update = gallery_needs_update()
    if force:
        print("  --full flag: forcing gallery regeneration")
    elif needs_update:
        print("  Fingerprint changed: regenerating gallery")
    else:
        print("  Fingerprint unchanged — skipping gallery export")
        return False

    if dry:
        print("  Would run: export_gallery.export()")
        return False

    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    from export_gallery import export
    export()
    save_gallery_fingerprint()
    return True


# ── Vite builds ──────────────────────────────────────────────────────────────

def build_show(dry: bool = False) -> bool:
    """Build Show app with Vite. Returns True on success."""
    if dry:
        print("  Would run: npm run build (Show)")
        return True

    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(SHOW_DIR),
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"  Show BUILD FAILED")
        # tsc errors go to stdout, vite errors to stderr
        output = (result.stdout + result.stderr).strip()
        if output:
            for line in output.split("\n")[:20]:
                print(f"    {line}")
        return False

    print("  Show built → frontend/show/dist/")
    return True


def build_system(dry: bool = False) -> bool:
    """Build System app and copy into Show dist. Returns True on success."""
    if dry:
        print("  Would run: npm run build (System)")
        return True

    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(SYSTEM_DIR),
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"  System BUILD FAILED")
        output = (result.stdout + result.stderr).strip()
        if output:
            for line in output.split("\n")[:20]:
                print(f"    {line}")
        return False

    # Copy System dist → frontend/show/dist/system/
    show_system = SHOW_DIR / "dist" / "system"
    if show_system.exists():
        shutil.rmtree(str(show_system))
    system_dist = SYSTEM_DIR / "dist"
    if system_dist.exists():
        shutil.copytree(str(system_dist), str(show_system))
        print("  System built → frontend/show/dist/system/")
    else:
        print("  WARNING: System dist/ not found after build")
        return False

    return True


def run(dry: bool = False, force: bool = False) -> dict:
    """Run the full build phase: export + Show + System."""
    # Export gallery
    exported = export_gallery(dry, force)

    # Build Show
    show_ok = build_show(dry)
    if not show_ok:
        return {"ok": False, "stage": "show_build", "exported": exported}

    # Build System into Show dist
    system_ok = build_system(dry)
    if not system_ok:
        return {"ok": False, "stage": "system_build", "exported": exported}

    return {"ok": True, "exported": exported}
