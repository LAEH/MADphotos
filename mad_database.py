#!/usr/bin/env python3
"""
mad_database.py — Centralized SQLite schema and helpers for the MADphotos pipeline.

All scripts share this module for database access. The single DB file
(mad_photos.db) is the source of truth for image state, tier paths,
AI variant tracking, Gemini analysis, GCS uploads, and pipeline runs.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "mad_photos.db"

SCHEMA_VERSION = 1

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- Core image registry (one row per original photograph)
CREATE TABLE IF NOT EXISTS images (
    uuid            TEXT PRIMARY KEY,
    original_path   TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    category        TEXT NOT NULL,
    subcategory     TEXT NOT NULL,
    source_format   TEXT NOT NULL,
    width           INTEGER NOT NULL,
    height          INTEGER NOT NULL,
    aspect_ratio    REAL NOT NULL,
    orientation     TEXT NOT NULL,
    original_size_bytes INTEGER,
    exif_data       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- All rendered tiers (originals AND AI variants)
CREATE TABLE IF NOT EXISTS tiers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid      TEXT NOT NULL REFERENCES images(uuid),
    variant_id      TEXT REFERENCES ai_variants(variant_id),
    tier_name       TEXT NOT NULL,
    format          TEXT NOT NULL,
    local_path      TEXT,
    gcs_url         TEXT,
    public_url      TEXT,
    width           INTEGER,
    height          INTEGER,
    file_size_bytes INTEGER,
    uploaded_at     TEXT,
    UNIQUE(image_uuid, variant_id, tier_name, format)
);

-- AI variant generation records
CREATE TABLE IF NOT EXISTS ai_variants (
    variant_id      TEXT PRIMARY KEY,
    image_uuid      TEXT NOT NULL REFERENCES images(uuid),
    variant_type    TEXT NOT NULL,
    model           TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    negative_prompt TEXT,
    edit_mode       TEXT NOT NULL,
    guidance_scale  REAL,
    seed            INTEGER,
    source_tier     TEXT NOT NULL DEFAULT 'display',
    generation_status TEXT NOT NULL DEFAULT 'pending',
    rai_reason      TEXT,
    error_message   TEXT,
    generation_time_ms INTEGER,
    created_at      TEXT NOT NULL
);

-- Gemini photography analysis
CREATE TABLE IF NOT EXISTS gemini_analysis (
    image_uuid      TEXT PRIMARY KEY REFERENCES images(uuid),
    model           TEXT NOT NULL,
    exposure        TEXT,
    sharpness       TEXT,
    lens_artifacts  TEXT,
    composition_technique TEXT,
    depth           TEXT,
    geometry        TEXT,
    color_palette   TEXT,
    semantic_pops   TEXT,
    grading_style   TEXT,
    time_of_day     TEXT,
    setting         TEXT,
    weather         TEXT,
    faces_count     INTEGER,
    vibe            TEXT,
    alt_text        TEXT,
    raw_json        TEXT NOT NULL,
    analyzed_at     TEXT NOT NULL,
    error           TEXT
);

-- Pipeline execution log
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phase           TEXT NOT NULL,
    status          TEXT NOT NULL,
    images_processed INTEGER DEFAULT 0,
    images_failed   INTEGER DEFAULT 0,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    error_message   TEXT,
    config          TEXT
);

-- GCS upload tracking
CREATE TABLE IF NOT EXISTS gcs_uploads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    local_path      TEXT NOT NULL,
    gcs_path        TEXT NOT NULL,
    file_size_bytes INTEGER,
    uploaded_at     TEXT NOT NULL,
    verified        INTEGER DEFAULT 0,
    UNIQUE(gcs_path)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_images_category ON images(category, subcategory);
CREATE INDEX IF NOT EXISTS idx_tiers_image ON tiers(image_uuid);
CREATE INDEX IF NOT EXISTS idx_tiers_variant ON tiers(variant_id);
CREATE INDEX IF NOT EXISTS idx_tiers_gcs ON tiers(gcs_url);
CREATE INDEX IF NOT EXISTS idx_variants_image ON ai_variants(image_uuid);
CREATE INDEX IF NOT EXISTS idx_variants_type ON ai_variants(variant_type);
CREATE INDEX IF NOT EXISTS idx_variants_status ON ai_variants(generation_status);
"""


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (and initialize if needed) the database."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # Run schema creation (IF NOT EXISTS makes it safe to run every time)
    conn.executescript(_SCHEMA_SQL)
    # Ensure version row
    cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
    if cur.fetchone() is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Helpers — images
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def image_exists(conn: sqlite3.Connection, uuid: str) -> bool:
    row = conn.execute("SELECT 1 FROM images WHERE uuid = ?", (uuid,)).fetchone()
    return row is not None


