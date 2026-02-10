#!/usr/bin/env python3
"""
firestore_sync.py — Pull Firestore vote collections into the local SQLite database.

Runs via launchd every 6 hours. Idempotent — uses Firestore document IDs
as primary keys so re-runs never duplicate data.

Collections synced:
  - tinder-votes    → firestore_tinder_votes (photo, vote, device, ts)
  - couple-likes    → firestore_couple_likes (a, b, strategy, ts)
  - couple-approves → firestore_couple_approves (photo, ts)
  - couple-rejects  → firestore_couple_rejects (photo, ts)

Usage:
  python3 backend/firestore_sync.py          # sync all collections
  python3 backend/firestore_sync.py --dry    # show counts without writing
"""
from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
LOG_PATH = PROJECT_ROOT / "backend" / "firestore_sync.log"

FIREBASE_PROJECT = "laeh380to760"
BASE_URL = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/databases/(default)/documents"
PAGE_SIZE = 300

COLLECTIONS = [
    {
        "name": "tinder-votes",
        "table": "firestore_tinder_votes",
        "schema": """
            CREATE TABLE IF NOT EXISTS firestore_tinder_votes (
                doc_id    TEXT PRIMARY KEY,
                photo     TEXT NOT NULL,
                vote      TEXT NOT NULL,
                device    TEXT,
                ts        TEXT,
                synced_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ftv_photo ON firestore_tinder_votes(photo);
            CREATE INDEX IF NOT EXISTS idx_ftv_vote ON firestore_tinder_votes(vote);
            CREATE INDEX IF NOT EXISTS idx_ftv_ts ON firestore_tinder_votes(ts);
        """,
        "fields": ["photo", "vote", "device", "ts"],
    },
    {
        "name": "couple-likes",
        "table": "firestore_couple_likes",
        "schema": """
            CREATE TABLE IF NOT EXISTS firestore_couple_likes (
                doc_id    TEXT PRIMARY KEY,
                a         TEXT NOT NULL,
                b         TEXT NOT NULL,
                strategy  TEXT,
                ts        TEXT,
                synced_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fcl_strategy ON firestore_couple_likes(strategy);
            CREATE INDEX IF NOT EXISTS idx_fcl_ts ON firestore_couple_likes(ts);
        """,
        "fields": ["a", "b", "strategy", "ts"],
    },
    {
        "name": "couple-approves",
        "table": "firestore_couple_approves",
        "schema": """
            CREATE TABLE IF NOT EXISTS firestore_couple_approves (
                doc_id    TEXT PRIMARY KEY,
                photo     TEXT NOT NULL,
                ts        TEXT,
                synced_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fca_photo ON firestore_couple_approves(photo);
        """,
        "fields": ["photo", "ts"],
    },
    {
        "name": "couple-rejects",
        "table": "firestore_couple_rejects",
        "schema": """
            CREATE TABLE IF NOT EXISTS firestore_couple_rejects (
                doc_id    TEXT PRIMARY KEY,
                photo     TEXT NOT NULL,
                ts        TEXT,
                synced_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fcr_photo ON firestore_couple_rejects(photo);
        """,
        "fields": ["photo", "ts"],
    },
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("firestore_sync")


def get_access_token() -> str:
    """Get a fresh gcloud access token."""
    result = subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gcloud auth failed: {result.stderr.strip()}")
    return result.stdout.strip()


def extract_value(field: dict) -> str | None:
    """Extract a scalar value from a Firestore field dict."""
    if "stringValue" in field:
        return field["stringValue"]
    if "timestampValue" in field:
        return field["timestampValue"]
    if "integerValue" in field:
        return str(field["integerValue"])
    if "doubleValue" in field:
        return str(field["doubleValue"])
    if "booleanValue" in field:
        return str(field["booleanValue"])
    if "nullValue" in field:
        return None
    return None


def fetch_collection(collection: str, token: str) -> list[dict]:
    """Fetch all documents from a Firestore collection with pagination."""
    docs = []
    page_token = None

    while True:
        url = f"{BASE_URL}/{collection}?pageSize={PAGE_SIZE}"
        if page_token:
            url += f"&pageToken={page_token}"

        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        batch = data.get("documents", [])
        docs.extend(batch)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return docs


def parse_doc(doc: dict, fields: list[str]) -> dict:
    """Parse a Firestore document into a flat dict."""
    doc_id = doc["name"].rsplit("/", 1)[-1]
    row = {"doc_id": doc_id}
    fs_fields = doc.get("fields", {})
    for f in fields:
        row[f] = extract_value(fs_fields[f]) if f in fs_fields else None
    return row


def sync_collection(conn: sqlite3.Connection, col: dict, token: str, dry: bool) -> int:
    """Sync one Firestore collection into the SQLite table. Returns new row count."""
    name = col["name"]
    table = col["table"]
    fields = col["fields"]

    # Ensure table exists
    conn.executescript(col["schema"])

    # Fetch from Firestore
    docs = fetch_collection(name, token)
    log.info(f"  {name}: {len(docs)} documents in Firestore")

    if dry or not docs:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    columns = ["doc_id"] + fields + ["synced_at"]
    placeholders = ",".join(["?"] * len(columns))
    sql = f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"

    new = 0
    for doc in docs:
        row = parse_doc(doc, fields)
        values = [row["doc_id"]] + [row.get(f) for f in fields] + [now]
        cursor = conn.execute(sql, values)
        new += cursor.rowcount

    conn.commit()
    return new


def print_summary(conn: sqlite3.Connection):
    """Print current table counts."""
    for col in COLLECTIONS:
        table = col["table"]
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            log.info(f"  {table}: {count} rows")
        except sqlite3.OperationalError:
            log.info(f"  {table}: (not yet created)")


def main():
    dry = "--dry" in sys.argv

    log.info("=" * 50)
    log.info(f"Firestore sync {'(DRY RUN)' if dry else 'started'}")

    token = get_access_token()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")

    total_new = 0
    for col in COLLECTIONS:
        try:
            new = sync_collection(conn, col, token, dry)
            total_new += new
            if new:
                log.info(f"  → {new} new rows inserted")
        except Exception as e:
            log.error(f"  {col['name']}: ERROR — {e}")

    log.info(f"Sync complete. {total_new} new rows total.")
    print_summary(conn)
    conn.close()

    # Regenerate data + rebuild + deploy so dashboards reflect fresh data
    if total_new > 0 and not dry:
        try:
            log.info("Regenerating static data...")
            subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_static.py")],
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True, timeout=120,
            )
            log.info("Static data updated.")
        except Exception as e:
            log.warning(f"Static data regeneration failed: {e}")

        # Rebuild and deploy State app to GitHub Pages
        state_dir = PROJECT_ROOT / "frontend" / "state"
        try:
            log.info("Building State app...")
            subprocess.run(
                ["npm", "run", "build"],
                cwd=str(state_dir),
                capture_output=True, text=True, timeout=120,
            )
            log.info("Deploying State to GitHub Pages...")
            subprocess.run(
                ["npx", "gh-pages", "-d", "dist"],
                cwd=str(state_dir),
                capture_output=True, text=True, timeout=120,
            )
            log.info("State deployed.")
        except Exception as e:
            log.warning(f"State build/deploy failed: {e}")

        # Deploy Show to Firebase (stats.json in show/data/)
        show_data = PROJECT_ROOT / "frontend" / "show" / "data"
        state_data = state_dir / "public" / "data" / "stats.json"
        if state_data.exists() and show_data.exists():
            import shutil
            shutil.copy2(str(state_data), str(show_data / "stats.json"))
        try:
            log.info("Deploying Show to Firebase...")
            subprocess.run(
                ["firebase", "deploy", "--only", "hosting:madphotos"],
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True, timeout=120,
            )
            log.info("Show deployed.")
        except Exception as e:
            log.warning(f"Firebase deploy failed: {e}")


if __name__ == "__main__":
    main()
