#!/usr/bin/env python3
"""
generate_status_page.py — Full system dashboard for MADphotos.

Usage:
    python generate_status_page.py              # Generate static docs/index.html
    python generate_status_page.py --serve      # Live dashboard at localhost:8080
    python generate_status_page.py --serve 9000 # Custom port
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "mad_photos.db"
VECTOR_PATH = Path(__file__).resolve().parent / "vectors.lance"
OUT_PATH = Path(__file__).resolve().parent / "docs" / "index.html"
MOSAIC_DIR = Path(__file__).resolve().parent / "rendered" / "mosaics"


def human_bytes(n):
    # type: (int) -> str
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def pct(part, whole):
    # type: (int, int) -> float
    return round(part / whole * 100, 2) if whole else 0.0


def get_stats():
    # type: () -> dict
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # ── Core counts ──────────────────────────────────────────
    total = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    analyzed = conn.execute(
        "SELECT COUNT(*) FROM gemini_analysis WHERE raw_json IS NOT NULL AND raw_json != ''"
    ).fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM gemini_analysis WHERE error IS NOT NULL AND (raw_json IS NULL OR raw_json = '')"
    ).fetchone()[0]
    pending = total - analyzed - failed
    pixel_analyzed = conn.execute("SELECT COUNT(*) FROM image_analysis").fetchone()[0]

    # ── Categories ───────────────────────────────────────────
    categories = [
        {"name": r["category"], "count": r["cnt"]}
        for r in conn.execute(
            "SELECT category, COUNT(*) as cnt FROM images GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
    ]

    # Subcategories mapped to camera-body friendly names
    _sub_name_map = {
        ("Digital", None): "Leica Digital",
        ("Digital", "Landscape"): "Leica Digital",
        ("Digital", "Portrait"): "Leica Digital",
        ("Analog", None): "Leica Analog",
        ("Analog", "Landscape"): "Leica Analog",
        ("Analog", "Portrait"): "Leica Analog",
        ("Monochrome", None): "Leica Monochrom",
        ("Monochrome", "Landscape"): "Leica Monochrom",
        ("Monochrome", "Portrait"): "Leica Monochrom",
        ("G12", None): "Canon G12",
        ("Osmo", "OsmoPro"): "DJI Osmo Pro",
        ("Osmo", "OsmoMemo"): "DJI Osmo Memo",
        ("Osmo", None): "DJI Osmo",
    }
    _sub_counts = {}  # type: Dict[str, int]
    for r in conn.execute(
        "SELECT category, subcategory, COUNT(*) as cnt FROM images "
        "GROUP BY category, subcategory ORDER BY category, cnt DESC"
    ).fetchall():
        key = (r["category"], r["subcategory"])
        friendly = _sub_name_map.get(key, f'{r["category"]}/{r["subcategory"]}' if r["subcategory"] else r["category"])
        _sub_counts[friendly] = _sub_counts.get(friendly, 0) + r["cnt"]
    subcategories = [
        {"name": name, "count": count}
        for name, count in sorted(_sub_counts.items(), key=lambda x: -x[1])
    ]

    # ── Tiers ────────────────────────────────────────────────
    # One row per tier/format combination (e.g. display/jpeg, display/webp)
    _tier_order = {'full': 0, 'original': 1, 'display': 2, 'mobile': 3,
                   'thumb': 4, 'micro': 5, 'gemini': 6}
    tiers = [
        {"name": r["tier_name"] + "/" + (r["format"] or "?"),
         "tier": r["tier_name"], "format": r["format"],
         "count": r["cnt"],
         "size": r["size"] or 0,
         "size_human": human_bytes(r["size"]) if r["size"] else "0 B"}
        for r in conn.execute(
            "SELECT tier_name, format, COUNT(*) as cnt, SUM(file_size_bytes) as size "
            "FROM tiers GROUP BY tier_name, format ORDER BY tier_name, format"
        ).fetchall()
    ]
    tiers.sort(key=lambda x: (_tier_order.get(x["tier"], 99), x["format"]))
    total_rendered_bytes = conn.execute(
        "SELECT COALESCE(SUM(file_size_bytes), 0) FROM tiers"
    ).fetchone()[0]
    total_tier_files = conn.execute("SELECT COUNT(*) FROM tiers").fetchone()[0]

    # ── Tier coverage ────────────────────────────────────────
    tier_coverage = []
    for tier in ['full', 'display', 'mobile', 'thumb', 'micro', 'gemini', 'original']:
        cnt = conn.execute(
            f"SELECT COUNT(DISTINCT image_uuid) FROM tiers WHERE tier_name=?", (tier,)
        ).fetchone()[0]
        tier_coverage.append({"tier": tier, "images": cnt})

    # ── AI Variants ──────────────────────────────────────────
    ai_variants_total = conn.execute("SELECT COUNT(*) FROM ai_variants").fetchone()[0]
    variant_summary = []
    for r in conn.execute(
        "SELECT variant_type, "
        "SUM(CASE WHEN generation_status='success' THEN 1 ELSE 0 END) as ok, "
        "SUM(CASE WHEN generation_status='failed' THEN 1 ELSE 0 END) as fail, "
        "SUM(CASE WHEN generation_status='filtered' OR generation_status='rai_filtered' THEN 1 ELSE 0 END) as filtered, "
        "SUM(CASE WHEN generation_status='pending' THEN 1 ELSE 0 END) as pending, "
        "COUNT(*) as total "
        "FROM ai_variants GROUP BY variant_type ORDER BY variant_type"
    ).fetchall():
        variant_summary.append({
            "type": r["variant_type"], "ok": r["ok"], "fail": r["fail"],
            "filtered": r["filtered"], "pending": r["pending"], "total": r["total"],
            "pct": pct(r["ok"], total),
        })

    gcs_uploads = conn.execute("SELECT COUNT(*) FROM gcs_uploads").fetchone()[0]

    # ── Camera fleet ─────────────────────────────────────────
    cameras = []
    for r in conn.execute("""
        SELECT i.camera_body, COUNT(*) as cnt, i.medium, i.film_stock,
               ROUND(AVG(a.wb_shift_r), 3) as wb_r,
               ROUND(AVG(a.wb_shift_b), 3) as wb_b,
               ROUND(AVG(a.noise_estimate), 1) as noise,
               ROUND(AVG(a.clip_low_pct), 1) as shadow_clip,
               ROUND(AVG(a.mean_brightness), 1) as luminance
        FROM images i LEFT JOIN image_analysis a ON i.uuid = a.image_uuid
        GROUP BY i.camera_body ORDER BY cnt DESC
    """).fetchall():
        cameras.append({
            "body": r["camera_body"],
            "count": r["cnt"],
            "medium": r["medium"] or "—",
            "film": r["film_stock"] or "—",
            "wb_r": r["wb_r"] or 0,
            "wb_b": r["wb_b"] or 0,
            "noise": r["noise"] or 0,
            "shadow": r["shadow_clip"] or 0,
            "luminance": r["luminance"] or 0,
        })

    # ── Source format ────────────────────────────────────────
    source_formats = [
        {"name": r[0], "count": r[1]}
        for r in conn.execute("""
            SELECT CASE
                WHEN original_path LIKE '%.jpg' OR original_path LIKE '%.JPG' THEN 'JPEG'
                WHEN original_path LIKE '%.dng' OR original_path LIKE '%.DNG' THEN 'DNG'
                WHEN original_path LIKE '%.raw' OR original_path LIKE '%.RAW' THEN 'RAW'
                ELSE 'other'
            END as fmt, COUNT(*)
            FROM images GROUP BY fmt ORDER BY COUNT(*) DESC
        """).fetchall()
    ]

    monochrome_count = conn.execute("SELECT COUNT(*) FROM images WHERE is_monochrome=1").fetchone()[0]

    # ── Pixel analysis ───────────────────────────────────────
    color_cast = [
        {"name": r[0] or "none", "count": r[1]}
        for r in conn.execute(
            "SELECT color_cast, COUNT(*) as cnt FROM image_analysis "
            "GROUP BY color_cast ORDER BY cnt DESC"
        ).fetchall()
    ]

    color_temp = [
        {"name": r[0], "count": r[1]}
        for r in conn.execute("""
            SELECT CASE
                WHEN est_color_temp < 3500 THEN 'warm (<3500K)'
                WHEN est_color_temp < 5000 THEN 'neutral (3500-5000K)'
                WHEN est_color_temp < 7000 THEN 'cool (5000-7000K)'
                ELSE 'very cool (>7000K)'
            END as range, COUNT(*) as cnt
            FROM image_analysis WHERE est_color_temp IS NOT NULL
            GROUP BY range ORDER BY cnt DESC
        """).fetchall()
    ]

    # ── Gemini insights ──────────────────────────────────────
    grading = [
        {"name": r["grading_style"], "count": r["cnt"]}
        for r in conn.execute(
            "SELECT grading_style, COUNT(*) as cnt FROM gemini_analysis "
            "WHERE raw_json != '' GROUP BY grading_style ORDER BY cnt DESC"
        ).fetchall()
    ]

    time_of_day = [
        {"name": r[0], "count": r[1]}
        for r in conn.execute(
            "SELECT time_of_day, COUNT(*) as cnt FROM gemini_analysis "
            "WHERE time_of_day IS NOT NULL AND raw_json != '' "
            "GROUP BY time_of_day ORDER BY cnt DESC"
        ).fetchall()
    ]

    settings = [
        {"name": r[0], "count": r[1]}
        for r in conn.execute(
            "SELECT setting, COUNT(*) as cnt FROM gemini_analysis "
            "WHERE setting IS NOT NULL AND raw_json != '' "
            "GROUP BY setting ORDER BY cnt DESC"
        ).fetchall()
    ]

    exposure = [
        {"name": r[0], "count": r[1]}
        for r in conn.execute(
            "SELECT exposure, COUNT(*) as cnt FROM gemini_analysis "
            "WHERE exposure IS NOT NULL AND raw_json != '' "
            "GROUP BY exposure ORDER BY cnt DESC"
        ).fetchall()
    ]

    composition = [
        {"name": r[0], "count": r[1]}
        for r in conn.execute(
            "SELECT composition_technique, COUNT(*) as cnt FROM gemini_analysis "
            "WHERE composition_technique IS NOT NULL AND raw_json != '' "
            "GROUP BY composition_technique ORDER BY cnt DESC"
        ).fetchall()
    ]

    vibes = [
        {"name": r[0], "count": r[1]}
        for r in conn.execute("""
            SELECT value, COUNT(*) as cnt FROM gemini_analysis, json_each(gemini_analysis.vibe)
            WHERE vibe IS NOT NULL AND raw_json != '' GROUP BY value ORDER BY cnt DESC LIMIT 20
        """).fetchall()
    ]

    rotate_stats = [
        {"value": r["should_rotate"] or "unknown", "count": r["cnt"]}
        for r in conn.execute(
            "SELECT should_rotate, COUNT(*) as cnt FROM gemini_analysis "
            "WHERE raw_json != '' GROUP BY should_rotate ORDER BY cnt DESC"
        ).fetchall()
    ]

    has_edit_prompt = conn.execute(
        "SELECT COUNT(*) FROM gemini_analysis WHERE overall_edit_prompt IS NOT NULL AND overall_edit_prompt != ''"
    ).fetchone()[0]
    has_semantic_pops = conn.execute(
        "SELECT COUNT(*) FROM gemini_analysis WHERE semantic_pops IS NOT NULL AND semantic_pops != '[]'"
    ).fetchone()[0]

    # ── Curation ─────────────────────────────────────────────
    curation = [
        {"status": r[0] or "pending", "count": r[1]}
        for r in conn.execute(
            "SELECT curated_status, COUNT(*) as cnt FROM images GROUP BY curated_status ORDER BY cnt DESC"
        ).fetchall()
    ]
    kept = sum(c["count"] for c in curation if c["status"] == "kept")
    rejected = sum(c["count"] for c in curation if c["status"] == "rejected")
    curated_total = kept + rejected

    # ── Vector store ─────────────────────────────────────────
    vector_count = 0
    vector_size_human = "—"
    try:
        import lancedb as _ldb
        if VECTOR_PATH.exists():
            _db = _ldb.connect(str(VECTOR_PATH))
            _tbl = _db.open_table("image_vectors")
            vector_count = _tbl.count_rows()
            # Compute directory size
            vsize = sum(
                f.stat().st_size for f in VECTOR_PATH.rglob("*") if f.is_file()
            )
            vector_size_human = human_bytes(vsize)
    except Exception:
        pass

    # ── Signal extraction ─────────────────────────────────────
    signals = {}
    for tbl in ['exif_metadata', 'dominant_colors', 'face_detections', 'object_detections', 'image_hashes']:
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            uuids = conn.execute(f"SELECT COUNT(DISTINCT image_uuid) FROM {tbl}").fetchone()[0]
            signals[tbl] = {"rows": cnt, "images": uuids}
        except Exception:
            signals[tbl] = {"rows": 0, "images": 0}

    # For faces/objects, "processed" includes images with zero detections (tracked in JSON files)
    base_dir = Path(__file__).resolve().parent
    for key, fname in [('face_detections', '.faces_processed.json'),
                       ('object_detections', '.objects_processed.json')]:
        try:
            pf = base_dir / fname
            if pf.exists():
                no_det = len(json.loads(pf.read_text()))
                signals[key]["processed"] = signals[key]["images"] + no_det
        except Exception:
            pass

    # EXIF details
    exif_gps = 0
    exif_iso = 0
    try:
        exif_gps = conn.execute("SELECT COUNT(*) FROM exif_metadata WHERE gps_lat IS NOT NULL").fetchone()[0]
        exif_iso = conn.execute("SELECT COUNT(*) FROM exif_metadata WHERE iso IS NOT NULL").fetchone()[0]
    except Exception:
        pass

    # Face stats
    face_images_with = 0
    face_total = 0
    try:
        face_images_with = signals['face_detections']['images']
        face_total = signals['face_detections']['rows']
    except Exception:
        pass

    # Object detection top labels
    top_objects = []
    try:
        top_objects = [
            {"name": r[0], "count": r[1]}
            for r in conn.execute(
                "SELECT label, COUNT(*) as cnt FROM object_detections "
                "GROUP BY label ORDER BY cnt DESC LIMIT 20"
            ).fetchall()
        ]
    except Exception:
        pass

    # Top dominant colors — use average RGB per color_name for the pill
    top_color_names = []
    try:
        top_color_names = [
            {"name": r[0],
             "hex": "#{:02x}{:02x}{:02x}".format(int(r[1]), int(r[2]), int(r[3])),
             "count": r[4]}
            for r in conn.execute(
                "SELECT color_name, AVG(r), AVG(g), AVG(b), COUNT(*) as cnt "
                "FROM dominant_colors GROUP BY color_name ORDER BY cnt DESC LIMIT 30"
            ).fetchall()
        ]
    except Exception:
        pass

    # ── Advanced signals ────────────────────────────────────
    # Aesthetic scores
    aesthetic_count = 0
    aesthetic_avg = 0
    aesthetic_min = 0
    aesthetic_max = 0
    aesthetic_labels = []
    try:
        aesthetic_count = conn.execute("SELECT COUNT(*) FROM aesthetic_scores").fetchone()[0]
        row = conn.execute("SELECT ROUND(AVG(overall_score),2), MIN(overall_score), MAX(overall_score) FROM aesthetic_scores").fetchone()
        if row:
            aesthetic_avg = row[0] or 0
            aesthetic_min = row[1] or 0
            aesthetic_max = row[2] or 0
        aesthetic_labels = [
            {"name": r[0] or "unlabeled", "count": r[1]}
            for r in conn.execute(
                "SELECT score_label, COUNT(*) as cnt FROM aesthetic_scores "
                "GROUP BY score_label ORDER BY cnt DESC"
            ).fetchall()
        ]
    except Exception:
        pass

    # Depth estimation
    depth_count = 0
    depth_avg_near = 0
    depth_avg_mid = 0
    depth_avg_far = 0
    depth_complexity_buckets = []
    try:
        depth_count = conn.execute("SELECT COUNT(*) FROM depth_estimation").fetchone()[0]
        row = conn.execute("SELECT ROUND(AVG(near_pct),1), ROUND(AVG(mid_pct),1), ROUND(AVG(far_pct),1) FROM depth_estimation").fetchone()
        if row:
            depth_avg_near = row[0] or 0
            depth_avg_mid = row[1] or 0
            depth_avg_far = row[2] or 0
        depth_complexity_buckets = [
            {"name": r[0], "count": r[1]}
            for r in conn.execute("""
                SELECT CASE
                    WHEN depth_complexity < 1.0 THEN 'simple'
                    WHEN depth_complexity < 2.0 THEN 'moderate'
                    WHEN depth_complexity < 3.0 THEN 'layered'
                    ELSE 'complex'
                END as bucket, COUNT(*) as cnt
                FROM depth_estimation GROUP BY bucket ORDER BY cnt DESC
            """).fetchall()
        ]
    except Exception:
        pass

    # Scene classification
    scene_count = 0
    top_scenes = []
    scene_environments = []
    try:
        scene_count = conn.execute("SELECT COUNT(*) FROM scene_classification").fetchone()[0]
        top_scenes = [
            {"name": r[0], "count": r[1]}
            for r in conn.execute(
                "SELECT scene_1, COUNT(*) as cnt FROM scene_classification "
                "GROUP BY scene_1 ORDER BY cnt DESC LIMIT 15"
            ).fetchall()
        ]
        scene_environments = [
            {"name": r[0] or "unknown", "count": r[1]}
            for r in conn.execute(
                "SELECT environment, COUNT(*) as cnt FROM scene_classification "
                "GROUP BY environment ORDER BY cnt DESC"
            ).fetchall()
        ]
    except Exception:
        pass

    # Enhancement plans
    enhancement_count = 0
    enhancement_statuses = []
    enhancement_cameras = []
    try:
        enhancement_count = conn.execute("SELECT COUNT(*) FROM enhancement_plans").fetchone()[0]
        enhancement_statuses = [
            {"name": r[0] or "planned", "count": r[1]}
            for r in conn.execute(
                "SELECT status, COUNT(*) as cnt FROM enhancement_plans "
                "GROUP BY status ORDER BY cnt DESC"
            ).fetchall()
        ]
        enhancement_cameras = [
            {"name": r[0] or "unknown", "count": r[1]}
            for r in conn.execute(
                "SELECT camera_body, COUNT(*) as cnt FROM enhancement_plans "
                "GROUP BY camera_body ORDER BY cnt DESC"
            ).fetchall()
        ]
    except Exception:
        pass

    # Location data
    location_count = 0
    location_sources = []
    location_accepted = 0
    try:
        location_count = conn.execute("SELECT COUNT(*) FROM image_locations").fetchone()[0]
        location_sources = [
            {"name": r[0] or "unknown", "count": r[1]}
            for r in conn.execute(
                "SELECT source, COUNT(*) as cnt FROM image_locations "
                "GROUP BY source ORDER BY cnt DESC"
            ).fetchall()
        ]
        location_accepted = conn.execute("SELECT COUNT(*) FROM image_locations WHERE accepted=1").fetchone()[0]
    except Exception:
        pass

    # ── Pipeline runs ────────────────────────────────────────
    runs = [
        {"phase": r["phase"], "status": r["status"],
         "ok": r["images_processed"], "failed": r["images_failed"],
         "started": r["started_at"][:16].replace("T", " ") if r["started_at"] else ""}
        for r in conn.execute(
            "SELECT phase, status, images_processed, images_failed, started_at "
            "FROM pipeline_runs ORDER BY started_at DESC LIMIT 15"
        ).fetchall()
    ]

    # ── Recent analyses ──────────────────────────────────────
    recent = [
        {"uuid": r["image_uuid"][:8], "style": r["grading_style"],
         "alt": r["alt_text"], "time": r["analyzed_at"][:19].replace("T", " ") if r["analyzed_at"] else ""}
        for r in conn.execute(
            "SELECT image_uuid, grading_style, alt_text, analyzed_at "
            "FROM gemini_analysis WHERE raw_json != '' "
            "ORDER BY analyzed_at DESC LIMIT 8"
        ).fetchall()
    ]

    # ── Sample analysis ──────────────────────────────────────
    sample_row = conn.execute(
        "SELECT image_uuid, raw_json, analyzed_at FROM gemini_analysis "
        "WHERE raw_json IS NOT NULL AND raw_json != '' "
        "ORDER BY analyzed_at DESC LIMIT 1"
    ).fetchone()
    sample = None
    if sample_row:
        try:
            sample = {
                "uuid": sample_row["image_uuid"],
                "time": sample_row["analyzed_at"][:19].replace("T", " ") if sample_row["analyzed_at"] else "",
                "data": json.loads(sample_row["raw_json"]),
            }
        except json.JSONDecodeError:
            pass

    # ── Disk usage ───────────────────────────────────────────
    db_size = os.path.getsize(str(DB_PATH)) if DB_PATH.exists() else 0
    web_json_path = Path(__file__).resolve().parent / "web" / "data" / "photos.json"
    web_json_size = os.path.getsize(str(web_json_path)) if web_json_path.exists() else 0
    web_photo_count = 0
    if web_json_path.exists():
        try:
            web_photo_count = len(json.loads(web_json_path.read_text()))
        except Exception:
            pass

    conn.close()

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total": total,
        "analyzed": analyzed,
        "failed": failed,
        "pending": pending,
        "analysis_pct": pct(analyzed, total),
        "pixel_analyzed": pixel_analyzed,
        "pixel_pct": pct(pixel_analyzed, total),
        "categories": categories,
        "subcategories": subcategories,
        "tiers": tiers,
        "tier_coverage": tier_coverage,
        "total_rendered_bytes": total_rendered_bytes,
        "total_rendered_human": human_bytes(total_rendered_bytes),
        "total_tier_files": total_tier_files,
        "ai_variants_total": ai_variants_total,
        "variant_summary": variant_summary,
        "gcs_uploads": gcs_uploads,
        "cameras": cameras,
        "source_formats": source_formats,
        "monochrome_count": monochrome_count,
        "color_cast": color_cast,
        "color_temp": color_temp,
        "grading": grading,
        "time_of_day": time_of_day,
        "settings": settings,
        "exposure": exposure,
        "composition": composition,
        "vibes": vibes,
        "rotate_stats": rotate_stats,
        "has_edit_prompt": has_edit_prompt,
        "has_semantic_pops": has_semantic_pops,
        "curation": curation,
        "kept": kept,
        "rejected": rejected,
        "curated_total": curated_total,
        "curation_pct": pct(curated_total, total),
        "vector_count": vector_count,
        "vector_size": vector_size_human,
        "runs": runs,
        "recent": recent,
        "sample": sample,
        "db_size": human_bytes(db_size),
        "web_json_size": human_bytes(web_json_size),
        "web_photo_count": web_photo_count,
        "signals": signals,
        "exif_gps": exif_gps,
        "exif_iso": exif_iso,
        "face_images_with": face_images_with,
        "face_total": face_total,
        "top_objects": top_objects,
        "top_color_names": top_color_names,
        "aesthetic_count": aesthetic_count,
        "aesthetic_avg": aesthetic_avg,
        "aesthetic_min": aesthetic_min,
        "aesthetic_max": aesthetic_max,
        "aesthetic_labels": aesthetic_labels,
        "depth_count": depth_count,
        "depth_avg_near": depth_avg_near,
        "depth_avg_mid": depth_avg_mid,
        "depth_avg_far": depth_avg_far,
        "depth_complexity_buckets": depth_complexity_buckets,
        "scene_count": scene_count,
        "top_scenes": top_scenes,
        "scene_environments": scene_environments,
        "enhancement_count": enhancement_count,
        "enhancement_statuses": enhancement_statuses,
        "enhancement_cameras": enhancement_cameras,
        "location_count": location_count,
        "location_sources": location_sources,
        "location_accepted": location_accepted,
    }


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MADphotos Dashboard</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='45' fill='%23111'/></svg>">
<style>
  /* ═══════════════════════════════════════════════════════════
     DESIGN TOKENS — Apple Human Interface Guidelines
     ═══════════════════════════════════════════════════════════ */
  :root {
    /* ── Type scale (SF Pro) ── */
    --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", system-ui, sans-serif;
    --font-display: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", system-ui, sans-serif;
    --font-mono: "SF Mono", ui-monospace, "Cascadia Code", "Fira Code", monospace;

    --text-xs: 11px;
    --text-sm: 13px;
    --text-base: 15px;
    --text-lg: 17px;
    --text-xl: 20px;
    --text-2xl: 22px;
    --text-3xl: 28px;
    --text-4xl: 34px;

    --leading-tight: 1.2;
    --leading-normal: 1.47;
    --leading-relaxed: 1.6;

    --tracking-tight: -0.01em;
    --tracking-normal: 0;
    --tracking-wide: 0.02em;
    --tracking-caps: 0.06em;

    /* ── Spacing scale (4px base) ── */
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-5: 20px;
    --space-6: 24px;
    --space-8: 32px;
    --space-10: 40px;
    --space-12: 48px;
    --space-16: 64px;

    /* ── Radius ── */
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
    --radius-xl: 20px;
    --radius-full: 9999px;

    /* ── Shadows ── */
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-lg: 0 4px 16px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04);

    /* ── Transitions ── */
    --ease-default: cubic-bezier(0.25, 0.1, 0.25, 1);
    --duration-fast: 150ms;
    --duration-normal: 250ms;

    /* ── Apple system colors ── */
    --apple-blue: #007AFF;
    --apple-green: #34C759;
    --apple-indigo: #5856D6;
    --apple-orange: #FF9500;
    --apple-pink: #FF2D55;
    --apple-purple: #AF52DE;
    --apple-red: #FF3B30;
    --apple-teal: #5AC8FA;
    --apple-yellow: #FFCC00;
    --apple-mint: #00C7BE;
    --apple-cyan: #32ADE6;
    --apple-brown: #A2845E;

    /* ── Sidebar width ── */
    --sidebar-w: 220px;
  }

  /* ── Light theme (default) ── */
  [data-theme="light"] {
    --bg: #F5F5F7;
    --bg-secondary: #FFFFFF;
    --bg-tertiary: #F2F2F7;
    --fg: #1D1D1F;
    --fg-secondary: #3A3A3C;
    --muted: #86868B;
    --border: rgba(0,0,0,0.08);
    --border-strong: rgba(0,0,0,0.14);
    --card-bg: #FFFFFF;
    --card-hover: #FAFAFA;
    --bar-bg: rgba(0,0,0,0.06);
    --bar-fill: #1D1D1F;
    --pill-bg: #FFFFFF;
    --pill-border: rgba(0,0,0,0.10);
    --pill-hover: #F5F5F7;
    --badge-green-bg: rgba(52,199,89,0.12);
    --badge-green-fg: #248A3D;
    --badge-amber-bg: rgba(255,149,0,0.12);
    --badge-amber-fg: #C93400;
    --badge-red-bg: rgba(255,59,48,0.12);
    --badge-red-fg: #D70015;
    --json-key: #1D1D1F;
    --json-str: #6E6E73;
    --json-num: #007AFF;
    --tag-icon-bg: rgba(0,0,0,0.05);
    --hover-overlay: rgba(0,0,0,0.03);
    --sidebar-bg: #FFFFFF;
    --sidebar-active-bg: rgba(0,0,0,0.04);
    color-scheme: light;
  }

  /* ── Dark theme ── */
  [data-theme="dark"] {
    --bg: #1C1C1E;
    --bg-secondary: #2C2C2E;
    --bg-tertiary: #3A3A3C;
    --fg: #F5F5F7;
    --fg-secondary: #D1D1D6;
    --muted: #98989D;
    --border: rgba(255,255,255,0.08);
    --border-strong: rgba(255,255,255,0.14);
    --card-bg: #2C2C2E;
    --card-hover: #3A3A3C;
    --bar-bg: rgba(255,255,255,0.08);
    --bar-fill: #F5F5F7;
    --pill-bg: #2C2C2E;
    --pill-border: rgba(255,255,255,0.12);
    --pill-hover: #3A3A3C;
    --badge-green-bg: rgba(48,209,88,0.16);
    --badge-green-fg: #30D158;
    --badge-amber-bg: rgba(255,159,10,0.16);
    --badge-amber-fg: #FF9F0A;
    --badge-red-bg: rgba(255,69,58,0.16);
    --badge-red-fg: #FF453A;
    --json-key: #F5F5F7;
    --json-str: #98989D;
    --json-num: #64D2FF;
    --tag-icon-bg: rgba(255,255,255,0.08);
    --hover-overlay: rgba(255,255,255,0.04);
    --sidebar-bg: #2C2C2E;
    --sidebar-active-bg: rgba(255,255,255,0.06);
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.2);
    --shadow-md: 0 2px 8px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2);
    --shadow-lg: 0 4px 16px rgba(0,0,0,0.4), 0 2px 4px rgba(0,0,0,0.2);
    color-scheme: dark;
  }

  /* ═══ RESET ═══ */
  html { scroll-behavior: smooth; }
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font-sans);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    background: var(--bg);
    color: var(--fg);
    display: flex;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  /* ═══ HERO ═══ */
  .hero {
    position: relative;
    border-radius: var(--radius-xl);
    overflow: hidden;
    margin-bottom: var(--space-10);
    min-height: 320px;
    display: flex;
    align-items: flex-end;
  }
  .hero-mosaic {
    position: absolute; inset: 0;
  }
  .hero-mosaic img {
    width: 100%; height: 100%; object-fit: cover;
    filter: brightness(0.4) saturate(0.8);
    transition: filter 0.5s;
  }
  .hero:hover .hero-mosaic img {
    filter: brightness(0.5) saturate(0.9);
  }
  .hero-overlay {
    position: absolute; inset: 0;
    background: linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.3) 50%, rgba(0,0,0,0.1) 100%);
  }
  .hero-content {
    position: relative; z-index: 1;
    padding: var(--space-10) var(--space-8);
    max-width: 640px;
  }
  .hero-title {
    font-family: var(--font-display);
    font-size: 48px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #FFFFFF;
    margin-bottom: var(--space-1);
    line-height: 1.1;
  }
  .hero-count {
    font-family: var(--font-display);
    font-size: var(--text-xl);
    font-weight: 600;
    color: rgba(255,255,255,0.7);
    margin-bottom: var(--space-4);
    letter-spacing: -0.01em;
  }
  .hero-tagline {
    font-size: var(--text-base);
    color: rgba(255,255,255,0.85);
    line-height: var(--leading-relaxed);
    margin-bottom: var(--space-3);
  }
  .hero-mission {
    font-size: var(--text-sm);
    color: rgba(255,255,255,0.6);
    line-height: var(--leading-relaxed);
    margin-bottom: var(--space-2);
  }
  .hero-mission em {
    color: rgba(255,255,255,0.85);
    font-style: italic;
  }
  @media (max-width: 700px) {
    .hero { min-height: 260px; }
    .hero-title { font-size: 32px; }
    .hero-content { padding: var(--space-6); }
    .hero-count { font-size: var(--text-lg); }
  }
  @media (max-width: 440px) {
    .hero { min-height: 220px; }
    .hero-title { font-size: 26px; }
    .hero-content { padding: var(--space-4); }
  }

  /* ═══ SIDEBAR ═══ */
  .sidebar {
    width: var(--sidebar-w);
    min-width: var(--sidebar-w);
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border);
    padding: var(--space-5) 0;
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .sidebar .sb-title {
    font-family: var(--font-display);
    font-size: var(--text-lg);
    font-weight: 700;
    letter-spacing: var(--tracking-tight);
    padding: 0 var(--space-5) var(--space-4);
    border-bottom: 1px solid var(--border);
    margin-bottom: var(--space-2);
  }
  .sidebar a {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-5);
    color: var(--muted);
    text-decoration: none;
    font-size: var(--text-sm);
    line-height: var(--leading-tight);
    border-radius: 0;
    transition: background var(--duration-fast) var(--ease-default),
                color var(--duration-fast) var(--ease-default);
  }
  .sidebar a:hover {
    background: var(--sidebar-active-bg);
    color: var(--fg);
  }
  .sidebar a.active {
    color: var(--fg);
    font-weight: 600;
    background: var(--sidebar-active-bg);
    border-left: 3px solid var(--apple-blue);
    padding-left: calc(var(--space-5) - 3px);
  }
  .sidebar .sb-sep {
    height: 1px;
    background: var(--border);
    margin: var(--space-2) var(--space-5);
  }
  .sidebar .sb-group {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
    color: var(--muted);
    padding: var(--space-3) var(--space-5) var(--space-1);
  }
  .sidebar .sb-toggle {
    cursor: pointer;
    user-select: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .sidebar .sb-arrow {
    font-size: 10px;
    transition: transform var(--duration-fast) var(--ease-default);
  }
  .sidebar .sb-toggle.open .sb-arrow {
    transform: rotate(90deg);
  }
  .sidebar .sb-collapsible {
    overflow: hidden;
    max-height: 500px;
    transition: max-height 0.2s ease;
  }
  .sidebar .sb-collapsed {
    max-height: 0;
  }
  .sidebar .sb-bottom {
    margin-top: auto;
    padding: var(--space-3) var(--space-5);
    border-top: 1px solid var(--border);
  }
  .theme-toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
    color: var(--muted);
    cursor: pointer;
    padding: var(--space-2) 0;
    background: none;
    border: none;
    font-family: inherit;
    width: 100%;
    transition: color var(--duration-fast);
  }
  .theme-toggle:hover { color: var(--fg); }
  .theme-toggle .theme-icon { font-size: 16px; }

  /* ═══ MAIN CONTENT ═══ */
  .main-content {
    flex: 1;
    padding: var(--space-10) var(--space-8);
    max-width: 1120px;
    min-width: 0;
    margin: 0 auto;
  }

  @media (max-width: 900px) {
    body { flex-direction: column; }
    .sidebar {
      width: 100%; min-width: unset; height: auto; position: relative;
      border-right: none; border-bottom: 1px solid var(--border);
      flex-direction: row; flex-wrap: wrap; gap: 0; padding: var(--space-3);
    }
    .sidebar .sb-title { width: 100%; border-bottom: none; padding-bottom: var(--space-1); }
    .sidebar .sb-group, .sidebar .sb-sep, .sidebar .sb-bottom { display: none; }
    .sidebar a { padding: var(--space-1) var(--space-3); }
    .main-content { padding: var(--space-6); }
  }

  /* ═══ TYPOGRAPHY ═══ */
  h1 {
    font-family: var(--font-display);
    font-size: var(--text-3xl);
    font-weight: 700;
    letter-spacing: var(--tracking-tight);
    margin-bottom: var(--space-1);
  }
  .subtitle {
    color: var(--muted);
    font-size: var(--text-sm);
    margin-bottom: var(--space-10);
  }
  .live-dot {
    display: inline-block;
    width: 7px; height: 7px;
    background: var(--apple-green);
    border-radius: var(--radius-full);
    margin-right: var(--space-2);
    animation: pulse 2s ease infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.85); }
  }

  /* Section headings */
  .section-title {
    font-family: var(--font-display);
    font-size: var(--text-xl);
    font-weight: 700;
    letter-spacing: var(--tracking-tight);
    color: var(--fg);
    margin: 0 0 var(--space-5);
    padding-bottom: var(--space-3);
    border-bottom: 1px solid var(--border);
  }
  .subsection-title {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
    color: var(--muted);
    margin: var(--space-4) 0 var(--space-2);
  }
  .subsection-title:first-child { margin-top: 0; }

  /* ═══ STAT CARDS ═══ */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: var(--space-3);
    margin-bottom: var(--space-4);
  }
  .stat-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: var(--space-4) var(--space-5);
    transition: border-color var(--duration-normal) var(--ease-default),
                box-shadow var(--duration-normal) var(--ease-default);
    box-shadow: var(--shadow-sm);
  }
  .stat-card:hover { box-shadow: var(--shadow-md); }
  .stat-card.updated { border-color: var(--apple-blue); }
  .stat-card .value {
    font-family: var(--font-display);
    font-size: var(--text-3xl);
    font-weight: 700;
    letter-spacing: var(--tracking-tight);
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .stat-card .label {
    font-size: var(--text-xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
    color: var(--muted);
    margin-top: var(--space-1);
  }
  .stat-card .sub {
    font-size: var(--text-xs);
    color: var(--muted);
    margin-top: var(--space-1);
  }

  /* ═══ PROGRESS BARS ═══ */
  .progress-wrap {
    background: var(--bar-bg);
    height: 8px;
    width: 100%;
    margin: var(--space-3) 0 var(--space-2);
    border-radius: var(--radius-full);
    overflow: hidden;
    position: relative;
  }
  .progress-fill {
    background: var(--fg);
    height: 100%;
    border-radius: var(--radius-full);
    transition: width 1s var(--ease-default);
  }
  .progress-fill.green { background: var(--apple-green); }
  .progress-fill.amber { background: var(--apple-orange); }
  .progress-info {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: var(--space-1);
  }
  .progress-info .pi-label {
    font-size: var(--text-sm);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .progress-info .pi-pct {
    font-size: var(--text-sm);
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .rate {
    font-size: var(--text-xs);
    color: var(--muted);
    margin-top: var(--space-1);
  }

  /* ═══ TABLES ═══ */
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
    margin-bottom: var(--space-4);
  }
  th {
    text-align: left;
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
    color: var(--muted);
    border-bottom: 1px solid var(--border-strong);
    padding: var(--space-2) var(--space-3);
  }
  td {
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border);
  }
  .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  tr:hover td { background: var(--hover-overlay); }

  /* ═══ LAYOUT ═══ */
  .section { margin-bottom: var(--space-12); }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-8); }
  .three-col { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: var(--space-6); }
  @media (max-width: 700px) {
    .two-col, .three-col { grid-template-columns: 1fr; }
    .stats-grid { grid-template-columns: 1fr 1fr; }
    h1 { font-size: var(--text-2xl); }
    .stat-card .value { font-size: var(--text-xl); }
  }
  @media (max-width: 440px) {
    .stats-grid { grid-template-columns: 1fr; }
    .main-content { padding: var(--space-4); }
  }
  .table-wrap {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin-bottom: var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--border);
    background: var(--card-bg);
  }
  .table-wrap table {
    min-width: 500px;
    margin-bottom: 0;
  }
  .table-wrap td:last-child, .table-wrap th:last-child { padding-right: var(--space-4); }
  .table-wrap td:first-child, .table-wrap th:first-child { padding-left: var(--space-4); }

  /* ═══ HF-STYLE TAGS (pills with category icons) ═══ */
  .tag-row {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
    margin: var(--space-2) 0;
  }
  .tag {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    background: var(--pill-bg);
    border: 1px solid var(--pill-border);
    border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-xs);
    line-height: 1;
    white-space: nowrap;
    transition: background var(--duration-fast), border-color var(--duration-fast);
    cursor: default;
  }
  .tag:hover {
    background: var(--pill-hover);
    border-color: var(--border-strong);
  }
  .tag .tag-icon {
    flex-shrink: 0;
    line-height: 0;
    display: inline-flex;
    align-items: center;
  }
  .tag .tag-icon svg {
    width: 14px;
    height: 14px;
  }
  .tag .tag-label { font-weight: 500; color: var(--fg-secondary); }
  .tag .tag-count {
    font-weight: 400;
    color: var(--muted);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
  }

  /* Color dot inside tags (for dominant colors) */
  .tag .tag-cdot {
    display: inline-block;
    width: 14px; height: 14px;
    border-radius: var(--radius-full);
    border: 1px solid var(--border-strong);
    flex-shrink: 0;
  }

  /* ═══ VARIANT CARDS ═══ */
  .variant-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-5);
    margin-bottom: var(--space-3);
    box-shadow: var(--shadow-sm);
  }
  .variant-card .variant-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: var(--space-2);
  }
  .variant-card .variant-name {
    font-weight: 600;
    font-size: var(--text-sm);
  }
  .variant-card .variant-counts {
    font-size: var(--text-xs);
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .variant-bar {
    height: 6px;
    background: var(--bar-bg);
    border-radius: var(--radius-full);
    display: flex;
    overflow: hidden;
  }
  .variant-bar .seg-ok { background: var(--apple-green); transition: width 1s; border-radius: var(--radius-full) 0 0 var(--radius-full); }
  .variant-bar .seg-fail { background: var(--apple-red); transition: width 1s; }
  .variant-bar .seg-filtered { background: var(--muted); transition: width 1s; }
  .mini-legend {
    display: flex;
    gap: var(--space-4);
    font-size: var(--text-xs);
    color: var(--muted);
    margin-top: var(--space-2);
  }
  .mini-legend span { display: flex; align-items: center; gap: var(--space-1); }
  .mini-legend span::before {
    content: '';
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: var(--radius-full);
  }
  .mini-legend .l-ok::before { background: var(--apple-green); }
  .mini-legend .l-fail::before { background: var(--apple-red); }
  .mini-legend .l-filtered::before { background: var(--muted); }

  /* ═══ MODEL CARDS ═══ */
  .model-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-3);
    margin: var(--space-3) 0;
  }
  @media (max-width: 600px) {
    .model-cards { grid-template-columns: 1fr; }
  }
  .model-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-5);
    box-shadow: var(--shadow-sm);
  }
  .model-card .mc-name { font-weight: 700; font-size: var(--text-base); }
  .model-card .mc-dim { font-size: var(--text-xs); color: var(--muted); margin-top: 2px; font-family: var(--font-mono); }
  .model-card .mc-desc { font-size: var(--text-xs); color: var(--muted); margin-top: var(--space-2); line-height: var(--leading-relaxed); }

  /* ═══ BADGES ═══ */
  .badge {
    display: inline-flex;
    align-items: center;
    font-size: var(--text-xs);
    font-weight: 600;
    padding: 2px var(--space-2);
    border-radius: var(--radius-sm);
    gap: var(--space-1);
  }
  .badge.done { background: var(--badge-green-bg); color: var(--badge-green-fg); }
  .badge.partial { background: var(--badge-amber-bg); color: var(--badge-amber-fg); }
  .badge.empty { background: var(--badge-red-bg); color: var(--badge-red-fg); }

  /* ═══ DISK / STORAGE ═══ */
  .disk-row {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
    margin: var(--space-3) 0;
  }
  .disk-item {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-3) var(--space-4);
    box-shadow: var(--shadow-sm);
  }
  .disk-item .di-val {
    font-family: var(--font-display);
    font-weight: 700;
    font-size: var(--text-lg);
  }
  .disk-item .di-label { font-size: var(--text-xs); color: var(--muted); }

  /* ═══ SAMPLE JSON ═══ */
  .sample-block {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-5);
    overflow-x: auto;
    max-height: 500px;
    overflow-y: auto;
  }
  .sample-block pre {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    line-height: var(--leading-relaxed);
    white-space: pre-wrap;
    word-break: break-word;
  }
  .sample-header { font-size: var(--text-xs); color: var(--muted); margin-bottom: var(--space-3); }
  .json-key { color: var(--json-key); font-weight: 600; }
  .json-str { color: var(--json-str); }
  .json-num { color: var(--json-num); font-weight: 600; }
  .json-bool { color: var(--apple-purple); font-weight: 600; }
  .json-null { color: var(--muted); }

  /* ═══ DEPTH BAR ═══ */
  .depth-bar {
    display: flex;
    height: 24px;
    border-radius: var(--radius-sm);
    overflow: hidden;
    margin: var(--space-2) 0;
    box-shadow: var(--shadow-sm);
  }
  .depth-bar .db-near { background: var(--apple-blue); }
  .depth-bar .db-mid { background: var(--apple-teal); }
  .depth-bar .db-far { background: var(--apple-indigo); }
  .depth-bar > div {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 600;
    color: white;
    min-width: 32px;
    transition: width 1s var(--ease-default);
  }
  .depth-legend {
    display: flex;
    gap: var(--space-4);
    font-size: var(--text-xs);
    color: var(--muted);
    margin-top: var(--space-1);
  }
  .depth-legend span { display: flex; align-items: center; gap: var(--space-1); }
  .depth-legend span::before {
    content: '';
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 2px;
  }
  .depth-legend .dl-near::before { background: var(--apple-blue); }
  .depth-legend .dl-mid::before { background: var(--apple-teal); }
  .depth-legend .dl-far::before { background: var(--apple-indigo); }

  /* ═══ CAMERA TABLE ═══ */
  .camera-table td:first-child { font-weight: 600; }
  .wb-pos { color: var(--apple-red); }
  .wb-neg { color: var(--apple-blue); }
  .wb-zero { color: var(--muted); }

  /* ═══ FOOTER ═══ */
  footer {
    margin-top: var(--space-16);
    padding-top: var(--space-4);
    border-top: 1px solid var(--border);
    font-size: var(--text-xs);
    color: var(--muted);
  }
  footer a { color: var(--muted); text-decoration: none; }
  footer a:hover { color: var(--fg); }
</style>
</head>
<body>

<nav class="sidebar" id="sidebar">
  <div class="sb-title">MADphotos</div>
  <a href="/readme">README</a>
  <a href="/" class="active">State</a>
  <a href="/journal">Journal de Bord</a>
  <a href="/instructions">System Instructions</a>
  <div class="sb-sep"></div>
  <div class="sb-group">Experiments</div>
  <a href="/drift">Drift</a>
  <a href="/blind-test">Blind Test</a>
  <a href="/mosaics">Mosaics</a>
  <div class="sb-sep"></div>
  <div class="sb-group sb-toggle" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('sb-collapsed')">
    Dashboard <span class="sb-arrow">&#9656;</span>
  </div>
  <div class="sb-collapsible sb-collapsed">
    <a href="#sec-gemini">Gemini Progress</a>
    <a href="#sec-cameras">Camera Fleet</a>
    <a href="#sec-signals">Signal Extraction</a>
    <a href="#sec-advanced">Advanced Signals</a>
    <a href="#sec-pixel">Pixel Analysis</a>
    <a href="#sec-vectors">Vector Store</a>
    <a href="#sec-insights">Gemini Insights</a>
    <a href="#sec-categories">Categories</a>
    <a href="#sec-tiers">Render Tiers</a>
    <a href="#sec-variants">Imagen Variants</a>
    <a href="#sec-storage">Storage</a>
    <a href="#sec-runs">Pipeline Runs</a>
    <a href="#sec-sample">Sample Output</a>
  </div>
  <div class="sb-bottom">
    <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">
      <span class="theme-icon" id="themeIcon">&#9790;</span>
      <span id="themeLabel">Dark Mode</span>
    </button>
  </div>
</nav>

<div class="main-content">

<!-- ═══ HERO LANDING ═══ -->
<div class="hero">
  <div class="hero-mosaic">
    <img src="/mosaic-hero" alt="9,011 photographs arranged by brightness" loading="eager">
    <div class="hero-overlay"></div>
  </div>
  <div class="hero-content">
    <h1 class="hero-title">MADphotos</h1>
    <p class="hero-count"><span id="hero-count">9,011</span> photographs</p>
    <p class="hero-tagline">Shot over a decade on Leica rangefinders, a monochrome sensor with no Bayer filter, scanned analog film, and pocket action cameras. Most have never been seen by anyone.</p>
    <p class="hero-mission">The mission: treat every single image as if it deserves a curator, a critic, and an editor. Not batch processing &mdash; <em>per-image intelligence</em>. An AI studies the exposure, the composition, the mood, the color. It writes editing instructions unique to that frame. Then another AI executes them. From that improved base, style variants bloom.</p>
    <p class="hero-mission">Everything tracked in one database. Every signal extractable. Every image searchable by what it <em>means</em>, not just what it&rsquo;s named.</p>
  </div>
</div>

<p class="subtitle" id="subtitle">System Dashboard</p>

<!-- ═══ TOP CARDS ═══ -->
<div class="stats-grid" id="top-cards">
  <div class="stat-card" id="card-total">
    <div class="value" id="val-total">&mdash;</div>
    <div class="label">Photographs</div>
    <div class="sub" id="sub-formats"></div>
  </div>
  <div class="stat-card" id="card-rendered">
    <div class="value" id="val-rendered">&mdash;</div>
    <div class="label" id="lbl-rendered">Tier Files</div>
    <div class="sub" id="sub-rendered"></div>
  </div>
  <div class="stat-card" id="card-gemini">
    <div class="value" id="val-gemini">&mdash;</div>
    <div class="label">Gemini AI</div>
    <div class="sub" id="sub-gemini"></div>
  </div>
  <div class="stat-card" id="card-pixel">
    <div class="value" id="val-pixel">&mdash;</div>
    <div class="label">Pixel Analysis</div>
    <div class="sub" id="sub-pixel"></div>
  </div>
  <div class="stat-card" id="card-vectors">
    <div class="value" id="val-vectors">&mdash;</div>
    <div class="label">Vector Triples</div>
    <div class="sub" id="sub-vectors"></div>
  </div>
  <div class="stat-card" id="card-variants">
    <div class="value" id="val-variants">&mdash;</div>
    <div class="label">AI Edits</div>
    <div class="sub" id="sub-variants"></div>
  </div>
  <div class="stat-card" id="card-curation">
    <div class="value" id="val-curation">&mdash;</div>
    <div class="label">Curated</div>
    <div class="sub" id="sub-curation"></div>
  </div>
  <div class="stat-card" id="card-gcs">
    <div class="value" id="val-gcs">&mdash;</div>
    <div class="label">GCS Uploads</div>
    <div class="sub" id="sub-gcs"></div>
  </div>
</div>

<!-- ═══ GEMINI PROGRESS ═══ -->
<div class="section" id="sec-gemini">
  <div class="section-title"><span class="live-dot" id="live-dot"></span>Gemini Analysis</div>
  <div class="progress-info">
    <span class="pi-label" id="progress-label">&mdash; / &mdash;</span>
    <span class="pi-pct" id="progress-pct"></span>
  </div>
  <div class="progress-wrap">
    <div class="progress-fill" id="progress-fill" style="width:0%"></div>
  </div>
  <div class="rate" id="rate-info"></div>
  <div class="table-wrap"><table>
    <tr><th>Status</th><th class="num">Count</th></tr>
    <tr><td>Completed</td><td class="num" id="st-done">&mdash;</td></tr>
    <tr><td>Failed</td><td class="num" id="st-fail">&mdash;</td></tr>
    <tr><td>Pending</td><td class="num" id="st-pend">&mdash;</td></tr>
  </table></div>
  <div style="font-size:var(--text-xs);color:var(--muted);">
    <span id="gemini-extras"></span>
  </div>
</div>

<!-- ═══ CAMERA FLEET ═══ -->
<div class="section" id="sec-cameras">
  <div class="section-title">Camera Fleet</div>
  <div class="table-wrap"><table class="camera-table">
    <thead>
      <tr>
        <th>Camera</th>
        <th class="num">Images</th>
        <th>Medium</th>
        <th>Film</th>
        <th class="num">Lum</th>
        <th class="num">WB Red</th>
        <th class="num">WB Blue</th>
        <th class="num">Noise</th>
        <th class="num">Shadow%</th>
      </tr>
    </thead>
    <tbody id="tbl-cameras"></tbody>
  </table></div>
</div>

<!-- ═══ SIGNAL EXTRACTION ═══ -->
<div class="section" id="sec-signals">
  <div class="section-title">Signal Extraction</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Phase</th><th class="num">Rows</th><th class="num">Images</th><th>Status</th></tr></thead>
    <tbody id="tbl-signals"></tbody>
  </table></div>
  <div class="two-col" style="margin-top:var(--space-4);">
    <div>
      <div class="subsection-title">Top Detected Objects</div>
      <div id="pills-objects" class="tag-row"></div>
    </div>
    <div>
      <div class="subsection-title">Dominant Colors</div>
      <div id="pills-domcolors" class="tag-row"></div>
    </div>
  </div>
</div>

<!-- ═══ ADVANCED SIGNALS (NEW) ═══ -->
<div class="section" id="sec-advanced">
  <div class="section-title">Advanced Signals</div>

  <div class="two-col">
    <!-- Depth Estimation -->
    <div>
      <div class="subsection-title">Depth Estimation</div>
      <div style="font-size:var(--text-sm);color:var(--muted);margin-bottom:var(--space-2);">
        <span id="depth-count"></span> images analyzed
      </div>
      <div class="depth-bar" id="depth-bar">
        <div class="db-near" id="db-near" style="width:33%">Near</div>
        <div class="db-mid" id="db-mid" style="width:33%">Mid</div>
        <div class="db-far" id="db-far" style="width:34%">Far</div>
      </div>
      <div class="depth-legend">
        <span class="dl-near">Near</span>
        <span class="dl-mid">Mid-range</span>
        <span class="dl-far">Far</span>
      </div>
      <div class="subsection-title" style="margin-top:var(--space-3);">Complexity</div>
      <div id="pills-depth" class="tag-row"></div>
    </div>

    <!-- Scene Classification -->
    <div>
      <div class="subsection-title">Scene Classification</div>
      <div style="font-size:var(--text-sm);color:var(--muted);margin-bottom:var(--space-2);">
        <span id="scene-count"></span> images classified
      </div>
      <div id="pills-scenes" class="tag-row"></div>
      <div class="subsection-title" style="margin-top:var(--space-3);">Environment</div>
      <div id="pills-environments" class="tag-row"></div>
    </div>
  </div>

  <div class="two-col" style="margin-top:var(--space-6);">
    <!-- Enhancement -->
    <div>
      <div class="subsection-title">Enhancement Engine</div>
      <div style="font-size:var(--text-sm);color:var(--muted);margin-bottom:var(--space-2);">
        <span id="enhance-count"></span> images enhanced
      </div>
      <div id="pills-enhance" class="tag-row"></div>
    </div>

    <!-- Locations -->
    <div>
      <div class="subsection-title">Locations</div>
      <div style="font-size:var(--text-sm);color:var(--muted);margin-bottom:var(--space-2);">
        <span id="location-count"></span> images with location &middot; <span id="exif-gps-count"></span> GPS from EXIF
      </div>
      <div id="pills-locations" class="tag-row"></div>
    </div>
  </div>
</div>

<!-- ═══ PIXEL ANALYSIS ═══ -->
<div class="section" id="sec-pixel">
  <div class="section-title">Pixel Analysis</div>
  <div class="two-col">
    <div>
      <div class="subsection-title">Color Cast</div>
      <div id="pills-cast" class="tag-row"></div>
    </div>
    <div>
      <div class="subsection-title">Color Temperature</div>
      <div id="pills-temp" class="tag-row"></div>
    </div>
  </div>
</div>

<!-- ═══ VECTOR STORE ═══ -->
<div class="section" id="sec-vectors">
  <div class="section-title">Vector Store</div>
  <div id="vector-info" style="font-size:var(--text-sm);color:var(--muted);margin-bottom:var(--space-3);"></div>
  <div class="model-cards">
    <div class="model-card">
      <div class="mc-name">DINOv2</div>
      <div class="mc-dim">768 dimensions</div>
      <div class="mc-desc">Self-supervised vision transformer. Sees composition, texture, spatial layout. The artistic eye.</div>
    </div>
    <div class="model-card">
      <div class="mc-name">SigLIP</div>
      <div class="mc-dim">768 dimensions</div>
      <div class="mc-desc">Multimodal image-text model. Sees meaning, enables text search. The semantic brain.</div>
    </div>
    <div class="model-card">
      <div class="mc-name">CLIP</div>
      <div class="mc-dim">512 dimensions</div>
      <div class="mc-desc">Subject matching model. Finds duplicates and similar scenes. The pattern matcher.</div>
    </div>
  </div>
</div>

<!-- ═══ GEMINI INSIGHTS ═══ -->
<div class="section" id="sec-insights">
  <div class="section-title">Gemini Insights</div>
  <div class="three-col">
    <div>
      <div class="subsection-title">Grading</div>
      <div id="pills-grading" class="tag-row"></div>
    </div>
    <div>
      <div class="subsection-title">Time of Day</div>
      <div id="pills-time" class="tag-row"></div>
    </div>
    <div>
      <div class="subsection-title">Setting</div>
      <div id="pills-setting" class="tag-row"></div>
    </div>
  </div>
  <div class="three-col" style="margin-top:var(--space-4);">
    <div>
      <div class="subsection-title">Exposure</div>
      <div id="pills-exposure" class="tag-row"></div>
    </div>
    <div>
      <div class="subsection-title">Composition</div>
      <div id="pills-composition" class="tag-row"></div>
    </div>
    <div>
      <div class="subsection-title">Rotation</div>
      <div id="pills-rotate" class="tag-row"></div>
    </div>
  </div>
  <div style="margin-top:var(--space-4);">
    <div class="subsection-title">Top Vibes</div>
    <div id="pills-vibes" class="tag-row"></div>
  </div>
</div>

<!-- ═══ CATEGORIES / SUBCATEGORIES ═══ -->
<div class="section two-col" id="sec-categories">
  <div>
    <div class="subsection-title">Categories</div>
    <div id="pills-cats" class="tag-row"></div>
  </div>
  <div>
    <div class="subsection-title">By Camera</div>
    <div id="pills-subs" class="tag-row"></div>
  </div>
</div>

<!-- ═══ RENDER TIERS ═══ -->
<div class="section" id="sec-tiers">
  <div class="section-title">Render Tiers</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Tier / Format</th><th class="num">Files</th><th class="num">Size</th></tr></thead>
    <tbody id="tbl-tiers"></tbody>
  </table></div>
</div>

<!-- ═══ IMAGEN VARIANTS ═══ -->
<div class="section" id="sec-variants">
  <div class="section-title">Imagen Variant Generation</div>
  <div id="variant-cards"></div>
  <div class="mini-legend">
    <span class="l-ok">Success</span>
    <span class="l-fail">Failed</span>
    <span class="l-filtered">Filtered</span>
  </div>
</div>

<!-- ═══ DISK USAGE ═══ -->
<div class="section" id="sec-storage">
  <div class="section-title">Storage</div>
  <div id="disk-info" class="disk-row"></div>
</div>

<!-- ═══ PIPELINE RUNS ═══ -->
<div class="section" id="sec-runs">
  <div class="section-title">Pipeline Runs</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Phase</th><th>Status</th><th class="num">OK</th><th class="num">Failed</th><th>Started</th></tr></thead>
    <tbody id="tbl-runs"></tbody>
  </table></div>
</div>

<!-- ═══ SAMPLE ANALYSIS ═══ -->
<div class="section" id="sec-sample">
  <div class="section-title">Sample Analysis</div>
  <div id="sample-meta" class="sample-header"></div>
  <div class="sample-block">
    <pre id="sample-json">Loading...</pre>
  </div>
</div>

<footer>
  MADphotos &mdash; <span id="footer-ts"></span> &mdash;
  <a href="/journal">Journal de Bord</a> &mdash;
  <a href="https://github.com/LAEH/MADphotos">github.com/LAEH/MADphotos</a>
</footer>

</div><!-- /.main-content -->

<script>
(function() {
  var POLL = %%POLL_MS%%;
  var API  = "%%API_URL%%";
  var prev = null;
  var prevTime = null;

  /* ── Theme toggle ── */
  function getTheme() {
    return localStorage.getItem('mad-theme') || 'light';
  }
  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    var icon = document.getElementById('themeIcon');
    var label = document.getElementById('themeLabel');
    if (icon) icon.textContent = t === 'dark' ? '\u2600' : '\u263E';
    if (label) label.textContent = t === 'dark' ? 'Light Mode' : 'Dark Mode';
  }
  window.toggleTheme = function() {
    var t = getTheme() === 'dark' ? 'light' : 'dark';
    localStorage.setItem('mad-theme', t);
    applyTheme(t);
  };
  applyTheme(getTheme());

  /* ── Helpers ── */
  function fmt(n) { return n != null ? n.toLocaleString() : "\u2014"; }
  function el(id) { return document.getElementById(id); }

  function flash(id) {
    var e = el(id);
    if (!e) return;
    e.classList.add("updated");
    setTimeout(function() { e.classList.remove("updated"); }, 1200);
  }

  function rows(data, cols) {
    return data.map(function(r) {
      return "<tr>" + cols.map(function(c) {
        var cls = c.cls ? ' class="' + c.cls + '"' : "";
        var v = typeof c.fn === "function" ? c.fn(r) : r[c.key];
        if (typeof v === "number") v = fmt(v);
        return "<td" + cls + ">" + (v || "\u2014") + "</td>";
      }).join("") + "</tr>";
    }).join("\n");
  }

  function badge(pct, total) {
    if (total === 0) return '<span class="badge empty">not started</span>';
    if (pct >= 100) return '<span class="badge done">complete</span>';
    if (pct > 0) return '<span class="badge partial">' + pct.toFixed(1) + '%</span>';
    return '<span class="badge empty">pending</span>';
  }

  /* ── SVG icon map ── */
  var IC = {
    camera:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>',
    scene:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 00-3-3.87M9 21v-2a4 4 0 00-4-4H3"/><path d="M1 21h22"/><path d="M12 2l3 7h-6l3-7z"/><path d="M7 10l-3 5"/><path d="M17 10l3 5"/></svg>',
    home:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>',
    depth:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2"/><path d="M7 7h10M9 12h6M11 17h2"/></svg>',
    pin:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 1118 0z"/><circle cx="12" cy="10" r="3"/></svg>',
    palette: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r="0.5" fill="currentColor"/><circle cx="17.5" cy="10.5" r="0.5" fill="currentColor"/><circle cx="8.5" cy="7.5" r="0.5" fill="currentColor"/><circle cx="6.5" cy="12" r="0.5" fill="currentColor"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.4-.47 1.4-1.17 0-.31-.13-.6-.34-.82A1.2 1.2 0 0112.72 19H14a8 8 0 008-8c0-4.4-4.5-9-10-9z"/></svg>',
    sun:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
    star:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
    sunset:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 18a5 5 0 00-10 0"/><line x1="12" y1="9" x2="12" y2="2"/><line x1="4.22" y1="10.22" x2="5.64" y2="11.64"/><line x1="1" y1="18" x2="3" y2="18"/><line x1="21" y1="18" x2="23" y2="18"/><line x1="18.36" y1="11.64" x2="19.78" y2="10.22"/><line x1="23" y1="22" x2="1" y2="22"/></svg>',
    bulb:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6M10 22h4"/><path d="M12 2a7 7 0 00-4 12.7V17h8v-2.3A7 7 0 0012 2z"/></svg>',
    frame:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="7" y="7" width="10" height="10"/></svg>',
    sparkle: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z"/></svg>',
    rotate:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>',
    film:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>',
    box:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
    eye:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
  };

  function tags(data, containerId, iconKey) {
    var container = el(containerId);
    if (!container) return;
    if (!data || !data.length) {
      container.innerHTML = '<span style="color:var(--muted);font-size:var(--text-xs)">No data</span>';
      return;
    }
    var svg = IC[iconKey] || IC.eye;
    container.innerHTML = data.map(function(r) {
      var label = r.name || r.value || "\u2014";
      return '<div class="tag">' +
        '<span class="tag-icon">' + svg + '</span>' +
        '<span class="tag-label">' + label + '</span>' +
        '<span class="tag-count">' + fmt(r.count) + '</span>' +
        '</div>';
    }).join("");
  }

  /* Color dots tag (for dominant colors) */
  function colorTags(data, containerId) {
    var container = el(containerId);
    if (!container) return;
    if (!data || !data.length) {
      container.innerHTML = '<span style="color:var(--muted);font-size:var(--text-xs)">No data</span>';
      return;
    }
    container.innerHTML = data.map(function(c) {
      var hex = c.hex || '#999';
      return '<div class="tag">' +
        '<span class="tag-cdot" style="background:' + hex + '"></span>' +
        '<span class="tag-count">' + fmt(c.count) + '</span>' +
        '</div>';
    }).join("");
  }

  /* ════════════════════════════════════════════════════════════
     UPDATE — main data binding
     ════════════════════════════════════════════════════════════ */
  function update(d) {
    el("subtitle").innerHTML =
      '<span class="live-dot"></span>System Dashboard \u2014 ' + d.timestamp;
    el("footer-ts").textContent = d.timestamp;

    /* ── Top cards ── */
    el("val-total").textContent = fmt(d.total);
    var fmtStr = d.source_formats ? d.source_formats.map(function(f) { return f.name + ": " + fmt(f.count); }).join(" \u00B7 ") : "";
    el("sub-formats").textContent = fmtStr;

    el("val-rendered").textContent = fmt(d.total_tier_files);
    el("sub-rendered").textContent = d.total_rendered_human;

    el("val-gemini").textContent = fmt(d.analyzed);
    el("sub-gemini").innerHTML = d.analysis_pct.toFixed(1) + '% \u2014 ' + badge(d.analysis_pct, d.analyzed);

    el("val-pixel").textContent = fmt(d.pixel_analyzed);
    el("sub-pixel").innerHTML = d.pixel_pct.toFixed(1) + '% \u2014 ' + badge(d.pixel_pct, d.pixel_analyzed);

    el("val-vectors").textContent = fmt(d.vector_count);
    el("sub-vectors").textContent = d.vector_size + " \u00B7 3 models";

    el("val-variants").textContent = fmt(d.ai_variants_total);
    var vtypes = d.variant_summary ? d.variant_summary.map(function(v) { return v.type + ": " + v.ok; }).join(" \u00B7 ") : "";
    el("sub-variants").textContent = vtypes;

    el("val-curation").textContent = d.curation_pct.toFixed(0) + "%";
    el("sub-curation").textContent = fmt(d.kept) + " kept \u00B7 " + fmt(d.rejected) + " rejected";

    el("val-gcs").textContent = fmt(d.gcs_uploads);
    el("sub-gcs").textContent = d.gcs_uploads > 0 ? "synced" : "not started";

    if (prev && d.analyzed !== prev.analyzed) flash("card-gemini");

    /* ── Gemini progress ── */
    el("progress-fill").style.width = d.analysis_pct + "%";
    el("progress-label").textContent = fmt(d.analyzed) + " / " + fmt(d.total);
    el("progress-pct").textContent = d.analysis_pct.toFixed(1) + "%";

    var now = Date.now();
    if (prev && prevTime && d.analyzed > prev.analyzed) {
      var dt = (now - prevTime) / 1000;
      var dn = d.analyzed - prev.analyzed;
      var rate = dn / dt * 60;
      var remaining = d.pending;
      var eta = remaining / (dn / dt);
      var etaH = Math.floor(eta / 3600);
      var etaM = Math.floor((eta % 3600) / 60);
      el("rate-info").textContent =
        rate.toFixed(1) + " img/min \u2014 ~" + etaH + "h " + etaM + "m remaining";
    }

    el("st-done").textContent = fmt(d.analyzed);
    el("st-fail").textContent = fmt(d.failed);
    el("st-pend").textContent = fmt(d.pending);

    var extras = [];
    if (d.has_edit_prompt) extras.push(fmt(d.has_edit_prompt) + " edit prompts");
    if (d.has_semantic_pops) extras.push(fmt(d.has_semantic_pops) + " semantic pops");
    el("gemini-extras").textContent = extras.join(" \u00B7 ");

    /* ── Camera fleet ── */
    el("tbl-cameras").innerHTML = rows(d.cameras, [
      {key: "body"},
      {key: "count", cls: "num"},
      {key: "medium"},
      {key: "film"},
      {key: "luminance", cls: "num"},
      {fn: function(r) {
        var cls = r.wb_r > 0.05 ? "wb-pos" : r.wb_r < -0.05 ? "wb-neg" : "wb-zero";
        return '<span class="' + cls + '">' + (r.wb_r > 0 ? "+" : "") + r.wb_r.toFixed(3) + '</span>';
      }, cls: "num"},
      {fn: function(r) {
        var cls = r.wb_b < -0.05 ? "wb-neg" : r.wb_b > 0.05 ? "wb-pos" : "wb-zero";
        return '<span class="' + cls + '">' + (r.wb_b > 0 ? "+" : "") + r.wb_b.toFixed(3) + '</span>';
      }, cls: "num"},
      {key: "noise", cls: "num"},
      {fn: function(r) { return r.shadow.toFixed(1) + "%"; }, cls: "num"}
    ]);

    /* ── Signal extraction ── */
    if (d.signals) {
      var sigNames = {
        'exif_metadata': 'EXIF Metadata',
        'dominant_colors': 'Dominant Colors (K-means LAB)',
        'face_detections': 'Face Detection (YuNet)',
        'object_detections': 'Object Detection (YOLOv8)',
        'image_hashes': 'Hashes + Quality'
      };
      var sigOrder = ['exif_metadata', 'dominant_colors', 'face_detections', 'object_detections', 'image_hashes'];
      var sigHtml = sigOrder.map(function(key) {
        var s = d.signals[key] || {rows: 0, images: 0};
        var completed = s.processed || s.images;
        var pctVal = d.total > 0 ? (completed / d.total * 100) : 0;
        var statusBadge = completed >= d.total ? '<span class="badge done">complete</span>' :
                          completed > 0 ? '<span class="badge partial">' + pctVal.toFixed(0) + '%</span>' :
                          '<span class="badge empty">pending</span>';
        var extra = '';
        if (key === 'exif_metadata' && d.exif_gps) extra = ' (' + fmt(d.exif_gps) + ' with GPS)';
        if (key === 'face_detections') extra = ' \u2014 ' + fmt(d.face_total) + ' faces in ' + fmt(s.images) + ' images';
        if (key === 'object_detections') extra = ' \u2014 ' + fmt(s.images) + ' images with objects';
        return '<tr><td>' + sigNames[key] + '</td><td class="num">' + fmt(s.rows) + '</td><td class="num">' + fmt(completed) + extra + '</td><td>' + statusBadge + '</td></tr>';
      }).join('');
      el('tbl-signals').innerHTML = sigHtml;
    }

    /* Objects & dominant colors */
    tags(d.top_objects, 'pills-objects', 'box');
    colorTags(d.top_color_names, 'pills-domcolors');

    /* ── Advanced Signals ── */
    /* Depth */
    el("depth-count").textContent = fmt(d.depth_count);
    if (d.depth_avg_near || d.depth_avg_mid || d.depth_avg_far) {
      el("db-near").style.width = d.depth_avg_near + "%";
      el("db-near").textContent = d.depth_avg_near + "%";
      el("db-mid").style.width = d.depth_avg_mid + "%";
      el("db-mid").textContent = d.depth_avg_mid + "%";
      el("db-far").style.width = d.depth_avg_far + "%";
      el("db-far").textContent = d.depth_avg_far + "%";
    }
    tags(d.depth_complexity_buckets, 'pills-depth', 'depth');

    /* Scenes */
    el("scene-count").textContent = fmt(d.scene_count);
    tags(d.top_scenes, 'pills-scenes', 'scene');
    tags(d.scene_environments, 'pills-environments', 'home');

    /* Enhancement */
    el("enhance-count").textContent = fmt(d.enhancement_count);
    tags(d.enhancement_cameras, 'pills-enhance', 'camera');

    /* Locations */
    el("location-count").textContent = fmt(d.location_count);
    el("exif-gps-count").textContent = fmt(d.exif_gps);
    tags(d.location_sources, 'pills-locations', 'pin');

    /* ── Pixel analysis — HF-style tags ── */
    tags(d.color_cast, 'pills-cast', 'palette');
    tags(d.color_temp, 'pills-temp', 'sun');

    /* ── Vector store ── */
    el("vector-info").innerHTML =
      fmt(d.vector_count) + ' images \u00D7 3 models \u2014 ' + d.vector_size + ' on disk' +
      (d.vector_count >= d.total ? ' \u2014 <span class="badge done">complete</span>' :
       d.vector_count > 0 ? ' \u2014 <span class="badge partial">' + (d.vector_count / d.total * 100).toFixed(1) + '%</span>' :
       ' \u2014 <span class="badge empty">not started</span>');

    /* ── Gemini insights ── */
    tags(d.grading, "pills-grading", "star");
    tags(d.time_of_day, "pills-time", "sunset");
    tags(d.settings, "pills-setting", "scene");
    tags(d.exposure, "pills-exposure", "bulb");
    tags(d.composition, "pills-composition", "frame");
    tags(d.vibes, "pills-vibes", "sparkle");
    tags(d.rotate_stats.map(function(r) { return {name: r.value, count: r.count}; }), "pills-rotate", "rotate");

    /* ── Categories ── */
    tags(d.categories, "pills-cats", "camera");
    tags(d.subcategories, "pills-subs", "film");

    /* ── Render tiers ── */
    el("tbl-tiers").innerHTML = d.tiers.map(function(t) {
      return "<tr><td>" + t.name + "</td><td class='num'>" + fmt(t.count) + "</td><td class='num'>" + t.size_human + "</td></tr>";
    }).join("\n");

    /* ── Variant cards ── */
    var vcHtml = "";
    if (d.variant_summary && d.variant_summary.length) {
      d.variant_summary.forEach(function(v) {
        var okW = d.total > 0 ? (v.ok / d.total * 100) : 0;
        var failW = d.total > 0 ? (v.fail / d.total * 100) : 0;
        var filtW = d.total > 0 ? (v.filtered / d.total * 100) : 0;
        vcHtml += '<div class="variant-card">' +
          '<div class="variant-header">' +
          '<span class="variant-name">' + v.type + '</span>' +
          '<span class="variant-counts">' + fmt(v.ok) + ' ok / ' + fmt(v.fail) + ' fail / ' + fmt(v.filtered) + ' filtered \u2014 ' + v.pct.toFixed(1) + '%</span>' +
          '</div>' +
          '<div class="variant-bar">' +
          '<div class="seg-ok" style="width:' + okW + '%"></div>' +
          '<div class="seg-fail" style="width:' + failW + '%"></div>' +
          '<div class="seg-filtered" style="width:' + filtW + '%"></div>' +
          '</div></div>';
      });
    } else {
      vcHtml = '<span style="color:var(--muted);font-size:var(--text-sm)">No variants generated yet</span>';
    }
    el("variant-cards").innerHTML = vcHtml;

    /* ── Disk / Storage ── */
    var diskHtml = '';
    diskHtml += '<div class="disk-item"><div class="di-val">' + d.total_rendered_human + '</div><div class="di-label">Rendered tiers</div></div>';
    diskHtml += '<div class="disk-item"><div class="di-val">' + d.db_size + '</div><div class="di-label">Database</div></div>';
    diskHtml += '<div class="disk-item"><div class="di-val">' + d.vector_size + '</div><div class="di-label">Vectors (LanceDB)</div></div>';
    if (d.web_photo_count > 0) {
      diskHtml += '<div class="disk-item"><div class="di-val">' + d.web_json_size + '</div><div class="di-label">Web gallery (' + fmt(d.web_photo_count) + ' photos)</div></div>';
    }
    el("disk-info").innerHTML = diskHtml;

    /* ── Pipeline runs ── */
    el("tbl-runs").innerHTML = rows(d.runs, [
      {key: "phase"}, {key: "status"}, {key: "ok", cls: "num"},
      {key: "failed", cls: "num"}, {key: "started"}
    ]);

    /* ── Sample JSON ── */
    var sampleEl = el("sample-json");
    var sampleMeta = el("sample-meta");
    if (d.sample && d.sample.data) {
      sampleMeta.textContent = d.sample.uuid + " \u2014 analyzed " + d.sample.time;
      sampleEl.innerHTML = syntaxHighlight(JSON.stringify(d.sample.data, null, 2));
    } else {
      sampleMeta.textContent = "";
      sampleEl.textContent = "No analyses yet";
    }

    prevTime = now;
    prev = d;
  }

  function syntaxHighlight(json) {
    json = json.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return json.replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      function(match) {
        var cls = "json-num";
        if (/^"/.test(match)) {
          cls = /:$/.test(match) ? "json-key" : "json-str";
        } else if (/true|false/.test(match)) {
          cls = "json-bool";
        } else if (/null/.test(match)) {
          cls = "json-null";
        }
        return '<span class="' + cls + '">' + match + '</span>';
      }
    );
  }

  function poll() {
    fetch(API).then(function(r) { return r.json(); }).then(update)
      .catch(function() {});
  }

  if (API === "inline") {
    update(%%INLINE_DATA%%);
  } else {
    poll();
    setInterval(poll, POLL);
  }

  /* ── Scroll spy ── */
  (function() {
    var sectionLinks = document.querySelectorAll('.sidebar a[href^="#"]');
    var sections = [];
    sectionLinks.forEach(function(a) {
      var id = a.getAttribute('href').slice(1);
      var sec = document.getElementById(id);
      if (sec) sections.push({el: sec, a: a});
    });
    function onScroll() {
      var scrollY = window.scrollY;
      var current = null;
      sections.forEach(function(s) {
        if (s.el.offsetTop - 120 <= scrollY) current = s;
      });
      sectionLinks.forEach(function(a) { a.classList.remove('active'); });
      if (current) current.a.classList.add('active');
    }
    window.addEventListener('scroll', onScroll);
    onScroll();
  })();
})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Shared page shell (sidebar + layout for all sub-pages)
# ---------------------------------------------------------------------------

def page_shell(title, content, active="", extra_css="", extra_js=""):
    # type: (str, str, str, str, str) -> str
    """Wrap content in the shared sidebar + main layout."""
    def _active(page):
        return ' class="active"' if page == active else ''

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MADphotos Dashboard</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='45' fill='%23111'/></svg>">
<style>
  :root {{
    --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", system-ui, sans-serif;
    --font-display: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", system-ui, sans-serif;
    --font-mono: "SF Mono", ui-monospace, "Cascadia Code", monospace;
    --text-xs: 11px; --text-sm: 13px; --text-base: 15px; --text-lg: 17px;
    --text-xl: 20px; --text-2xl: 22px; --text-3xl: 28px;
    --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
    --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-10: 40px;
    --radius-sm: 6px; --radius-md: 10px; --radius-lg: 14px;
    --sidebar-w: 220px;
    --apple-blue: #007AFF; --apple-green: #34C759;
    --leading-normal: 1.47; --leading-relaxed: 1.6;
    --tracking-tight: -0.01em; --tracking-caps: 0.06em;
    --duration-fast: 150ms; --ease-default: cubic-bezier(0.25, 0.1, 0.25, 1);
  }}
  [data-theme="light"] {{
    --bg: #F5F5F7; --bg-secondary: #FFFFFF; --fg: #1D1D1F;
    --fg-secondary: #3A3A3C; --muted: #86868B;
    --border: rgba(0,0,0,0.08); --border-strong: rgba(0,0,0,0.14);
    --card-bg: #FFFFFF; --sidebar-bg: #FFFFFF;
    --sidebar-active-bg: rgba(0,0,0,0.04); --hover-overlay: rgba(0,0,0,0.03);
    color-scheme: light;
  }}
  [data-theme="dark"] {{
    --bg: #1C1C1E; --bg-secondary: #2C2C2E; --fg: #F5F5F7;
    --fg-secondary: #D1D1D6; --muted: #98989D;
    --border: rgba(255,255,255,0.08); --border-strong: rgba(255,255,255,0.14);
    --card-bg: #2C2C2E; --sidebar-bg: #2C2C2E;
    --sidebar-active-bg: rgba(255,255,255,0.06); --hover-overlay: rgba(255,255,255,0.04);
    color-scheme: dark;
  }}
  html {{ scroll-behavior: smooth; }}
  *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: var(--font-sans); font-size: var(--text-base);
    line-height: var(--leading-normal); background: var(--bg); color: var(--fg);
    display: flex; min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }}
  .sidebar {{
    width: var(--sidebar-w); min-width: var(--sidebar-w);
    background: var(--sidebar-bg); border-right: 1px solid var(--border);
    padding: var(--space-5) 0; position: sticky; top: 0; height: 100vh;
    overflow-y: auto; display: flex; flex-direction: column;
  }}
  .sidebar .sb-title {{
    font-family: var(--font-display); font-size: var(--text-lg); font-weight: 700;
    letter-spacing: var(--tracking-tight); padding: 0 var(--space-5) var(--space-4);
    border-bottom: 1px solid var(--border); margin-bottom: var(--space-2);
  }}
  .sidebar a {{
    display: flex; align-items: center; gap: var(--space-2);
    padding: var(--space-2) var(--space-5); color: var(--muted);
    text-decoration: none; font-size: var(--text-sm);
    transition: background var(--duration-fast) var(--ease-default),
                color var(--duration-fast) var(--ease-default);
  }}
  .sidebar a:hover {{ background: var(--sidebar-active-bg); color: var(--fg); }}
  .sidebar a.active {{
    color: var(--fg); font-weight: 600; background: var(--sidebar-active-bg);
    border-left: 3px solid var(--apple-blue);
    padding-left: calc(var(--space-5) - 3px);
  }}
  .sidebar .sb-sep {{ height: 1px; background: var(--border); margin: var(--space-2) var(--space-5); }}
  .sidebar .sb-group {{
    font-size: var(--text-xs); font-weight: 600; text-transform: uppercase;
    letter-spacing: var(--tracking-caps); color: var(--muted);
    padding: var(--space-3) var(--space-5) var(--space-1);
  }}
  .sidebar .sb-bottom {{
    margin-top: auto; padding: var(--space-3) var(--space-5);
    border-top: 1px solid var(--border);
  }}
  .theme-toggle {{
    display: flex; align-items: center; gap: var(--space-2);
    font-size: var(--text-sm); color: var(--muted); cursor: pointer;
    padding: var(--space-2) 0; background: none; border: none;
    font-family: inherit; width: 100%;
    transition: color var(--duration-fast);
  }}
  .theme-toggle:hover {{ color: var(--fg); }}
  .theme-toggle .theme-icon {{ font-size: 16px; }}
  .main-content {{
    flex: 1; padding: var(--space-10) var(--space-8);
    max-width: 900px; min-width: 0; margin: 0 auto;
  }}
  @media (max-width: 900px) {{
    body {{ flex-direction: column; }}
    .sidebar {{ width: 100%; min-width: unset; height: auto; position: relative;
               border-right: none; border-bottom: 1px solid var(--border);
               flex-direction: row; flex-wrap: wrap; padding: var(--space-3); }}
    .sidebar .sb-title {{ width: 100%; border-bottom: none; padding-bottom: var(--space-1); }}
    .sidebar .sb-group, .sidebar .sb-sep, .sidebar .sb-bottom {{ display: none; }}
    .sidebar a {{ padding: var(--space-1) var(--space-3); }}
    .main-content {{ padding: var(--space-6); }}
  }}
  h1 {{ font-family: var(--font-display); font-size: var(--text-3xl); font-weight: 700;
       letter-spacing: var(--tracking-tight); margin-bottom: var(--space-2); }}
  h2 {{ font-family: var(--font-display); font-size: var(--text-xl); font-weight: 700;
       margin: var(--space-8) 0 var(--space-3); color: var(--fg);
       border-bottom: 1px solid var(--border); padding-bottom: var(--space-2); }}
  h3 {{ font-size: var(--text-lg); font-weight: 600; margin: var(--space-6) 0 var(--space-2); color: var(--fg); }}
  h4 {{ font-size: var(--text-base); font-weight: 600; margin: var(--space-4) 0 var(--space-2); color: var(--muted); }}
  p {{ font-size: var(--text-sm); margin: var(--space-2) 0; line-height: var(--leading-relaxed); }}
  ul {{ font-size: var(--text-sm); margin: var(--space-2) 0 var(--space-2) var(--space-5); }}
  li {{ margin: var(--space-1) 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: var(--text-sm); margin: var(--space-3) 0 var(--space-4); }}
  th {{ text-align: left; font-size: var(--text-xs); font-weight: 600; text-transform: uppercase;
       letter-spacing: var(--tracking-caps); color: var(--muted);
       border-bottom: 1px solid var(--border-strong); padding: var(--space-2) var(--space-3); }}
  td {{ padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--border); }}
  code {{ background: var(--hover-overlay); padding: 2px var(--space-2); font-size: var(--text-sm);
         font-family: var(--font-mono); border-radius: var(--radius-sm); }}
  strong {{ font-weight: 700; }}
  a {{ color: var(--fg); }}
  blockquote {{ font-size: var(--text-sm); color: var(--muted); border-left: 3px solid var(--border);
               padding-left: var(--space-4); margin: var(--space-2) 0; font-style: normal; }}
  footer {{ margin-top: var(--space-10); padding-top: var(--space-4);
           border-top: 1px solid var(--border); font-size: var(--text-xs); color: var(--muted); }}
  footer a {{ color: var(--muted); text-decoration: none; }}
  {extra_css}
</style>
</head>
<body>
<nav class="sidebar">
  <div class="sb-title">MADphotos</div>
  <a href="/readme"{_active("readme")}>README</a>
  <a href="/"{_active("status")}>State</a>
  <a href="/journal"{_active("journal")}>Journal de Bord</a>
  <a href="/instructions"{_active("instructions")}>System Instructions</a>
  <div class="sb-sep"></div>
  <div class="sb-group">Experiments</div>
  <a href="/drift"{_active("drift")}>Drift</a>
  <a href="/blind-test"{_active("blind-test")}>Blind Test</a>
  <a href="/mosaics"{_active("mosaics")}>Mosaics</a>
  <div class="sb-bottom">
    <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">
      <span class="theme-icon" id="themeIcon">&#9790;</span>
      <span id="themeLabel">Dark Mode</span>
    </button>
  </div>
</nav>
<div class="main-content">
{content}
<footer>MADphotos &mdash; <a href="https://github.com/LAEH/MADphotos">github.com/LAEH/MADphotos</a></footer>
</div>
<script>
(function() {{
  function getTheme() {{ return localStorage.getItem('mad-theme') || 'light'; }}
  function applyTheme(t) {{
    document.documentElement.setAttribute('data-theme', t);
    var icon = document.getElementById('themeIcon');
    var label = document.getElementById('themeLabel');
    if (icon) icon.textContent = t === 'dark' ? '\\u2600' : '\\u263E';
    if (label) label.textContent = t === 'dark' ? 'Light Mode' : 'Dark Mode';
  }}
  window.toggleTheme = function() {{
    var t = getTheme() === 'dark' ? 'light' : 'dark';
    localStorage.setItem('mad-theme', t);
    applyTheme(t);
  }};
  applyTheme(getTheme());
}})();
</script>
{extra_js}
</body>
</html>"""