def upsert_image(conn: sqlite3.Connection, *, uuid: str, original_path: str,
                 filename: str, category: str, subcategory: str,
                 source_format: str, width: int, height: int,
                 original_size_bytes: Optional[int] = None,
                 exif_data: Optional[str] = None) -> None:
    aspect = width / height if height else 0
    if width > height:
        orientation = "landscape"
    elif height > width:
        orientation = "portrait"
    else:
        orientation = "square"
    now = _now()
    conn.execute("""
        INSERT INTO images (uuid, original_path, filename, category, subcategory,
            source_format, width, height, aspect_ratio, orientation,
            original_size_bytes, exif_data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(uuid) DO UPDATE SET
            width=excluded.width, height=excluded.height,
            aspect_ratio=excluded.aspect_ratio, orientation=excluded.orientation,
            original_size_bytes=excluded.original_size_bytes,
            exif_data=excluded.exif_data, updated_at=excluded.updated_at
    """, (uuid, original_path, filename, category, subcategory,
          source_format, width, height, aspect, orientation,
          original_size_bytes, exif_data, now, now))
    conn.commit()


def get_all_image_uuids(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT uuid FROM images").fetchall()
    return {r["uuid"] for r in rows}


# ---------------------------------------------------------------------------
# Helpers — tiers
# ---------------------------------------------------------------------------

def tier_exists(conn: sqlite3.Connection, image_uuid: str,
                tier_name: str, fmt: str,
                variant_id: Optional[str] = None) -> bool:
    if variant_id:
        row = conn.execute(
            "SELECT 1 FROM tiers WHERE image_uuid=? AND variant_id=? AND tier_name=? AND format=?",
            (image_uuid, variant_id, tier_name, fmt)).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM tiers WHERE image_uuid=? AND variant_id IS NULL AND tier_name=? AND format=?",
            (image_uuid, tier_name, fmt)).fetchone()
    return row is not None


def upsert_tier(conn: sqlite3.Connection, *, image_uuid: str,
                tier_name: str, fmt: str, local_path: str,
                variant_id: Optional[str] = None,
                width: Optional[int] = None, height: Optional[int] = None,
                file_size_bytes: Optional[int] = None) -> None:
    conn.execute("""
        INSERT INTO tiers (image_uuid, variant_id, tier_name, format, local_path,
                           width, height, file_size_bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(image_uuid, variant_id, tier_name, format) DO UPDATE SET
            local_path=excluded.local_path, width=excluded.width,
            height=excluded.height, file_size_bytes=excluded.file_size_bytes
    """, (image_uuid, variant_id, tier_name, fmt, local_path,
          width, height, file_size_bytes))


def update_tier_gcs(conn: sqlite3.Connection, image_uuid: str,
                    tier_name: str, fmt: str,
                    gcs_url: str, public_url: str,
                    variant_id: Optional[str] = None) -> None:
    now = _now()
    if variant_id:
        conn.execute("""
            UPDATE tiers SET gcs_url=?, public_url=?, uploaded_at=?
            WHERE image_uuid=? AND variant_id=? AND tier_name=? AND format=?
        """, (gcs_url, public_url, now, image_uuid, variant_id, tier_name, fmt))
    else:
        conn.execute("""
            UPDATE tiers SET gcs_url=?, public_url=?, uploaded_at=?
            WHERE image_uuid=? AND variant_id IS NULL AND tier_name=? AND format=?
        """, (gcs_url, public_url, now, image_uuid, tier_name, fmt))


def get_image_tiers_count(conn: sqlite3.Connection, image_uuid: str,
                          variant_id: Optional[str] = None) -> int:
    """Count how many tier rows exist for an image (optionally for a specific variant)."""
    if variant_id:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM tiers WHERE image_uuid=? AND variant_id=?",
            (image_uuid, variant_id)).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM tiers WHERE image_uuid=? AND variant_id IS NULL",
            (image_uuid,)).fetchone()
    return row["c"]


# ---------------------------------------------------------------------------
# Helpers — AI variants
# ---------------------------------------------------------------------------

