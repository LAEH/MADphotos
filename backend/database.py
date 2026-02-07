#!/usr/bin/env python3
"""
database.py — Centralized SQLite schema and helpers for the MADphotos pipeline.

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"

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
    camera_body     TEXT,
    film_stock      TEXT,
    medium          TEXT,
    is_monochrome   INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    curated_status  TEXT DEFAULT 'pending'
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

-- Location intelligence (GPS, manual tags, propagated suggestions)
CREATE TABLE IF NOT EXISTS image_locations (
    image_uuid      TEXT PRIMARY KEY REFERENCES images(uuid),
    location_name   TEXT,
    latitude        REAL,
    longitude       REAL,
    source          TEXT,  -- 'gps_exif' / 'user_manual' / 'propagated'
    confidence      REAL,
    propagated_from TEXT,
    accepted        INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_locations_name ON image_locations(location_name);
CREATE INDEX IF NOT EXISTS idx_locations_source ON image_locations(source);

-- Per-image enhancement recipes (computed from pixel analysis + camera profile)
CREATE TABLE IF NOT EXISTS enhancement_plans (
    image_uuid          TEXT PRIMARY KEY,
    version             INTEGER DEFAULT 1,
    camera_body         TEXT,
    plan_json           TEXT,
    -- Key parameters (queryable)
    wb_correction_r     REAL,
    wb_correction_b     REAL,
    gamma               REAL,
    shadow_lift          REAL,
    highlight_pull       REAL,
    contrast_strength    REAL,
    saturation_scale     REAL,
    sharpen_radius       REAL,
    sharpen_percent      REAL,
    -- Execution tracking
    status              TEXT DEFAULT 'planned',
    source_tier         TEXT DEFAULT 'display',
    output_path         TEXT,
    -- Pre/post metrics for comparison
    pre_brightness      REAL,
    post_brightness     REAL,
    pre_wb_shift_r      REAL,
    post_wb_shift_r     REAL,
    pre_contrast        REAL,
    post_contrast       REAL,
    -- Timestamps
    planned_at          TEXT,
    enhanced_at         TEXT,
    reviewed_at         TEXT,
    FOREIGN KEY (image_uuid) REFERENCES images(uuid)
);
CREATE INDEX IF NOT EXISTS idx_enhance_status ON enhancement_plans(status);
CREATE INDEX IF NOT EXISTS idx_enhance_camera ON enhancement_plans(camera_body);

-- V2 signal-aware enhancement recipes (uses depth, scene, style, Gemini, faces)
CREATE TABLE IF NOT EXISTS enhancement_plans_v2 (
    image_uuid          TEXT PRIMARY KEY,
    camera_body         TEXT,
    plan_json           TEXT,
    -- Key parameters
    wb_correction_r     REAL,
    wb_correction_b     REAL,
    gamma               REAL,
    shadow_lift          REAL,
    highlight_pull       REAL,
    contrast_strength    REAL,
    saturation_scale     REAL,
    sharpen_radius       REAL,
    sharpen_percent      REAL,
    -- Signal-specific adjustments
    depth_adjustment     TEXT,
    scene_adjustment     TEXT,
    style_adjustment     TEXT,
    vibe_adjustment      TEXT,
    face_adjustment      TEXT,
    -- Execution tracking
    status              TEXT DEFAULT 'planned',
    source_tier         TEXT DEFAULT 'display',
    output_path         TEXT,
    -- Pre/post metrics
    pre_brightness      REAL,
    post_brightness     REAL,
    pre_wb_shift_r      REAL,
    post_wb_shift_r     REAL,
    pre_contrast        REAL,
    post_contrast       REAL,
    -- Timestamps
    planned_at          TEXT,
    enhanced_at         TEXT,
    FOREIGN KEY (image_uuid) REFERENCES images(uuid)
);
CREATE INDEX IF NOT EXISTS idx_enhance_v2_status ON enhancement_plans_v2(status);

-- Programmatic image analysis (pixel-level metrics for auto-enhance)
CREATE TABLE IF NOT EXISTS image_analysis (
    image_uuid          TEXT PRIMARY KEY REFERENCES images(uuid),
    mean_brightness     REAL,
    std_brightness      REAL,
    clip_low_pct        REAL,
    clip_high_pct       REAL,
    dynamic_range       REAL,
    mean_saturation     REAL,
    std_saturation      REAL,
    mean_r              REAL,
    mean_g              REAL,
    mean_b              REAL,
    wb_shift_r          REAL,
    wb_shift_b          REAL,
    color_cast          TEXT,
    contrast_ratio      REAL,
    noise_estimate      REAL,
    dominant_hue        INTEGER,
    is_low_key          INTEGER DEFAULT 0,
    is_high_key         INTEGER DEFAULT 0,
    shadow_pct          REAL,
    midtone_pct         REAL,
    highlight_pct       REAL,
    shadow_mean         REAL,
    midtone_mean        REAL,
    highlight_mean      REAL,
    est_color_temp      INTEGER,
    shadow_wb_r         REAL,
    shadow_wb_b         REAL,
    highlight_wb_r      REAL,
    highlight_wb_b      REAL,
    histogram_json      TEXT,
    analyzed_at         TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Migrations for existing databases
# ---------------------------------------------------------------------------

_MIGRATIONS = [
    # v2: camera metadata on images table
    ("images", "camera_body", "ALTER TABLE images ADD COLUMN camera_body TEXT"),
    ("images", "film_stock", "ALTER TABLE images ADD COLUMN film_stock TEXT"),
    ("images", "medium", "ALTER TABLE images ADD COLUMN medium TEXT"),
    ("images", "is_monochrome", "ALTER TABLE images ADD COLUMN is_monochrome INTEGER DEFAULT 0"),
    ("images", "curated_status", "ALTER TABLE images ADD COLUMN curated_status TEXT DEFAULT 'pending'"),
    # v3: enriched image_analysis columns
    ("image_analysis", "shadow_pct", "ALTER TABLE image_analysis ADD COLUMN shadow_pct REAL"),
    ("image_analysis", "midtone_pct", "ALTER TABLE image_analysis ADD COLUMN midtone_pct REAL"),
    ("image_analysis", "highlight_pct", "ALTER TABLE image_analysis ADD COLUMN highlight_pct REAL"),
    ("image_analysis", "shadow_mean", "ALTER TABLE image_analysis ADD COLUMN shadow_mean REAL"),
    ("image_analysis", "midtone_mean", "ALTER TABLE image_analysis ADD COLUMN midtone_mean REAL"),
    ("image_analysis", "highlight_mean", "ALTER TABLE image_analysis ADD COLUMN highlight_mean REAL"),
    ("image_analysis", "est_color_temp", "ALTER TABLE image_analysis ADD COLUMN est_color_temp INTEGER"),
    ("image_analysis", "shadow_wb_r", "ALTER TABLE image_analysis ADD COLUMN shadow_wb_r REAL"),
    ("image_analysis", "shadow_wb_b", "ALTER TABLE image_analysis ADD COLUMN shadow_wb_b REAL"),
    ("image_analysis", "highlight_wb_r", "ALTER TABLE image_analysis ADD COLUMN highlight_wb_r REAL"),
    ("image_analysis", "highlight_wb_b", "ALTER TABLE image_analysis ADD COLUMN highlight_wb_b REAL"),
]


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Add columns that don't exist yet (safe to run repeatedly)."""
    for table, column, sql in _MIGRATIONS:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(sql)
    conn.commit()


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (and initialize if needed) the database."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # Run schema creation (IF NOT EXISTS makes it safe to run every time)
    conn.executescript(_SCHEMA_SQL)
    _run_migrations(conn)
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


