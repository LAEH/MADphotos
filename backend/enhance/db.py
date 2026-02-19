"""Database helpers for the enhance proposal system."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from . import DB_PATH, BATCH_SIZE


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS enhance_proposals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            image_uuid    TEXT NOT NULL,
            type          TEXT NOT NULL,
            params_json   TEXT NOT NULL,
            preview_path  TEXT,
            batch_id      INTEGER,
            status        TEXT DEFAULT 'pending',
            feedback      TEXT,
            reviewed_at   TEXT,
            deployed_at   TEXT,
            created_at    TEXT NOT NULL,
            UNIQUE(image_uuid)
        );

        CREATE TABLE IF NOT EXISTS enhance_batches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT NOT NULL,
            status      TEXT DEFAULT 'active'
        );

        CREATE INDEX IF NOT EXISTS idx_enhance_proposals_status
            ON enhance_proposals(status);
        CREATE INDEX IF NOT EXISTS idx_enhance_proposals_batch
            ON enhance_proposals(batch_id);
        CREATE INDEX IF NOT EXISTS idx_enhance_proposals_type
            ON enhance_proposals(type);
    """)
    # Add feedback column if missing (migration from older schema)
    try:
        conn.execute("SELECT feedback FROM enhance_proposals LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE enhance_proposals ADD COLUMN feedback TEXT")
        conn.commit()


def get_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute("""
        SELECT type, status, count(*) as cnt
        FROM enhance_proposals
        GROUP BY type, status
    """).fetchall()
    by_type: Dict[str, Dict[str, int]] = {}
    totals = {"pending": 0, "accepted": 0, "rejected": 0, "deployed": 0, "feedback": 0}
    for r in rows:
        t = r["type"]
        s = r["status"]
        c = r["cnt"]
        if t not in by_type:
            by_type[t] = {}
        by_type[t][s] = c
        if s in totals:
            totals[s] += c
    # Count deployed separately (accepted + deployed_at set)
    deployed = conn.execute(
        "SELECT count(*) FROM enhance_proposals WHERE deployed_at IS NOT NULL"
    ).fetchone()[0]
    totals["deployed"] = deployed
    # Accepted but not yet deployed — this drives the Deploy button
    undeployed = conn.execute(
        "SELECT count(*) FROM enhance_proposals WHERE status = 'accepted' AND deployed_at IS NULL"
    ).fetchone()[0]
    totals["undeployed"] = undeployed
    # Count feedback items
    fb = conn.execute(
        "SELECT count(*) FROM enhance_proposals WHERE feedback IS NOT NULL AND status = 'feedback'"
    ).fetchone()[0]
    totals["feedback"] = fb
    return {"by_type": by_type, "totals": totals}


def get_or_create_batch(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT id FROM enhance_batches WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        return row["id"]
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO enhance_batches (created_at, status) VALUES (?, 'active')",
        (now,),
    )
    conn.commit()
    return cur.lastrowid


def get_batch_proposals(conn: sqlite3.Connection, batch_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT id, image_uuid, type, params_json, preview_path, status, feedback
        FROM enhance_proposals
        WHERE batch_id = ? AND status IN ('pending', 'feedback')
        ORDER BY
            CASE WHEN feedback IS NOT NULL THEN 0 ELSE 1 END,
            RANDOM()
    """, (batch_id,)).fetchall()
    return [dict(r) for r in rows]


def assign_batch(conn: sqlite3.Connection, batch_id: int) -> int:
    """Assign up to BATCH_SIZE unassigned proposals to the given batch.
    Feedback items first, then diverse random sample across types."""
    cur = conn.execute("""
        UPDATE enhance_proposals
        SET batch_id = ?
        WHERE id IN (
            SELECT id FROM enhance_proposals
            WHERE batch_id IS NULL AND status IN ('pending', 'feedback')
            ORDER BY
                CASE WHEN status = 'feedback' THEN 0 ELSE 1 END,
                RANDOM()
            LIMIT ?
        )
    """, (batch_id, BATCH_SIZE))
    conn.commit()
    return cur.rowcount


def update_proposal(conn: sqlite3.Connection, proposal_id: int, status: str,
                    feedback: str | None = None) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    if status == 'feedback':
        cur = conn.execute(
            """UPDATE enhance_proposals
               SET status = 'feedback', feedback = ?, reviewed_at = ?, batch_id = NULL
               WHERE id = ?""",
            (feedback, now, proposal_id),
        )
    else:
        cur = conn.execute(
            "UPDATE enhance_proposals SET status = ?, reviewed_at = ? WHERE id = ?",
            (status, now, proposal_id),
        )
    conn.commit()
    return cur.rowcount > 0


def get_accepted_undeployed(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT id, image_uuid, type, params_json, preview_path
        FROM enhance_proposals
        WHERE status = 'accepted' AND deployed_at IS NULL
        ORDER BY id
    """).fetchall()
    return [dict(r) for r in rows]


def complete_batch(conn: sqlite3.Connection, batch_id: int) -> None:
    """Mark batch as completed if all proposals are reviewed."""
    pending = conn.execute(
        "SELECT count(*) FROM enhance_proposals WHERE batch_id = ? AND status IN ('pending', 'feedback')",
        (batch_id,),
    ).fetchone()[0]
    if pending == 0:
        conn.execute(
            "UPDATE enhance_batches SET status = 'completed' WHERE id = ?",
            (batch_id,),
        )
        conn.commit()


def mark_deployed(conn: sqlite3.Connection, proposal_ids: List[int]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for pid in proposal_ids:
        conn.execute(
            "UPDATE enhance_proposals SET deployed_at = ? WHERE id = ?",
            (now, pid),
        )
        updated += 1
    conn.commit()
    return updated


def get_learning_stats(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    """Compute acceptance rate per primary type from reviewed proposals.
    Returns {type: {accepted: N, rejected: N, rate: 0.0-1.0}}."""
    rows = conn.execute("""
        SELECT type, status, count(*) as cnt
        FROM enhance_proposals
        WHERE status IN ('accepted', 'rejected')
        GROUP BY type, status
    """).fetchall()
    stats: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        t = r["type"]
        if t not in stats:
            stats[t] = {"accepted": 0, "rejected": 0, "rate": 0.0}
        stats[t][r["status"]] = r["cnt"]
    for t, s in stats.items():
        total = s["accepted"] + s["rejected"]
        s["rate"] = s["accepted"] / total if total > 0 else 0.0
    return stats


def get_proposed_uuids(conn: sqlite3.Connection) -> set:
    """Return set of all image_uuids that have any proposal (any status)."""
    rows = conn.execute("SELECT DISTINCT image_uuid FROM enhance_proposals").fetchall()
    return {r["image_uuid"] for r in rows}


def cleanup_rejected_previews(conn: sqlite3.Connection) -> int:
    """Delete preview files for rejected proposals, return count deleted."""
    from . import PREVIEW_DIR
    rows = conn.execute("""
        SELECT id, preview_path FROM enhance_proposals
        WHERE status = 'rejected' AND preview_path IS NOT NULL
    """).fetchall()
    deleted = 0
    for r in rows:
        preview = PREVIEW_DIR.parent.parent / r["preview_path"]
        if preview.exists():
            preview.unlink()
            deleted += 1
    return deleted