def variant_exists(conn: sqlite3.Connection, variant_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM ai_variants WHERE variant_id = ?", (variant_id,)).fetchone()
    return row is not None


def get_variant_status(conn: sqlite3.Connection, variant_id: str) -> Optional[str]:
    row = conn.execute("SELECT generation_status FROM ai_variants WHERE variant_id = ?",
                       (variant_id,)).fetchone()
    return row["generation_status"] if row else None


def upsert_variant(conn: sqlite3.Connection, *, variant_id: str, image_uuid: str,
                   variant_type: str, model: str, prompt: str,
                   negative_prompt: Optional[str] = None,
                   edit_mode: str = "EDIT_MODE_STYLE",
                   guidance_scale: Optional[float] = None,
                   seed: Optional[int] = None,
                   source_tier: str = "display",
                   generation_status: str = "pending",
                   rai_reason: Optional[str] = None,
                   error_message: Optional[str] = None,
                   generation_time_ms: Optional[int] = None) -> None:
    now = _now()
    conn.execute("""
        INSERT INTO ai_variants (variant_id, image_uuid, variant_type, model, prompt,
            negative_prompt, edit_mode, guidance_scale, seed, source_tier,
            generation_status, rai_reason, error_message, generation_time_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(variant_id) DO UPDATE SET
            generation_status=excluded.generation_status,
            rai_reason=excluded.rai_reason,
            error_message=excluded.error_message,
            generation_time_ms=excluded.generation_time_ms
    """, (variant_id, image_uuid, variant_type, model, prompt,
          negative_prompt, edit_mode, guidance_scale, seed, source_tier,
          generation_status, rai_reason, error_message, generation_time_ms, now))
    conn.commit()


def get_ungenerated_variants(conn: sqlite3.Connection,
                             variant_type: Optional[str] = None,
                             include_failed: bool = True) -> List[Dict]:
    """Return image UUIDs that need a variant generated.

    By default also retries 'failed' variants (only skips 'success' and 'filtered').
    """
    if variant_type:
        skip_statuses = ("success", "filtered")
        if not include_failed:
            skip_statuses = ("success", "filtered", "failed")
        rows = conn.execute("""
            SELECT i.uuid, i.original_path, i.category, i.subcategory
            FROM images i
            WHERE NOT EXISTS (
                SELECT 1 FROM ai_variants v
                WHERE v.image_uuid = i.uuid
                  AND v.variant_type = ?
                  AND v.generation_status IN (?, ?)
            )
            ORDER BY i.uuid
        """, (variant_type, skip_statuses[0], skip_statuses[1])).fetchall()
    else:
        rows = conn.execute("""
            SELECT DISTINCT i.uuid, i.original_path, i.category, i.subcategory
            FROM images i
            ORDER BY i.uuid
        """).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers — Gemini analysis
# ---------------------------------------------------------------------------

def analysis_exists(conn: sqlite3.Connection, image_uuid: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM gemini_analysis WHERE image_uuid = ? AND raw_json IS NOT NULL",
        (image_uuid,)).fetchone()
    return row is not None


def upsert_analysis(conn: sqlite3.Connection, *, image_uuid: str, model: str,
                    raw_json: str, parsed: Optional[Dict] = None,
                    error: Optional[str] = None) -> None:
    now = _now()
    tech = (parsed or {}).get("technical", {})
    comp = (parsed or {}).get("composition", {})
    color = (parsed or {}).get("color", {})
    env = (parsed or {}).get("environment", {})
    narr = (parsed or {}).get("narrative", {})

    conn.execute("""
        INSERT INTO gemini_analysis (image_uuid, model, exposure, sharpness, lens_artifacts,
            composition_technique, depth, geometry, color_palette, semantic_pops,
            grading_style, time_of_day, setting, weather, faces_count, vibe, alt_text,
            raw_json, analyzed_at, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(image_uuid) DO UPDATE SET
            model=excluded.model, exposure=excluded.exposure, sharpness=excluded.sharpness,
            lens_artifacts=excluded.lens_artifacts, composition_technique=excluded.composition_technique,
            depth=excluded.depth, geometry=excluded.geometry, color_palette=excluded.color_palette,
            semantic_pops=excluded.semantic_pops, grading_style=excluded.grading_style,
            time_of_day=excluded.time_of_day, setting=excluded.setting, weather=excluded.weather,
            faces_count=excluded.faces_count, vibe=excluded.vibe, alt_text=excluded.alt_text,
            raw_json=excluded.raw_json, analyzed_at=excluded.analyzed_at, error=excluded.error
    """, (
        image_uuid, model,
        tech.get("exposure"), tech.get("sharpness"),
        json.dumps(tech.get("lens_artifacts")) if tech.get("lens_artifacts") else None,
        comp.get("technique"), comp.get("depth"),
        json.dumps(comp.get("geometry")) if comp.get("geometry") else None,
        json.dumps(color.get("palette")) if color.get("palette") else None,
        json.dumps(color.get("semantic_pops")) if color.get("semantic_pops") else None,
        color.get("grading_style"),
        env.get("time"), env.get("setting"), env.get("weather"),
        narr.get("faces"), json.dumps(narr.get("vibe")) if narr.get("vibe") else None,
        narr.get("alt_text"),
        raw_json, now, error,
    ))
    conn.commit()


def get_unanalyzed_uuids(conn: sqlite3.Connection, include_errors: bool = True) -> List[str]:
    """Return UUIDs that need Gemini analysis. By default retries errored ones too."""
    if include_errors:
        # Missing entirely OR has an error (empty raw_json)
        rows = conn.execute("""
            SELECT i.uuid FROM images i
            WHERE NOT EXISTS (
                SELECT 1 FROM gemini_analysis g
                WHERE g.image_uuid = i.uuid
                  AND g.raw_json IS NOT NULL
                  AND g.raw_json != ''
                  AND g.error IS NULL
            )
            ORDER BY i.uuid
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT i.uuid FROM images i
            WHERE NOT EXISTS (
                SELECT 1 FROM gemini_analysis g
                WHERE g.image_uuid = i.uuid AND g.raw_json IS NOT NULL AND g.raw_json != ''
            )
            ORDER BY i.uuid
        """).fetchall()
    return [r["uuid"] for r in rows]


# ---------------------------------------------------------------------------
# Helpers — pipeline runs
# ---------------------------------------------------------------------------

def start_run(conn: sqlite3.Connection, phase: str, config: Optional[Dict] = None) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO pipeline_runs (phase, status, started_at, config) VALUES (?, 'started', ?, ?)",
        (phase, now, json.dumps(config) if config else None))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, *,
               images_processed: int = 0, images_failed: int = 0,
               status: str = "completed", error_message: Optional[str] = None) -> None:
    now = _now()
    conn.execute("""
        UPDATE pipeline_runs SET status=?, images_processed=?, images_failed=?,
            completed_at=?, error_message=?
        WHERE run_id=?
    """, (status, images_processed, images_failed, now, error_message, run_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers — GCS uploads
# ---------------------------------------------------------------------------

def record_upload(conn: sqlite3.Connection, local_path: str, gcs_path: str,
                  file_size_bytes: Optional[int] = None) -> None:
    now = _now()
    conn.execute("""
        INSERT INTO gcs_uploads (local_path, gcs_path, file_size_bytes, uploaded_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(gcs_path) DO UPDATE SET
            uploaded_at=excluded.uploaded_at, file_size_bytes=excluded.file_size_bytes
    """, (local_path, gcs_path, file_size_bytes, now))


def is_uploaded(conn: sqlite3.Connection, gcs_path: str) -> bool:
    row = conn.execute("SELECT 1 FROM gcs_uploads WHERE gcs_path = ?", (gcs_path,)).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Stats & export
# ---------------------------------------------------------------------------

def get_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    imgs = conn.execute("SELECT COUNT(*) as c FROM images").fetchone()["c"]
    tiers_count = conn.execute("SELECT COUNT(*) as c FROM tiers").fetchone()["c"]
    variants = conn.execute("SELECT COUNT(*) as c FROM ai_variants WHERE generation_status='success'").fetchone()["c"]
    analyzed = conn.execute("SELECT COUNT(*) as c FROM gemini_analysis WHERE raw_json IS NOT NULL").fetchone()["c"]
    uploaded = conn.execute("SELECT COUNT(*) as c FROM gcs_uploads").fetchone()["c"]
    return {
        "images": imgs,
        "tier_files": tiers_count,
        "ai_variants_generated": variants,
        "gemini_analyzed": analyzed,
        "gcs_uploaded": uploaded,
    }


def export_json(conn: sqlite3.Connection, output_path: Path) -> None:
    """Export the entire database as a JSON file."""
    data = {"version": SCHEMA_VERSION, "exported_at": _now(), "images": {}}
    rows = conn.execute("SELECT * FROM images ORDER BY uuid").fetchall()
    for img in rows:
        uuid = img["uuid"]
        entry = dict(img)
        # Attach tiers
        tier_rows = conn.execute(
            "SELECT * FROM tiers WHERE image_uuid = ?", (uuid,)).fetchall()
        entry["tiers"] = [dict(t) for t in tier_rows]
        # Attach variants
        var_rows = conn.execute(
            "SELECT * FROM ai_variants WHERE image_uuid = ?", (uuid,)).fetchall()
        entry["ai_variants"] = [dict(v) for v in var_rows]
        # Attach analysis
        analysis = conn.execute(
            "SELECT * FROM gemini_analysis WHERE image_uuid = ?", (uuid,)).fetchone()
        entry["gemini_analysis"] = dict(analysis) if analysis else None
        data["images"][uuid] = entry
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