# ---------------------------------------------------------------------------
# README renderer
# ---------------------------------------------------------------------------

README_PATH = Path(__file__).resolve().parent / "README.md"


def render_readme():
    # type: () -> str
    """Read README.md and render a styled HTML page."""
    if not README_PATH.exists():
        return "<p>No README.md found.</p>"
    raw = README_PATH.read_text()

    import re

    def md_inline(text):
        # type: (str) -> str
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        return text

    lines = raw.split('\n')
    html_parts = []
    in_table = False
    in_list = False
    i = 0
    while i < len(lines):
        line = lines[i]

        # Heading
        m = re.match(r'^(#{1,4})\s+(.*)', line)
        if m:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            if in_table:
                html_parts.append('</tbody></table>')
                in_table = False
            level = len(m.group(1))
            text = md_inline(m.group(2))
            slug = re.sub(r'[^a-z0-9]+', '-', m.group(2).lower()).strip('-')
            html_parts.append(f'<h{level} id="{slug}">{text}</h{level}>')
            i += 1
            continue

        # Table row
        if line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            # Skip separator rows
            if all(re.match(r'^[-:]+$', c) for c in cells):
                i += 1
                continue
            if not in_table:
                html_parts.append('<table><thead><tr>')
                html_parts.append(''.join(f'<th>{md_inline(c)}</th>' for c in cells))
                html_parts.append('</tr></thead><tbody>')
                in_table = True
            else:
                html_parts.append('<tr>')
                html_parts.append(''.join(f'<td>{md_inline(c)}</td>' for c in cells))
                html_parts.append('</tr>')
            i += 1
            continue

        if in_table and not line.strip().startswith('|'):
            html_parts.append('</tbody></table>')
            in_table = False

        # List item
        if re.match(r'^[-*]\s', line.strip()):
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            text = md_inline(re.sub(r'^[-*]\s+', '', line.strip()))
            html_parts.append(f'<li>{text}</li>')
            i += 1
            continue

        if in_list and not re.match(r'^[-*]\s', line.strip()):
            html_parts.append('</ul>')
            in_list = False

        # Paragraph
        if line.strip():
            html_parts.append(f'<p>{md_inline(line.strip())}</p>')

        i += 1

    if in_list:
        html_parts.append('</ul>')
    if in_table:
        html_parts.append('</tbody></table>')

    body = '\n'.join(html_parts)

    readme_style = """<style>
  .main-content h1 { font-size: var(--text-3xl); margin-bottom: var(--space-1); }
  .main-content > p:first-of-type {
    font-size: var(--text-lg); line-height: var(--leading-relaxed);
    color: var(--fg-secondary); max-width: 640px;
  }
  .main-content h2 {
    font-size: var(--text-xl); margin: var(--space-10) 0 var(--space-4);
    padding-bottom: var(--space-2); border-bottom: 1px solid var(--border);
  }
  .main-content h3 {
    font-size: var(--text-lg); margin: var(--space-6) 0 var(--space-2);
  }
  .main-content > p, .main-content > ul {
    font-size: var(--text-sm); line-height: var(--leading-relaxed);
    color: var(--fg-secondary); max-width: 640px;
  }
  .main-content table {
    width: 100%; border-collapse: separate; border-spacing: 0;
    background: var(--card-bg); border: 1px solid var(--border);
    border-radius: var(--radius-md); overflow: hidden;
    margin: var(--space-4) 0;
  }
  .main-content th {
    text-align: left; font-size: var(--text-xs); font-weight: 600;
    text-transform: uppercase; letter-spacing: var(--tracking-caps);
    color: var(--muted); padding: var(--space-3) var(--space-4);
    background: var(--hover-overlay); border-bottom: 1px solid var(--border);
  }
  .main-content td {
    font-size: var(--text-sm); padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border); color: var(--fg-secondary);
  }
  .main-content tr:last-child td { border-bottom: none; }
  .main-content tr:hover td { background: var(--hover-overlay); }
  .main-content ol {
    font-size: var(--text-sm); color: var(--fg-secondary);
    line-height: var(--leading-relaxed); padding-left: var(--space-5);
    max-width: 640px;
  }
  .main-content li {
    margin: var(--space-2) 0; font-size: var(--text-sm);
    color: var(--fg-secondary); line-height: var(--leading-relaxed);
  }
  .main-content code {
    font-family: var(--font-mono); font-size: 0.9em;
    background: var(--hover-overlay); padding: 1px var(--space-1);
    border-radius: 3px; color: var(--fg);
  }
</style>
"""
    content = readme_style + body
    return page_shell("README", content, active="readme")