# Camera metadata mapping: category/subcategory → (camera_body, film_stock, medium)
CAMERA_MAP = {
    ("Analog", None):       ("Leica MP", "Kodak Portra 400 VC", "scanned_film"),
    ("Digital", None):      ("Leica M8", None, "digital"),
    ("G12", None):          ("Canon G12", None, "digital"),
    ("Monochrome", None):   ("Leica Monochrom", None, "digital"),
    ("Osmo", "OsmoPro"):    ("DJI Osmo Pro", None, "digital"),
    ("Osmo", "OsmoMemo"):   ("DJI Osmo Memo", None, "digital"),
}


def populate_camera_metadata(conn: sqlite3.Connection) -> int:
    """Fill camera_body, film_stock, medium, is_monochrome from category mapping."""
    updated = 0
    for (cat, sub), (camera, film, medium) in CAMERA_MAP.items():
        if sub:
            where = "category = ? AND subcategory = ?"
            params = [camera, film, medium, cat, sub]
        else:
            where = "category = ?"
            params = [camera, film, medium, cat]
        cur = conn.execute(f"""
            UPDATE images SET camera_body = ?, film_stock = ?, medium = ?
            WHERE {where} AND camera_body IS NULL
        """, params)
        updated += cur.rowcount

    # Monochrome category: always monochrome (Leica Monochrom sensor)
    conn.execute("UPDATE images SET is_monochrome = 1 WHERE category = 'Monochrome'")

    # Analog monochrome: detect from Gemini grading_style or leave for pixel analysis
    conn.execute("""
        UPDATE images SET is_monochrome = 1, film_stock = 'Monochrome Film'
        WHERE category = 'Analog' AND uuid IN (
            SELECT image_uuid FROM gemini_analysis WHERE grading_style = 'Monochrome'
        )
    """)

    conn.commit()
    return updated


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
                             include_failed: bool = True,
                             kept_only: bool = False) -> List[Dict]:
    """Return image UUIDs that need a variant generated.

    By default also retries 'failed' variants (only skips 'success' and 'filtered').
    If kept_only=True, only returns images with curated_status='kept'.
    """
    curated_filter = "AND i.curated_status = 'kept'" if kept_only else ""
    if variant_type:
        skip_statuses = ("success", "filtered")
        if not include_failed:
            skip_statuses = ("success", "filtered", "failed")
        rows = conn.execute(f"""
            SELECT i.uuid, i.original_path, i.category, i.subcategory
            FROM images i
            WHERE NOT EXISTS (
                SELECT 1 FROM ai_variants v
                WHERE v.image_uuid = i.uuid
                  AND v.variant_type = ?
                  AND v.generation_status IN (?, ?)
            )
            {curated_filter}
            ORDER BY i.uuid
        """, (variant_type, skip_statuses[0], skip_statuses[1])).fetchall()
    else:
        rows = conn.execute(f"""
            SELECT DISTINCT i.uuid, i.original_path, i.category, i.subcategory
            FROM images i
            WHERE 1=1 {curated_filter}
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
