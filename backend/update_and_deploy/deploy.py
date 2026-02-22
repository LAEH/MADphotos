"""Phase 8: Deploy — Firestore sync + Firebase deploy + HTTP verify."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import urllib.request
from . import BACKEND, DB_PATH, FIREBASE_HOSTING, PROJECT_ROOT, LIVE_URLS


# ── Firestore sync ───────────────────────────────────────────────────────────

def sync_firestore(dry: bool = False) -> dict:
    """Pull latest votes from Firestore into local SQLite."""
    if dry:
        print("  Would sync Firestore collections")
        return {"new_rows": 0, "dry": True}

    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    from firestore_sync import (
        get_access_token, sync_collection, generate_picks_json,
        generate_voted_json, COLLECTIONS,
    )

    token = get_access_token()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")

    total_new = 0
    for col in COLLECTIONS:
        try:
            new = sync_collection(conn, col, token, dry=False)
            total_new += new
            if new:
                print(f"    {col['name']}: +{new} rows")
        except Exception as e:
            print(f"    {col['name']}: ERROR — {e}")

    print(f"    Sync total: {total_new} new rows")

    # Regenerate picks.json + voted.json
    try:
        generate_picks_json(conn)
    except Exception as e:
        print(f"    picks.json failed: {e}")

    try:
        generate_voted_json(conn)
    except Exception as e:
        print(f"    voted.json failed: {e}")

    conn.close()
    return {"new_rows": total_new}


# ── Firebase deploy ──────────────────────────────────────────────────────────

def deploy_firebase(dry: bool = False) -> bool:
    """Deploy to Firebase hosting. Returns True on success."""
    hosting_target = f"hosting:{FIREBASE_HOSTING}"
    if dry:
        print(f"  Would run: firebase deploy --only {hosting_target}")
        return True

    result = subprocess.run(
        ["firebase", "deploy", "--only", hosting_target],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, timeout=180,
    )

    if result.returncode != 0:
        print(f"  DEPLOY FAILED")
        output = (result.stdout + result.stderr).strip()
        if output:
            for line in output.split("\n")[:10]:
                print(f"    {line}")
        return False

    print("  Deployed to Firebase (Show + System)")
    return True


# ── Post-deploy verification ─────────────────────────────────────────────────

def verify_deploy(dry: bool = False) -> dict:
    """HTTP health checks on live URLs."""
    if dry:
        print(f"  Would check {len(LIVE_URLS)} live URLs")
        return {"checked": 0, "dry": True}

    results = []
    for url in LIVE_URLS:
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "MADphotos-deploy-check/1.0")
            resp = urllib.request.urlopen(req, timeout=15)
            status = resp.status
            ok = 200 <= status < 400
            results.append({"url": url, "status": status, "ok": ok})
            print(f"    {'OK' if ok else 'FAIL'}  {status}  {url}")
        except Exception as e:
            results.append({"url": url, "status": 0, "ok": False, "error": str(e)})
            print(f"    FAIL  ---  {url}  ({e})")

    all_ok = all(r["ok"] for r in results)
    if all_ok:
        print(f"  All {len(results)} URLs healthy")
    else:
        failed = sum(1 for r in results if not r["ok"])
        print(f"  {failed}/{len(results)} URLs failed health check")

    return {"results": results, "all_ok": all_ok}


def run(dry: bool = False) -> dict:
    """Run the full deploy phase: Firebase deploy + verification."""
    ok = deploy_firebase(dry)
    if not ok and not dry:
        return {"deployed": False, "verified": False}

    verify = verify_deploy(dry)
    return {"deployed": ok, "verified": verify.get("all_ok", False), "verify": verify}