# ---------------------------------------------------------------------------
# System Instructions renderer
# ---------------------------------------------------------------------------

def render_instructions():
    # type: () -> str
    content = """<h1>System Instructions</h1>
<p style="font-size:var(--text-sm);color:var(--muted);margin-bottom:var(--space-6);">
  Development principles and operational guidelines for MADphotos.
</p>

<h2>Vision</h2>
<p>9,011 photographs. Every one should carry the richest possible set of reliable, valuable signals &mdash;
extracted from every available open-source model and programmatic method. The goal is not just
to organize images but to <strong>deeply understand</strong> each one: its technical properties,
its semantic content, its emotional resonance, its relationship to every other image in the collection.</p>
<p>Three apps serve three purposes: <strong>See</strong> (native macOS curator &mdash; the human decides),
<strong>Show</strong> (public web gallery &mdash; the curated experience),
<strong>State</strong> (this dashboard &mdash; the control room).</p>

<h2>Signal Completeness</h2>
<ul>
  <li><strong>100% coverage is the target.</strong> Every image must have every signal. After any pipeline run, verify all tables have full coverage. Partial = something failed silently.</li>
  <li><strong>Check for gaps.</strong> Always run a count before declaring complete. Compare table rows against total image count.</li>
  <li><strong>No duplicates.</strong> UUIDs are deterministic (UUID5, DNS namespace + relative path). Run <code>GROUP BY image_uuid HAVING COUNT(*) &gt; 1</code> to verify.</li>
  <li><strong>New models welcome.</strong> When a better open-source model appears for any signal, integrate it. More signals = richer understanding.</li>
</ul>

<h2>Performance</h2>
<ul>
  <li><strong>Batch processing.</strong> Always batch, never one-at-a-time. Use GPU/MPS where available.</li>
  <li><strong>Incremental.</strong> Never reprocess completed images. Every script checks for existing results and skips. Processing can be interrupted and resumed.</li>
  <li><strong>Parallel where possible.</strong> Independent phases run concurrently. Monitor throughput (images/second). If it drops, investigate.</li>
</ul>

<h2>Data Integrity</h2>
<ul>
  <li><strong>Single source of truth.</strong> <code>mad_photos.db</code> is authoritative. All scripts read/write to it.</li>
  <li><strong>Flat rendered layout.</strong> <code>rendered/{tier}/{format}/{uuid}.ext</code> &mdash; NO category subdirectories. Never create <code>rendered/originals/</code> (plural).</li>
  <li><strong>DNG/RAW color space.</strong> Convert with <code>sips -m sRGB Profile.icc</code> to avoid Display P3 purple cast.</li>
  <li><strong>Monochrome sensor.</strong> Leica Monochrom has no Bayer filter. NEVER color-correct Monochrome images.</li>
  <li><strong>Deterministic UUIDs.</strong> UUID5 from DNS namespace + relative path. Every script must produce the same UUID for the same image.</li>
</ul>

<h2>Code Quality</h2>
<ul>
  <li><strong>Python 3.9 compatibility.</strong> <code>from __future__ import annotations</code>, <code>Optional[X]</code> not <code>X | None</code>.</li>
  <li><strong>Clean repository.</strong> No dead code, no commented-out blocks, no unused imports. Every file has a purpose.</li>
  <li><strong>Error resilience.</strong> Never crash silently. Log failures, track them, continue. One bad image must not stop a 9,011-image batch.</li>
</ul>

<h2>AI Analysis</h2>
<ul>
  <li><strong>Vertex AI + ADC only.</strong> Never use API keys. Both Gemini and Imagen use Application Default Credentials.</li>
  <li><strong>Structured output.</strong> Keep raw JSON for future re-extraction. Parse into individual columns for fast queries.</li>
  <li><strong>Source quality.</strong> Imagen uses <code>full</code> tier (3840px). Gemini uses <code>gemini</code> tier (2048px).</li>
  <li><strong>Two-stage variants.</strong> Stage 1 from original. Stage 2 from gemini_edit. Chain preserves quality.</li>
</ul>

<h2>Dashboard &amp; Monitoring</h2>
<ul>
  <li><strong>Live polling every 5s.</strong> Dashboard reflects true system state at all times.</li>
  <li><strong>Journal de Bord.</strong> Every significant action gets a journal entry. Format: <code>### HH:MM &mdash; Title</code>. This is the project narrative.</li>
  <li><strong>Consistent UI.</strong> All label+count data uses pill/tag format. Sidebar on every page. These become filters.</li>
</ul>

<h2>Signal Inventory</h2>
<table>
  <thead><tr><th>Signal</th><th>Source</th><th>Status</th><th>Key Fields</th></tr></thead>
  <tbody>
    <tr><td>EXIF</td><td>Pillow</td><td>9,011 / 9,011</td><td>Camera, lens, focal length, aperture, shutter, ISO, GPS, flash, WB</td></tr>
    <tr><td>Pixel Analysis</td><td>NumPy / OpenCV</td><td>9,011 / 9,011</td><td>Brightness, saturation, contrast, noise, WB shifts, color temp, histograms</td></tr>
    <tr><td>Dominant Colors</td><td>K-means (LAB)</td><td>9,011 / 9,011</td><td>5 clusters: hex, RGB, LAB, percentage, CSS name</td></tr>
    <tr><td>Face Detection</td><td>YuNet</td><td>9,011 / 9,011</td><td>Bounding boxes, 5 landmarks, confidence, face area %</td></tr>
    <tr><td>Object Detection</td><td>YOLOv8n</td><td>9,011 / 9,011</td><td>80 COCO classes, bounding boxes, confidence</td></tr>
    <tr><td>Perceptual Hashes</td><td>imagehash</td><td>9,011 / 9,011</td><td>pHash, aHash, dHash, wHash, blur, sharpness, entropy</td></tr>
    <tr><td>Vectors</td><td>DINOv2 + SigLIP + CLIP</td><td>9,011 / 9,011</td><td>768d + 768d + 512d = 2,048 dimensions per image</td></tr>
    <tr><td>Gemini Analysis</td><td>Gemini 2.5 Pro</td><td>5,635 / 9,011</td><td>Alt text, vibes, exposure, composition, grading, time, setting, pops, edit prompt</td></tr>
    <tr><td>Aesthetic Scoring</td><td>LAION aesthetic (CLIP MLP)</td><td>9,011 / 9,011</td><td>Score 1&ndash;10, label (excellent/good/average/poor)</td></tr>
    <tr><td>Depth Estimation</td><td>Depth Anything v2</td><td>9,011 / 9,011</td><td>Near/mid/far percentages, complexity bucket</td></tr>
    <tr><td>Scene Classification</td><td>Places365 (ResNet50)</td><td>9,011 / 9,011</td><td>Top 3 scene labels, environment (indoor/outdoor)</td></tr>
    <tr><td>Style Classification</td><td>Scene + composition derived</td><td>9,011 / 9,011</td><td>Style label (street, portrait, landscape, etc.)</td></tr>
    <tr><td>OCR / Text Detection</td><td>EasyOCR</td><td>in progress</td><td>Detected text regions, language, confidence</td></tr>
    <tr><td>Image Captions</td><td>BLIP (Salesforce)</td><td>in progress</td><td>Natural language caption per image</td></tr>
    <tr><td>Facial Emotions</td><td>ViT face expression</td><td>in progress</td><td>Dominant emotion, 7-class scores per face</td></tr>
    <tr><td>Enhancement Plans</td><td>Camera-aware engine</td><td>9,011 / 9,011</td><td>WB correction, gamma, shadows, highlights, contrast, saturation, sharpening</td></tr>
  </tbody>
</table>

<h2>Future Signals</h2>
<ul>
  <li><strong>Segmentation</strong> &mdash; SAM (Segment Anything) for object masks</li>
  <li><strong>Better aesthetic scoring</strong> &mdash; Current LAION model gives no discrimination (91% score &ldquo;excellent&rdquo;). Needs recalibration or alternative model.</li>
</ul>
"""
    return page_shell("System Instructions", content, active="instructions")


# ---------------------------------------------------------------------------
# Mosaics renderer
# ---------------------------------------------------------------------------

def render_mosaics():
    # type: () -> str
    """Render the mosaics gallery page."""
    meta_path = MOSAIC_DIR / "mosaics.json"
    mosaics = []
    if meta_path.exists():
        mosaics = json.loads(meta_path.read_text())

    if not mosaics:
        return page_shell("Mosaics", "<h1>Mosaics</h1><p>No mosaics generated yet. Run <code>python3 generate_mosaics.py</code></p>", active="mosaics")

    cards = []
    for m in mosaics:
        cards.append(
            f'<div class="mosaic-card" onclick="openMosaic(\'/mosaics/{m["file"]}\', \'{m["title"]}\')">'
            f'<img src="/mosaics/{m["file"]}" loading="lazy" alt="{m["title"]}">'
            f'<div class="mosaic-meta">'
            f'<div class="mosaic-title">{m["title"]}</div>'
            f'<div class="mosaic-desc">{m["desc"]}</div>'
            f'<div class="mosaic-count">{m["count"]:,} images</div>'
            f'</div></div>'
        )

    content = f"""<style>
  .mosaic-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: var(--space-6);
    margin-top: var(--space-4);
  }}
  .mosaic-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    cursor: pointer;
    overflow: hidden;
    transition: transform var(--duration-fast) var(--ease-default),
                box-shadow var(--duration-fast) var(--ease-default);
  }}
  .mosaic-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  }}
  .mosaic-card img {{
    width: 100%;
    display: block;
    aspect-ratio: 1;
    object-fit: cover;
  }}
  .mosaic-meta {{
    padding: var(--space-3) var(--space-4);
  }}
  .mosaic-title {{
    font-weight: 700;
    font-size: var(--text-sm);
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
  }}
  .mosaic-desc {{
    font-size: var(--text-xs);
    color: var(--muted);
    margin-top: var(--space-1);
    line-height: var(--leading-normal);
  }}
  .mosaic-count {{
    font-size: var(--text-xs);
    color: var(--muted);
    margin-top: var(--space-1);
    font-weight: 600;
  }}

  /* Mosaic zoom modal — fullscreen overlay, keeps its own color scheme */
  .mosaic-modal {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    z-index: 9999;
    background: rgba(0,0,0,0.92);
    justify-content: center;
    align-items: center;
    flex-direction: column;
  }}
  .mosaic-modal.active {{
    display: flex;
  }}
  .mosaic-modal-header {{
    position: fixed;
    top: 0; left: 0; right: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-4) var(--space-5);
    background: rgba(0,0,0,0.7);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    z-index: 10001;
  }}
  .mosaic-modal-title {{
    font-size: var(--text-sm);
    font-weight: 700;
    color: rgba(255,255,255,0.95);
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
  }}
  .mosaic-modal-controls {{
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }}
  .mosaic-modal-controls button {{
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.25);
    color: rgba(255,255,255,0.95);
    padding: var(--space-1) var(--space-3);
    font-family: var(--font-sans);
    font-size: var(--text-sm);
    cursor: pointer;
    border-radius: var(--radius-sm);
    transition: background var(--duration-fast) var(--ease-default);
  }}
  .mosaic-modal-controls button:hover {{
    background: rgba(255,255,255,0.25);
  }}
  .mosaic-modal-zoom-label {{
    font-size: var(--text-xs);
    color: rgba(255,255,255,0.6);
    min-width: 48px;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }}
  .mosaic-modal-viewport {{
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    overflow: auto;
    cursor: grab;
    z-index: 10000;
    padding-top: 48px;
  }}
  .mosaic-modal-viewport:active {{
    cursor: grabbing;
  }}
  .mosaic-modal-viewport img {{
    display: block;
    transform-origin: 0 0;
    transition: transform var(--duration-fast) var(--ease-default);
  }}
</style>

<!-- Mosaic zoom modal -->
<div class="mosaic-modal" id="mosaicModal">
  <div class="mosaic-modal-header">
    <div class="mosaic-modal-title" id="mosaicModalTitle"></div>
    <div class="mosaic-modal-controls">
      <button onclick="mosaicZoom(-1)" title="Zoom out (-)">-</button>
      <span class="mosaic-modal-zoom-label" id="mosaicZoomLabel">100%</span>
      <button onclick="mosaicZoom(1)" title="Zoom in (+)">+</button>
      <button onclick="mosaicFit()" title="Fit to screen (F)">Fit</button>
      <button onclick="mosaicActual()" title="Actual size (1)">1:1</button>
      <button onclick="closeMosaic()" title="Close (Esc)">Close</button>
    </div>
  </div>
  <div class="mosaic-modal-viewport" id="mosaicViewport">
    <img id="mosaicImg" draggable="false">
  </div>
</div>

<script>
(function() {{
  var modal = document.getElementById('mosaicModal');
  var viewport = document.getElementById('mosaicViewport');
  var img = document.getElementById('mosaicImg');
  var titleEl = document.getElementById('mosaicModalTitle');
  var zoomLabel = document.getElementById('mosaicZoomLabel');
  var scale = 1;
  var isDragging = false;
  var dragStart = {{x: 0, y: 0}};
  var scrollStart = {{x: 0, y: 0}};

  window.openMosaic = function(src, title) {{
    img.src = src;
    titleEl.textContent = title;
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    img.onload = function() {{
      mosaicFit();
    }};
  }};

  window.closeMosaic = function() {{
    modal.classList.remove('active');
    document.body.style.overflow = '';
    img.src = '';
  }};

  window.mosaicZoom = function(dir) {{
    var steps = [0.25, 0.33, 0.5, 0.67, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4];
    var idx = 0;
    for (var i = 0; i < steps.length; i++) {{
      if (Math.abs(steps[i] - scale) < 0.01) {{ idx = i; break; }}
      if (steps[i] > scale) {{ idx = dir > 0 ? i : Math.max(0, i-1); break; }}
      idx = i;
    }}
    idx = Math.max(0, Math.min(steps.length - 1, idx + dir));
    setScale(steps[idx]);
  }};

  window.mosaicFit = function() {{
    if (!img.naturalWidth) return;
    var vw = viewport.clientWidth;
    var vh = viewport.clientHeight - 48;
    var s = Math.min(vw / img.naturalWidth, vh / img.naturalHeight, 1);
    setScale(s);
  }};

  window.mosaicActual = function() {{
    setScale(1);
  }};

  function setScale(s) {{
    scale = s;
    img.style.width = (img.naturalWidth * scale) + 'px';
    img.style.height = (img.naturalHeight * scale) + 'px';
    zoomLabel.textContent = Math.round(scale * 100) + '%';
  }}

  // Mouse wheel zoom
  viewport.addEventListener('wheel', function(e) {{
    e.preventDefault();
    var dir = e.deltaY < 0 ? 1 : -1;
    mosaicZoom(dir);
  }}, {{passive: false}});

  // Drag to pan
  viewport.addEventListener('mousedown', function(e) {{
    isDragging = true;
    dragStart.x = e.clientX;
    dragStart.y = e.clientY;
    scrollStart.x = viewport.scrollLeft;
    scrollStart.y = viewport.scrollTop;
  }});
  window.addEventListener('mousemove', function(e) {{
    if (!isDragging) return;
    viewport.scrollLeft = scrollStart.x - (e.clientX - dragStart.x);
    viewport.scrollTop = scrollStart.y - (e.clientY - dragStart.y);
  }});
  window.addEventListener('mouseup', function() {{
    isDragging = false;
  }});

  // Keyboard shortcuts
  window.addEventListener('keydown', function(e) {{
    if (!modal.classList.contains('active')) return;
    if (e.key === 'Escape') closeMosaic();
    else if (e.key === '+' || e.key === '=') mosaicZoom(1);
    else if (e.key === '-') mosaicZoom(-1);
    else if (e.key === 'f' || e.key === 'F') mosaicFit();
    else if (e.key === '1') mosaicActual();
  }});
}})();
</script>

<h1>Mosaics</h1>
<p style="font-size:var(--text-sm);color:var(--muted);margin-bottom:var(--space-4);">
  Every photograph in the collection, tiled into ~4K square mosaics.
  Each mosaic sorts the images by a different dimension. Click to zoom.
  <span style="color:var(--muted);opacity:0.6;">Scroll to zoom, drag to pan. Keys: +/- zoom, F fit, 1 actual size, Esc close.</span>
</p>
<div class="mosaic-grid">
{''.join(cards)}
</div>"""

    return page_shell("Mosaics", content, active="mosaics")


# ---------------------------------------------------------------------------
# Journal renderer
# ---------------------------------------------------------------------------

JOURNAL_PATH = Path(__file__).resolve().parent / "docs" / "journal.md"


def render_journal():
    """Read journal.md and render a compact B&W HTML page."""
    if not JOURNAL_PATH.exists():
        return "<p>No journal found.</p>"
    raw = JOURNAL_PATH.read_text()

    import re

    def md_inline(text):
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        return text

    def first_sentence(text):
        m = re.match(r'([^.!?]+[.!?])', text)
        return m.group(1).strip() if m else text[:120]

    def parse_event_line(stripped, event_lines):
        if stripped.startswith("> "):
            event_lines.append(f'<blockquote>{md_inline(stripped[2:])}</blockquote>')
        elif stripped.startswith("**Intent.**"):
            text = stripped.replace("**Intent.**", "").strip()
            event_lines.append(f'<p class="intent">{md_inline(first_sentence(text))}</p>')
        elif stripped.startswith("**Discovered.**"):
            text = stripped.replace("**Discovered.**", "").strip()
            event_lines.append(f'<p class="discovered">{md_inline(first_sentence(text))}</p>')

    lines = raw.split("\n")
    intro_html = []
    date_sections = []
    current_date = None  # type: Optional[dict]
    current_event_lines = []  # type: list
    current_event_heading = ""
    in_intro = True
    in_list = False
    in_event = False
    skip_rest = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                intro_html.append("</ul>")
                in_list = False
            skip_rest = False
            continue

        if stripped.startswith("# "):
            intro_html.append(f'<h1>{stripped[2:]}</h1>')
            continue

        if stripped.startswith("## "):
            if in_event and current_date is not None:
                current_date["events"].append(
                    {"html": current_event_heading + "\n".join(current_event_lines) + "</div>"}
                )
                in_event = False
            header_text = stripped[3:]
            if re.match(r'\d{4}-\d{2}-\d{2}', header_text):
                in_intro = False
                current_date = {"header": header_text, "events": []}
                date_sections.append(current_date)
            else:
                if in_intro:
                    intro_html.append(f'<h2 class="date-header">{header_text}</h2>')
            continue

        if stripped.startswith("### "):
            if in_event and current_date is not None:
                current_date["events"].append(
                    {"html": current_event_heading + "\n".join(current_event_lines) + "</div>"}
                )
            in_event = True
            skip_rest = False
            current_event_lines = []
            heading = stripped[4:]
            m = re.match(r'(.+?)\s*\*\((.+?)\)\*\s*$', heading)
            if m:
                current_event_heading = (
                    f'<div class="event">'
                    f'<h3>{m.group(1).rstrip()}</h3>'
                    f'<span class="quote">({m.group(2)})</span>'
                )
            else:
                current_event_heading = f'<div class="event"><h3>{heading}</h3>'
            continue

        if stripped.startswith("---"):
            if in_event and current_date is not None:
                current_date["events"].append(
                    {"html": current_event_heading + "\n".join(current_event_lines) + "</div>"}
                )
                in_event = False
            continue

        if in_event and not in_intro:
            if not skip_rest:
                if stripped.startswith("> ") or stripped.startswith("**Intent.**") or stripped.startswith("**Discovered.**"):
                    parse_event_line(stripped, current_event_lines)
                    if stripped.startswith("**Intent.**") or stripped.startswith("**Discovered.**"):
                        skip_rest = True
            continue

        if in_intro:
            if stripped.startswith("- "):
                if not in_list:
                    intro_html.append("<ul>")
                    in_list = True
                intro_html.append(f"<li>{md_inline(stripped[2:])}</li>")
            elif not skip_rest:
                intro_html.append(f"<p>{md_inline(stripped)}</p>")

    if in_event and current_date is not None:
        current_date["events"].append(
            {"html": current_event_heading + "\n".join(current_event_lines) + "</div>"}
        )
    if in_list:
        intro_html.append("</ul>")

    html_parts = intro_html[:]
    for date_sec in reversed(date_sections):
        html_parts.append(f'<h2 class="date-header">{date_sec["header"]}</h2>')
        for ev in reversed(date_sec["events"]):
            html_parts.append(ev["html"])

    body = "\n".join(html_parts)

    journal_content = f"""<style>
  .date-header {{
    font-size: var(--text-sm); font-weight: 600; margin: var(--space-8) 0 var(--space-3);
    padding: var(--space-2) var(--space-3); color: var(--muted);
    background: var(--hover-overlay); border-radius: var(--radius-sm);
    letter-spacing: var(--tracking-caps); text-transform: uppercase;
  }}
  .event {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-5);
    margin-bottom: var(--space-3);
    transition: border-color var(--duration-fast) var(--ease-default);
    position: relative;
  }}
  .event:hover {{
    border-color: var(--border-strong);
  }}
  /* Thread connector line */
  .event + .event::before {{
    content: "";
    position: absolute;
    top: calc(-1 * var(--space-3));
    left: var(--space-6);
    width: 2px;
    height: var(--space-3);
    background: var(--border);
  }}
  .main-content h3 {{
    font-size: var(--text-sm); font-weight: 700; margin: 0;
    color: var(--fg); display: block; line-height: var(--leading-normal);
  }}
  .quote {{
    font-size: var(--text-xs); color: var(--muted); font-style: italic;
    font-weight: 400; display: block; margin-top: 2px;
  }}
  .intent {{
    font-size: var(--text-sm); color: var(--fg-secondary);
    margin: var(--space-2) 0 0; line-height: var(--leading-relaxed);
  }}
  .discovered {{
    font-size: var(--text-sm); color: var(--muted);
    margin: var(--space-2) 0 0; font-style: italic; line-height: var(--leading-relaxed);
    padding-left: var(--space-3);
    border-left: 2px solid var(--border-strong);
  }}
  .event blockquote {{
    font-size: var(--text-sm); color: var(--fg-secondary);
    margin: var(--space-2) 0 0; line-height: var(--leading-relaxed);
    padding-left: var(--space-3);
    border-left: 2px solid var(--apple-blue);
    font-style: italic;
  }}
  .main-content p {{ font-size: var(--text-sm); color: var(--fg-secondary); margin-bottom: var(--space-2); line-height: var(--leading-relaxed); }}
  .main-content ul {{ list-style: none; margin: var(--space-3) 0; }}
  .main-content li {{
    font-size: var(--text-sm); color: var(--fg-secondary);
    padding: var(--space-1) 0 var(--space-1) var(--space-5); position: relative;
  }}
  .main-content li::before {{ content: "\u2014"; position: absolute; left: 0; color: var(--muted); }}
  hr {{ border: none; margin: 0; }}
</style>
{body}"""

    return page_shell("Journal de Bord", journal_content, active="journal")


# ---------------------------------------------------------------------------
# Drift — Vector nearest-neighbor explorer
# ---------------------------------------------------------------------------

RENDERED_DIR = Path(__file__).resolve().parent / "rendered"


def render_drift():
    # type: () -> str
    """Sample 10 images, find 4 nearest neighbors per embedding model."""
    import random

    try:
        import lancedb as _ldb
    except ImportError:
        return page_shell("Drift", "<h1>Drift</h1><p>lancedb not installed.</p>", active="drift")

    lance_path = Path(__file__).resolve().parent / "vectors.lance"
    if not lance_path.exists():
        return page_shell("Drift", "<h1>Drift</h1><p>No vector store found.</p>", active="drift")

    _db = _ldb.connect(str(lance_path))
    tbl = _db.open_table("image_vectors")
    df = tbl.to_pandas()

    # Sample 10 random images
    all_uuids = df["uuid"].tolist()
    sample_uuids = random.sample(all_uuids, min(10, len(all_uuids)))

    models = [
        ("dino", "DINOv2", "Composition & texture"),
        ("siglip", "SigLIP", "Semantic meaning"),
        ("clip", "CLIP", "Subject matching"),
    ]

    sections_html = []
    for idx, query_uuid in enumerate(sample_uuids):
        query_row = df[df["uuid"] == query_uuid].iloc[0]

        rows_html = []
        for col, model_name, model_desc in models:
            query_vec = query_row[col]
            results = tbl.search(query_vec, vector_column_name=col).limit(5).to_pandas()
            # Skip self (first result)
            neighbors = results[results["uuid"] != query_uuid].head(4)

            # Build neighbor cells
            neighbor_cells = []
            for _, nb_row in neighbors.iterrows():
                nb_uuid = nb_row["uuid"]
                dist = nb_row["_distance"]
                neighbor_cells.append(
                    f'<div class="drift-cell">'
                    f'<img src="/thumb/{nb_uuid}" loading="lazy" alt="{nb_uuid[:8]}">'
                    f'<div class="drift-dist">{dist:.3f}</div>'
                    f'</div>'
                )

            rows_html.append(
                f'<div class="drift-model-row">'
                f'<div class="drift-model-label">'
                f'<span class="drift-model-name">{model_name}</span>'
                f'<span class="drift-model-desc">{model_desc}</span>'
                f'</div>'
                f'<div class="drift-cell drift-cell-query">'
                f'<img src="/thumb/{query_uuid}" loading="lazy" alt="{query_uuid[:8]}">'
                f'<div class="drift-dist">query</div>'
                f'</div>'
                + "".join(neighbor_cells) +
                f'</div>'
            )

        sections_html.append(
            f'<div class="drift-section">'
            f'<div class="drift-section-header">'
            f'<span class="drift-section-num">{idx + 1}</span>'
            f'<span class="drift-section-uuid">{query_uuid[:8]}</span>'
            f'</div>'
            + "\n".join(rows_html) +
            f'</div>'
        )

    body = "\n".join(sections_html)

    content = f"""<style>
  .drift-section {{
    margin-bottom: var(--space-10);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--card-bg);
    overflow: hidden;
  }}
  .drift-section-header {{
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--border);
    background: var(--hover-overlay);
  }}
  .drift-section-num {{
    font-family: var(--font-display);
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--muted);
  }}
  .drift-section-uuid {{
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--muted);
  }}
  .drift-model-row {{
    display: flex;
    align-items: stretch;
    border-bottom: 1px solid var(--border);
    min-height: 120px;
  }}
  .drift-model-row:last-child {{ border-bottom: none; }}
  .drift-model-label {{
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-width: 100px;
    max-width: 100px;
    padding: var(--space-3);
    border-right: 1px solid var(--border);
    background: var(--hover-overlay);
  }}
  .drift-model-name {{
    font-size: var(--text-sm);
    font-weight: 700;
    color: var(--fg);
  }}
  .drift-model-desc {{
    font-size: 10px;
    color: var(--muted);
    margin-top: 2px;
  }}
  .drift-cell {{
    flex: 1;
    position: relative;
    min-width: 0;
    border-right: 1px solid var(--border);
  }}
  .drift-cell:last-child {{ border-right: none; }}
  .drift-cell img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    min-height: 120px;
  }}
  .drift-cell-query {{
    flex: 1;
    position: relative;
  }}
  .drift-cell-query::after {{
    content: "";
    position: absolute;
    inset: 0;
    border: 3px solid var(--apple-blue);
    pointer-events: none;
  }}
  .drift-dist {{
    position: absolute;
    bottom: 0;
    left: 0;
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 600;
    color: rgba(255,255,255,0.95);
    background: rgba(0,0,0,0.6);
    padding: 2px var(--space-2);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
  }}
  .drift-cell-query .drift-dist {{
    background: var(--apple-blue);
  }}
  @media (max-width: 700px) {{
    .drift-model-label {{ min-width: 60px; max-width: 60px; }}
    .drift-model-name {{ font-size: var(--text-xs); }}
    .drift-model-desc {{ display: none; }}
  }}
</style>

<h1>Drift</h1>
<p style="font-size:var(--text-sm);color:var(--muted);margin-bottom:var(--space-6);">
  10 random images. For each, the 4 nearest neighbors from each embedding model.
  <strong>DINOv2</strong> sees texture and composition.
  <strong>SigLIP</strong> sees semantic meaning.
  <strong>CLIP</strong> matches subjects.
  Distance = L2 in embedding space.
  <a href="/drift" style="color:var(--apple-blue);text-decoration:none;margin-left:var(--space-2);">Reshuffle &rarr;</a>
</p>
{body}"""

    return page_shell("Drift", content, active="drift")


# ---------------------------------------------------------------------------
# Blind test renderer
# ---------------------------------------------------------------------------

BLIND_TEST_DIR = Path(__file__).resolve().parent / "ai_variants" / "blind_test"


def render_blind_test():
    """Build the 3-way blind test: Original vs Enhanced v1 vs Enhanced v2."""
    manifest_path = BLIND_TEST_DIR / "manifest.json"
    if not manifest_path.exists():
        return page_shell("Blind Test", """
            <div style="text-align:center;padding:var(--space-16) 0;color:var(--muted);">
                <p style="font-size:var(--text-lg);margin-bottom:var(--space-4);">No blind test data yet.</p>
                <p style="font-size:var(--text-sm);">Run <code>python3 prep_blind_test.py</code> after both enhancement engines have completed.</p>
            </div>
        """)
    test_data = json.loads(manifest_path.read_text())
    total = len(test_data)

    rows_html = []
    for i, item in enumerate(test_data):
        uid = item["uuid"]
        order = item["order"]  # e.g. ["enhanced_v2", "original", "enhanced_v1"]
        cells = []
        for j, method in enumerate(order):
            letter = chr(65 + j)  # A, B, C
            cells.append(
                f'<div class="bt-cell" data-row="{i}" data-method="{method}" onclick="pick(this)">'
                f'<img src="/blind/{uid}_{method}.jpg" loading="lazy" alt="Option {letter}">'
                f'<div class="bt-letter">{letter}</div>'
                f'<div class="bt-reveal-label"></div>'
                f'</div>'
            )
        camera = item.get("camera", "")
        camera_tag = f'<span class="bt-cam">{camera}</span>' if camera else ""
        rows_html.append(
            f'<div class="bt-row" id="row-{i}">'
            f'<div class="bt-meta"><span class="bt-num">{i+1}</span>{camera_tag}</div>'
            f'<div class="bt-images">'
            + "".join(cells) +
            f'</div></div>'
        )

    body = "\n".join(rows_html)

    content = f"""
<div class="bt-header">
  <h1>Blind Test</h1>
  <p class="bt-subtitle">{total} images &mdash; 3 versions per row (Original, Enhanced v1, Enhanced v2) in random order.<br>
  Click the best-looking version in each row. Your pick gets elevated. Skip rows if none stands out.</p>
  <div class="bt-scoreboard" id="scoreboard">
    <div class="bt-score-item"><span class="bt-score-val" id="score-picked">0</span><span class="bt-score-lbl">picked</span></div>
    <div class="bt-score-item"><span class="bt-score-val" id="score-skipped">{total}</span><span class="bt-score-lbl">remaining</span></div>
  </div>
</div>
{body}
<div class="bt-actions">
  <button class="bt-btn bt-btn-reveal" onclick="reveal()" id="btn-reveal">Reveal Results</button>
</div>
<div class="bt-results" id="results"></div>
"""

    css = """
  .bt-header { margin-bottom: var(--space-8); }
  .bt-header h1 {
    font-family: var(--font-display, -apple-system, sans-serif);
    font-size: 28px; font-weight: 700; letter-spacing: -0.01em;
    margin-bottom: var(--space-2);
  }
  .bt-subtitle {
    font-size: var(--text-sm, 13px); color: var(--muted, #86868B);
    line-height: 1.5; margin-bottom: var(--space-6, 24px);
  }
  .bt-scoreboard {
    display: flex; gap: var(--space-6, 24px);
    padding: var(--space-4, 16px) var(--space-6, 24px);
    background: var(--card-bg, #fff); border: 1px solid var(--border, rgba(0,0,0,0.08));
    border-radius: var(--radius-md, 10px); display: inline-flex;
  }
  .bt-score-item { text-align: center; }
  .bt-score-val {
    display: block; font-size: 24px; font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .bt-score-lbl { font-size: 11px; color: var(--muted, #86868B); text-transform: uppercase; letter-spacing: 0.05em; }

  .bt-row {
    margin-bottom: var(--space-6, 24px);
    padding-bottom: var(--space-6, 24px);
    border-bottom: 1px solid var(--border, rgba(0,0,0,0.08));
  }
  .bt-row:last-child { border-bottom: none; }
  .bt-meta {
    display: flex; align-items: center; gap: var(--space-3, 12px);
    margin-bottom: var(--space-3, 12px);
  }
  .bt-num {
    font-size: 11px; font-weight: 600; color: var(--muted, #86868B);
    background: var(--card-bg, #fff); border: 1px solid var(--border, rgba(0,0,0,0.08));
    border-radius: var(--radius-sm, 6px);
    padding: 2px 8px; font-variant-numeric: tabular-nums;
  }
  .bt-cam {
    font-size: 11px; color: var(--muted, #86868B);
  }
  .bt-images {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-3, 12px);
  }
  .bt-cell {
    position: relative; cursor: pointer; overflow: hidden;
    border-radius: var(--radius-md, 10px);
    border: 3px solid transparent;
    background: var(--card-bg, #fff);
    transition: transform 0.25s cubic-bezier(0.25, 0.1, 0.25, 1),
                box-shadow 0.25s cubic-bezier(0.25, 0.1, 0.25, 1),
                border-color 0.15s ease;
  }
  .bt-cell img {
    width: 100%; display: block;
    border-radius: calc(var(--radius-md, 10px) - 3px);
  }
  .bt-cell:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  }
  .bt-cell.selected {
    border-color: #007AFF;
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0,122,255,0.2), 0 4px 12px rgba(0,0,0,0.08);
  }
  .bt-cell.selected .bt-letter {
    background: #007AFF; color: #fff;
  }
  .bt-letter {
    position: absolute; top: var(--space-2, 8px); left: var(--space-2, 8px);
    width: 28px; height: 28px; border-radius: 50%;
    background: rgba(0,0,0,0.5); color: rgba(255,255,255,0.9);
    font-size: 13px; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s, color 0.15s;
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  }
  .bt-reveal-label {
    position: absolute; bottom: 0; left: 0; right: 0;
    background: rgba(0,0,0,0.75); color: #fff;
    font-size: 12px; font-weight: 600; text-align: center;
    padding: 6px; display: none;
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  }
  .bt-revealed .bt-reveal-label { display: block; }
  .bt-revealed .bt-cell.selected .bt-reveal-label { background: rgba(0,122,255,0.85); }

  .bt-actions {
    text-align: center; margin: var(--space-8, 32px) 0;
    position: sticky; bottom: var(--space-4, 16px); z-index: 10;
  }
  .bt-btn {
    padding: var(--space-3, 12px) var(--space-8, 32px);
    border: none; font-family: inherit; font-size: 15px; font-weight: 600;
    cursor: pointer; border-radius: var(--radius-full, 9999px);
    transition: opacity 0.15s, transform 0.15s;
  }
  .bt-btn:hover { opacity: 0.85; transform: scale(1.02); }
  .bt-btn:active { transform: scale(0.98); }
  .bt-btn-reveal {
    background: #1D1D1F; color: #F5F5F7;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  }
  .bt-results {
    margin: var(--space-8, 32px) 0;
    padding: var(--space-6, 24px) var(--space-8, 32px);
    background: var(--card-bg, #fff);
    border: 1px solid var(--border, rgba(0,0,0,0.08));
    border-radius: var(--radius-lg, 14px);
    display: none;
  }
  .bt-results h2 {
    font-size: 20px; font-weight: 700; margin-bottom: var(--space-4, 16px);
  }
  .bt-result-row {
    display: flex; align-items: center; gap: var(--space-4, 16px);
    padding: var(--space-3, 12px) 0;
    border-bottom: 1px solid var(--border, rgba(0,0,0,0.08));
  }
  .bt-result-row:last-child { border-bottom: none; }
  .bt-result-name { font-weight: 600; font-size: 14px; min-width: 120px; }
  .bt-result-bar-wrap {
    flex: 1; height: 8px; background: var(--bar-bg, rgba(0,0,0,0.06));
    border-radius: 4px; overflow: hidden;
  }
  .bt-result-bar {
    height: 100%; border-radius: 4px;
    transition: width 0.8s cubic-bezier(0.25, 0.1, 0.25, 1);
  }
  .bt-result-count { font-size: 14px; font-weight: 600; min-width: 60px; text-align: right; font-variant-numeric: tabular-nums; }

  @media (max-width: 700px) {{
    .bt-images {{ grid-template-columns: 1fr; gap: var(--space-2, 8px); }}
    .bt-cell {{ border-width: 2px; }}
    .bt-header h1 {{ font-size: 22px; }}
    .bt-scoreboard {{ flex-direction: column; gap: var(--space-2, 8px); }}
  }}
"""

    script = """
<script>
var picks = {};
var TOTAL = """ + str(total) + """;
var METHOD_NAMES = { original: "Original", enhanced_v1: "Enhanced v1", enhanced_v2: "Enhanced v2" };
var METHOD_COLORS = { original: "#86868B", enhanced_v1: "#007AFF", enhanced_v2: "#34C759" };

function updateScoreboard() {
  var n = Object.keys(picks).length;
  document.getElementById("score-picked").textContent = n;
  document.getElementById("score-skipped").textContent = TOTAL - n;
}

function pick(el) {
  var row = el.dataset.row;
  var method = el.dataset.method;
  var cells = document.querySelectorAll('.bt-cell[data-row="'+row+'"]');

  // Toggle off if already selected
  if (picks[row] === method) {
    delete picks[row];
    cells.forEach(function(c) { c.classList.remove('selected'); });
    updateScoreboard();
    return;
  }

  // Select this one
  cells.forEach(function(c) { c.classList.remove('selected'); });
  el.classList.add('selected');
  picks[row] = method;
  updateScoreboard();
}

function reveal() {
  var scores = { original: 0, enhanced_v1: 0, enhanced_v2: 0 };
  var total_picked = 0;
  for (var k in picks) { scores[picks[k]]++; total_picked++; }
  var skipped = TOTAL - total_picked;
  var maxScore = Math.max(scores.original, scores.enhanced_v1, scores.enhanced_v2, 1);

  // Show labels on all images
  document.querySelectorAll('.bt-row').forEach(function(row) { row.classList.add('bt-revealed'); });
  document.querySelectorAll('.bt-cell').forEach(function(cell) {
    var method = cell.dataset.method;
    var label = cell.querySelector('.bt-reveal-label');
    label.textContent = METHOD_NAMES[method];
  });

  // Build results
  var html = '<h2>Results</h2>';
  ['original', 'enhanced_v1', 'enhanced_v2'].forEach(function(m) {
    var pct = maxScore > 0 ? (scores[m] / TOTAL * 100) : 0;
    var barW = maxScore > 0 ? (scores[m] / maxScore * 100) : 0;
    html += '<div class="bt-result-row">' +
      '<span class="bt-result-name" style="color:' + METHOD_COLORS[m] + '">' + METHOD_NAMES[m] + '</span>' +
      '<div class="bt-result-bar-wrap"><div class="bt-result-bar" style="width:' + barW + '%;background:' + METHOD_COLORS[m] + '"></div></div>' +
      '<span class="bt-result-count">' + scores[m] + ' / ' + TOTAL + '</span>' +
      '</div>';
  });
  if (skipped > 0) {
    html += '<div style="text-align:center;margin-top:16px;font-size:13px;color:#86868B;">Skipped: ' + skipped + ' rows</div>';
  }

  var res = document.getElementById('results');
  res.innerHTML = html;
  res.style.display = 'block';

  // Hide reveal button
  document.getElementById('btn-reveal').style.display = 'none';

  res.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
</script>
"""

    return page_shell("Blind Test", content, extra_css=css, extra_js=script)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/stats":
            data = json.dumps(get_stats()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/readme":
            html = render_readme().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/mosaics":
            html = render_mosaics().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/instructions":
            html = render_instructions().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        elif self.path.startswith("/mosaics/"):
            fname = self.path[9:]
            fpath = MOSAIC_DIR / fname
            if fpath.exists() and fpath.suffix in (".jpg", ".jpeg", ".png"):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(fpath.read_bytes())
            else:
                self.send_error(404)
        elif self.path == "/mosaic-hero":
            mosaic_path = RENDERED_DIR / "mosaics" / "by_brightness.jpg"
            if mosaic_path.exists():
                # Serve a resized version for the hero
                hero_cache = BASE_DIR / "docs" / "hero-mosaic.jpg"
                if hero_cache.exists():
                    data = hero_cache.read_bytes()
                else:
                    from PIL import Image as _PILImage
                    img = _PILImage.open(str(mosaic_path))
                    w, h = img.size
                    new_w = 1200
                    new_h = int(h * new_w / w)
                    img = img.resize((new_w, new_h), _PILImage.LANCZOS)
                    import io
                    buf = io.BytesIO()
                    img.save(buf, "JPEG", quality=75, optimize=True)
                    data = buf.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)
        elif self.path == "/journal":
            html = render_journal().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/drift":
            html = render_drift().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        elif self.path.startswith("/thumb/"):
            uuid = self.path[7:]
            fpath = RENDERED_DIR / "thumb" / "jpeg" / f"{uuid}.jpg"
            if fpath.exists():
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(fpath.read_bytes())
            else:
                self.send_error(404)
        elif self.path == "/blind-test":
            html = render_blind_test().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        elif self.path.startswith("/blind/"):
            fname = self.path[7:]
            fpath = BLIND_TEST_DIR / fname
            if fpath.exists() and fpath.suffix in (".jpg", ".jpeg", ".png"):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(fpath.read_bytes())
            else:
                self.send_error(404)
        else:
            html = PAGE_HTML.replace("%%POLL_MS%%", "5000")
            html = html.replace("%%API_URL%%", "/api/stats")
            html = html.replace("%%INLINE_DATA%%", "null")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())

    def log_message(self, fmt, *args):
        pass


def serve(port):
    # type: (int) -> None
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Live dashboard: http://localhost:{port}")
    print(f"  /journal     — Journal de Bord")
    print(f"  /drift       — Vector drift exploration")
    print(f"  /blind-test  — Enhancement blind test")
    print("Polling DB every 5s. Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


# ---------------------------------------------------------------------------
# Static generation
# ---------------------------------------------------------------------------

def generate_static():
    """Write a self-contained static HTML file with embedded data."""
    stats = get_stats()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = PAGE_HTML.replace("%%POLL_MS%%", "0")
    html = html.replace("%%API_URL%%", "inline")
    html = html.replace("%%INLINE_DATA%%", json.dumps(stats))
    html = html.replace('animation: blink 2s infinite;', 'display: none;')
    # Add generation timestamp to subtitle
    html = html.replace(
        'System Dashboard</p>',
        f'System Dashboard &mdash; snapshot {ts}</p>',
    )
    # Sidebar: make links work as anchors only (no server routes on GitHub Pages)
    html = html.replace('href="/readme"', 'href="https://github.com/LAEH/MADphotos#readme"')
    html = html.replace('href="/journal"', 'href="https://github.com/LAEH/MADphotos/blob/main/docs/journal.md"')
    html = html.replace('href="/mosaics"', 'href="#sec-storage"')
    html = html.replace('href="/instructions"', 'href="#sec-runs"')
    html = html.replace('href="/drift"', 'href="#"')
    html = html.replace('href="/blind-test"', 'href="#"')
    # Hero mosaic: point to local file for GitHub Pages
    html = html.replace('src="/mosaic-hero"', 'src="hero-mosaic.jpg"')
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html)
    print(f"Wrote {OUT_PATH} ({len(html):,} bytes) — snapshot {ts}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--serve" in sys.argv:
        idx = sys.argv.index("--serve")
        port = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit() else 8080
        serve(port)
    else:
        generate_static()
