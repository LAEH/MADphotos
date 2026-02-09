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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
VECTOR_PATH = PROJECT_ROOT / "images" / "vectors.lance"
OUT_PATH = PROJECT_ROOT / "frontend" / "state" / "state.html"
MOSAIC_DIR = PROJECT_ROOT / "images" / "rendered" / "mosaics"


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
        row = conn.execute("SELECT ROUND(AVG(score),2), MIN(score), MAX(score) FROM aesthetic_scores").fetchone()
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

    # Aesthetic histogram (score distribution)
    aesthetic_histogram = []
    try:
        aesthetic_histogram = [
            {"bucket": r[0], "count": r[1]}
            for r in conn.execute(
                "SELECT ROUND(score, 1) as bucket, COUNT(*) "
                "FROM aesthetic_scores GROUP BY bucket ORDER BY bucket"
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
            "FROM pipeline_runs "
            "WHERE images_processed > 0 OR images_failed > 0 "
            "ORDER BY started_at DESC LIMIT 15"
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

    # ── Advanced signal counts (OCR, captions, emotions, style) ─
    style_count = 0
    top_styles = []  # type: list
    ocr_images = 0
    ocr_texts = 0
    caption_count = 0
    emotion_count = 0
    top_emotions = []  # type: list
    aspect_ratios = []  # type: list
    try:
        style_count = conn.execute("SELECT COUNT(*) FROM style_classification").fetchone()[0]
        top_styles = [{"name": r[0], "count": r[1]} for r in conn.execute(
            "SELECT style, COUNT(*) FROM style_classification GROUP BY style ORDER BY COUNT(*) DESC LIMIT 12").fetchall()]
    except Exception:
        pass
    try:
        ocr_images = conn.execute("SELECT COUNT(DISTINCT image_uuid) FROM ocr_detections").fetchone()[0]
        ocr_texts = conn.execute("SELECT COUNT(*) FROM ocr_detections WHERE text != ''").fetchone()[0]
    except Exception:
        pass
    try:
        caption_count = conn.execute("SELECT COUNT(*) FROM image_captions").fetchone()[0]
    except Exception:
        pass
    try:
        emotion_count = conn.execute("SELECT COUNT(DISTINCT image_uuid) FROM facial_emotions").fetchone()[0]
        top_emotions = [{"name": r[0], "count": r[1]} for r in conn.execute(
            "SELECT dominant_emotion, COUNT(*) FROM facial_emotions GROUP BY dominant_emotion ORDER BY COUNT(*) DESC").fetchall()]
    except Exception:
        pass
    try:
        ratio_rows = conn.execute("""
            SELECT
                CASE
                    WHEN CAST(pixel_width AS REAL) / NULLIF(pixel_height, 0) > 1.1 THEN 'Landscape'
                    WHEN CAST(pixel_width AS REAL) / NULLIF(pixel_height, 0) < 0.9 THEN 'Portrait'
                    ELSE 'Square'
                END AS ratio_type,
                COUNT(*) as cnt
            FROM exif_metadata
            WHERE pixel_width > 0 AND pixel_height > 0
            GROUP BY ratio_type ORDER BY cnt DESC
        """).fetchall()
        aspect_ratios = [{"name": r[0], "count": r[1]} for r in ratio_rows]
    except Exception:
        pass

    # ── V2 Signals ──────────────────────────────────────────
    v2_signals = {}
    for tbl_name in ['aesthetic_scores_v2', 'florence_captions', 'segmentation_masks',
                      'open_detections', 'image_tags', 'foreground_masks',
                      'pose_detections', 'saliency_maps', 'face_identities']:
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl_name}").fetchone()[0]
            uuids = conn.execute(f"SELECT COUNT(DISTINCT image_uuid) FROM {tbl_name}").fetchone()[0]
            v2_signals[tbl_name] = {"rows": cnt, "images": uuids}
        except Exception:
            v2_signals[tbl_name] = {"rows": 0, "images": 0}

    # Aesthetic v2 stats
    aesthetic_v2_count = v2_signals.get('aesthetic_scores_v2', {}).get('images', 0)
    aesthetic_v2_labels = []
    try:
        aesthetic_v2_labels = [
            {"name": r[0] or "unlabeled", "count": r[1]}
            for r in conn.execute(
                "SELECT score_label, COUNT(*) as cnt FROM aesthetic_scores_v2 "
                "GROUP BY score_label ORDER BY cnt DESC"
            ).fetchall()
        ]
    except Exception:
        pass

    # Top image tags
    top_tags = []
    try:
        # Parse pipe-separated tags and count
        tag_rows = conn.execute("SELECT tags FROM image_tags WHERE tags IS NOT NULL").fetchall()
        tag_counts = {}
        for row in tag_rows:
            for tag in row[0].split(" | "):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = [{"name": k, "count": v} for k, v in
                    sorted(tag_counts.items(), key=lambda x: -x[1])[:30]]
    except Exception:
        pass

    # Top open detection labels
    top_open_labels = []
    try:
        top_open_labels = [
            {"name": r[0], "count": r[1]}
            for r in conn.execute(
                "SELECT label, COUNT(*) as cnt FROM open_detections "
                "GROUP BY label ORDER BY cnt DESC LIMIT 20"
            ).fetchall()
        ]
    except Exception:
        pass

    # Total models completed (17 displayed models + v2)
    # Use 'processed' for detection models (images with + without detections)
    face_processed = signals.get('face_detections', {}).get('processed', signals.get('face_detections', {}).get('images', 0))
    obj_processed = signals.get('object_detections', {}).get('processed', signals.get('object_detections', {}).get('images', 0))
    face_images_with = signals.get('face_detections', {}).get('images', 0)
    # Each (count, denominator) pair — most use total, Facial Emotions uses face count
    model_checks = [
        (analyzed, total),           # 01 Gemini
        (pixel_analyzed, total),     # 02 Pixel Analysis
        (vector_count, total),       # 03 DINOv2
        (vector_count, total),       # 04 SigLIP
        (vector_count, total),       # 05 CLIP
        (face_processed, total),     # 06 YuNet
        (obj_processed, total),      # 07 YOLOv8n
        (aesthetic_count, total),    # 08 NIMA
        (depth_count, total),        # 09 Depth Anything
        (scene_count, total),        # 10 Places365
        (style_count, total),        # 11 Style Net
        (caption_count, total),      # 12 BLIP
        (ocr_images, total),         # 13 EasyOCR
        (emotion_count, face_images_with or 1),  # 14 Facial Emotions (vs face images)
        (enhancement_count, total),  # 15 Enhancement Engine
        (signals.get('dominant_colors', {}).get('images', 0), total),  # 16 K-means LAB
        (signals.get('exif_metadata', {}).get('images', 0), total),    # 17 EXIF Parser
        # V2 models
        (aesthetic_v2_count, total),  # 18 Aesthetic v2
        (v2_signals.get('florence_captions', {}).get('images', 0), total),     # 19 Florence-2
        (v2_signals.get('segmentation_masks', {}).get('images', 0), total),    # 20 SAM
        (v2_signals.get('open_detections', {}).get('images', 0), total),       # 21 Grounding DINO
        (v2_signals.get('image_tags', {}).get('images', 0), total),            # 22 RAM++ / CLIP tags
        (v2_signals.get('foreground_masks', {}).get('images', 0), total),      # 23 rembg
        (v2_signals.get('saliency_maps', {}).get('images', 0), total),         # 24 Saliency
    ]
    models_complete = sum(1 for count, denom in model_checks if denom > 0 and count >= denom)

    # Total signals extracted across all models
    total_signals = sum([
        signals.get('exif_metadata', {}).get('rows', 0),
        signals.get('dominant_colors', {}).get('rows', 0),
        signals.get('face_detections', {}).get('rows', 0),
        signals.get('object_detections', {}).get('rows', 0),
        signals.get('image_hashes', {}).get('rows', 0),
        aesthetic_count, depth_count, scene_count, style_count,
        caption_count, ocr_texts, emotion_count,
        pixel_analyzed, enhancement_count, vector_count * 3,
        analyzed,
        # V2 signals
        v2_signals.get('aesthetic_scores_v2', {}).get('rows', 0),
        v2_signals.get('florence_captions', {}).get('rows', 0),
        v2_signals.get('segmentation_masks', {}).get('rows', 0),
        v2_signals.get('open_detections', {}).get('rows', 0),
        v2_signals.get('image_tags', {}).get('rows', 0),
        v2_signals.get('foreground_masks', {}).get('rows', 0),
        v2_signals.get('pose_detections', {}).get('rows', 0),
        v2_signals.get('saliency_maps', {}).get('rows', 0),
        v2_signals.get('face_identities', {}).get('rows', 0),
    ])

    # ── Disk usage ───────────────────────────────────────────
    db_size = os.path.getsize(str(DB_PATH)) if DB_PATH.exists() else 0
    web_json_path = PROJECT_ROOT / "frontend" / "show" / "data" / "photos.json"
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
        "aesthetic_histogram": aesthetic_histogram,
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
        "style_count": style_count,
        "top_styles": top_styles,
        "ocr_images": ocr_images,
        "ocr_texts": ocr_texts,
        "caption_count": caption_count,
        "emotion_count": emotion_count,
        "top_emotions": top_emotions,
        "aspect_ratios": aspect_ratios,
        "models_complete": models_complete,
        "total_signals": total_signals,
        # V2 signals
        "v2_signals": v2_signals,
        "aesthetic_v2_count": aesthetic_v2_count,
        "aesthetic_v2_labels": aesthetic_v2_labels,
        "top_tags": top_tags,
        "top_open_labels": top_open_labels,
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
    --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
    --duration-fast: 150ms;
    --duration-normal: 250ms;

    /* ── Apple system colors (canonical names from Show) ── */
    --system-blue: #007AFF;
    --system-green: #34C759;
    --system-indigo: #5856D6;
    --system-orange: #FF9500;
    --system-pink: #FF2D55;
    --system-purple: #AF52DE;
    --system-red: #FF3B30;
    --system-teal: #5AC8FA;
    --system-yellow: #FFCC00;
    --system-mint: #00C7BE;
    --system-cyan: #32ADE6;
    --system-brown: #A2845E;
    /* Legacy aliases */
    --apple-blue: var(--system-blue);
    --apple-green: var(--system-green);
    --apple-indigo: var(--system-indigo);
    --apple-orange: var(--system-orange);
    --apple-pink: var(--system-pink);
    --apple-purple: var(--system-purple);
    --apple-red: var(--system-red);
    --apple-teal: var(--system-teal);
    --apple-yellow: var(--system-yellow);
    --apple-mint: var(--system-mint);
    --apple-cyan: var(--system-cyan);
    --apple-brown: var(--system-brown);

    /* ── Spacing Scale (from Show) ── */
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-6: 24px;
    --space-8: 32px;
    --space-10: 40px;
    --space-12: 48px;
    --space-16: 64px;

    /* ── Type Scale (from Show) ── */
    --text-xs: 11px;
    --text-sm: 13px;
    --text-base: 15px;
    --text-lg: 17px;
    --text-xl: 20px;
    --text-2xl: 22px;
    --text-3xl: 28px;
    --text-4xl: 34px;

    /* ── Sidebar width ── */
    --sidebar-w: 220px;
  }

  /* ── Light theme (default) ── */
  [data-theme="light"] {
    --bg: #F5F5F7;
    --bg-secondary: #FFFFFF;
    --bg-elevated: #FFFFFF;
    --bg-tertiary: #F2F2F7;
    --fg: #1D1D1F;
    --text: #1D1D1F;
    --fg-secondary: #3A3A3C;
    --text-dim: #3A3A3C;
    --muted: #86868B;
    --text-muted: #86868B;
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
    --bg-elevated: #2C2C2E;
    --bg-tertiary: #3A3A3C;
    --fg: #F5F5F7;
    --text: #F5F5F7;
    --fg-secondary: #D1D1D6;
    --text-dim: #D1D1D6;
    --muted: #98989D;
    --text-muted: #98989D;
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

  /* ═══ AI ANIMATIONS ═══ */
  @keyframes ai-shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }
  @keyframes fade-up {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes ai-gradient {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
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
    .hero { min-height: 200px; border-radius: var(--radius-lg); }
    .hero-title { font-size: 28px; }
    .hero-content { padding: var(--space-4); }
    .hero-count { font-size: var(--text-base); }
    .hero-tagline, .hero-mission { display: none; }
  }
  @media (max-width: 440px) {
    .hero { min-height: 160px; border-radius: var(--radius-md); margin-bottom: var(--space-6); }
    .hero-title { font-size: 24px; }
    .hero-content { padding: var(--space-3); }
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
  .sidebar::after {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 2px;
    height: 100%;
    background: linear-gradient(180deg,
      var(--apple-blue) 0%,
      var(--apple-purple) 35%,
      var(--apple-pink) 65%,
      var(--apple-orange) 100%
    );
    opacity: 0.35;
    background-size: 100% 300%;
    animation: ai-gradient 8s ease infinite;
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
    padding-left: calc(var(--space-5) - 3px);
    border-left: 3px solid transparent;
    color: var(--muted);
    text-decoration: none;
    font-size: var(--text-sm);
    line-height: var(--leading-tight);
    border-radius: 0;
    transition: background var(--duration-fast) var(--ease-default),
                color var(--duration-fast) var(--ease-default),
                border-color var(--duration-fast) var(--ease-default);
  }
  .sidebar a:hover {
    background: var(--sidebar-active-bg);
    color: var(--fg);
  }
  .sidebar a.active {
    color: var(--fg);
    font-weight: 600;
    background: var(--sidebar-active-bg);
    border-left-color: var(--apple-blue);
  }
  .sidebar a.sb-sub {
    padding-left: var(--space-8);
    font-size: var(--text-xs);
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
    padding: var(--space-4);
    max-width: 1120px;
    min-width: 0;
    margin: 0 auto;
    width: 100%;
    animation: fade-up 0.5s var(--ease-default) both;
  }

  /* ── Mobile hamburger ── */
  .sb-hamburger {
    display: none;
    align-items: center;
    justify-content: center;
    width: 36px; height: 36px;
    background: none; border: none; cursor: pointer;
    color: var(--fg); font-size: 20px;
    border-radius: var(--radius-sm);
    transition: background var(--duration-fast);
  }
  .sb-hamburger:hover { background: var(--sidebar-active-bg); }

  @media (max-width: 900px) {
    body { flex-direction: column; }
    .sidebar {
      width: 100%; min-width: unset; height: auto; position: sticky; top: 0;
      z-index: 100; border-right: none; border-bottom: 1px solid var(--border);
      flex-direction: row; flex-wrap: wrap; gap: 0; padding: var(--space-2) var(--space-3);
      backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
      background: color-mix(in srgb, var(--sidebar-bg) 85%, transparent);
    }
    .sidebar .sb-title {
      width: auto; border-bottom: none; padding: 0 var(--space-2) 0 0;
      margin-bottom: 0; font-size: var(--text-base);
    }
    .sb-hamburger { display: flex; margin-left: auto; }
    .sidebar > a, .sidebar .sb-group, .sidebar .sb-sep,
    .sidebar .sb-bottom, .sidebar .sb-collapsible,
    .sidebar .sb-toggle { display: none; }
    .sidebar.open > a { display: flex; width: 100%; }
    .sidebar.open .sb-sep { display: block; width: 100%; }
    .sidebar.open .sb-group { display: block; width: 100%; }
    .sidebar.open .sb-bottom { display: block; width: 100%; }
    .sidebar.open .sb-toggle { display: block; width: 100%; }
    .main-content { padding: var(--space-4); }
  }

  @media (min-width: 901px) {
    .main-content { padding: var(--space-10) var(--space-8); }
  }

  /* ═══ TYPOGRAPHY ═══ */
  h1 {
    font-family: var(--font-display);
    font-size: 42px;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.1;
    margin-bottom: var(--space-1);
    color: var(--fg);
  }
  .subtitle {
    color: var(--muted);
    font-size: var(--text-sm);
    margin-bottom: var(--space-3);
  }
  .manifesto {
    font-size: var(--text-sm);
    line-height: var(--leading-relaxed);
    color: var(--fg-secondary);
    margin-bottom: 0;
  }
  .manifesto strong { color: var(--fg); font-weight: 700; }

  /* ═══ HERO HEADER ═══ */
  .state-hero {
    margin-bottom: var(--space-8);
    animation: fade-up 0.6s var(--ease-default) both;
  }
  .state-hero h1 { margin-bottom: var(--space-1); }
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
    position: relative;
  }
  .section-title::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0;
    width: 60px;
    height: 2px;
    background: linear-gradient(90deg, var(--apple-blue), var(--apple-purple));
    border-radius: 1px;
    opacity: 0.6;
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

  /* ═══ ELEMENT GRID (model intelligence — compact) ═══ */
  .el-section-title {
    font-family: var(--font-display); font-size: var(--text-lg); font-weight: 700;
    letter-spacing: var(--tracking-tight); margin-bottom: var(--space-1);
  }
  .el-section-sub { display: none; }
  .el-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 6px;
  }
  .el-card.status-done {
    border-color: var(--border);
  }
  .el-card.status-active {
    border-color: var(--apple-blue);
    background: color-mix(in srgb, var(--apple-blue) 4%, var(--card-bg));
  }
  .el-card.status-pending {
    opacity: 0.35;
  }
  .el-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 8px 10px;
    position: relative;
    transition: transform var(--duration-fast), box-shadow var(--duration-fast);
    animation: fade-up 0.4s var(--ease-default) both;
  }
  .el-card:nth-child(n+4) { animation-delay: 60ms; }
  .el-card:nth-child(n+7) { animation-delay: 120ms; }
  .el-card:nth-child(n+10) { animation-delay: 180ms; }
  .el-card:nth-child(n+13) { animation-delay: 240ms; }
  .el-card:hover { transform: translateY(-1px); box-shadow: var(--shadow-sm); }
  .el-card .el-num {
    position: absolute; top: 4px; right: 6px;
    font-family: var(--font-mono); font-size: 8px;
    color: var(--muted); font-weight: 600; opacity: 0.6;
  }
  .el-card .el-model {
    font-family: var(--font-display); font-size: 11px; font-weight: 700;
    color: var(--fg); margin-bottom: 0; padding-right: var(--space-4);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .el-card .el-tech {
    font-family: var(--font-mono); font-size: 8px; color: var(--muted);
    letter-spacing: 0.02em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .el-card .el-desc { display: none; }
  .el-card .el-count {
    font-family: var(--font-display); font-size: var(--text-base); font-weight: 800;
    color: var(--fg); line-height: 1; font-variant-numeric: tabular-nums;
    margin-top: 4px;
  }
  .el-card .el-bar {
    height: 2px; background: var(--border);
    border-radius: 1px; margin-top: 4px; overflow: hidden;
  }
  .el-card .el-fill {
    height: 100%; border-radius: 1px;
    background: var(--fg);
    transition: width 1s var(--ease-default);
  }
  .el-card.status-done .el-fill { background: var(--muted); }
  .el-card.status-active .el-fill { background: var(--apple-blue); }
  .el-card .el-pct { display: none; }
  .el-badge {
    display: inline-block; font-size: 8px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.04em;
    padding: 0 4px; border-radius: 2px;
    vertical-align: middle; margin-left: 3px;
  }
  .el-badge.done { background: color-mix(in srgb, var(--apple-green) 15%, transparent); color: var(--apple-green); font-weight: 700; }
  .el-badge.active { background: color-mix(in srgb, var(--apple-blue) 15%, transparent); color: var(--apple-blue); font-weight: 700; animation: pulse-badge 2s ease-in-out infinite; }
  .el-badge.pending { background: var(--hover-overlay); color: var(--muted); }
  @keyframes pulse-badge { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
  @media (max-width: 600px) {
    .el-grid { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
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
  .two-col { display: grid; grid-template-columns: 1fr; gap: var(--space-6); }
  .three-col { display: grid; grid-template-columns: 1fr; gap: var(--space-6); }

  /* Mobile-first responsive */
  h1 { font-size: var(--text-3xl); }
  @media (max-width: 640px) {
    h1 { font-size: var(--text-2xl); }
    .el-grid { grid-template-columns: 1fr; }
  }
  @media (min-width: 641px) and (max-width: 900px) {
    .el-grid { grid-template-columns: repeat(2, 1fr); }
  }
  @media (min-width: 640px) {
    h1 { font-size: 42px; }
  }

  @media (min-width: 768px) {
    .two-col { grid-template-columns: 1fr 1fr; gap: var(--space-8); }
    .three-col { grid-template-columns: 1fr 1fr 1fr; }
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
  .tag .tag-label { font-weight: 500; color: var(--fg-secondary); text-transform: capitalize; }
  .tag .tag-count {
    font-weight: 700;
    font-size: 10px;
    font-variant-numeric: tabular-nums;
    color: var(--fg);
  }
  .signal-group {
    margin-bottom: var(--space-6);
  }
  .signal-group:last-child { margin-bottom: 0; }
  .signal-group-label {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--fg);
    margin-bottom: var(--space-3);
    padding-bottom: var(--space-1);
    border-bottom: 1px solid var(--border);
  }
  /* Only icon gets group color — border stays default, count stays black */
  .tag-cat-scene .tag-icon svg { color: var(--apple-teal); }
  .tag-cat-scene-env .tag-icon svg { color: color-mix(in srgb, var(--apple-teal) 70%, var(--apple-green)); }
  .tag-cat-scene-set .tag-icon svg { color: color-mix(in srgb, var(--apple-teal) 60%, var(--apple-blue)); }
  .tag-cat-scene-obj .tag-icon svg { color: color-mix(in srgb, var(--apple-teal) 50%, var(--apple-green)); }
  .tag-cat-scene-loc .tag-icon svg { color: color-mix(in srgb, var(--apple-teal) 40%, var(--apple-blue)); }

  .tag-cat-style .tag-icon svg { color: var(--apple-purple); }
  .tag-cat-style-emo .tag-icon svg { color: var(--apple-pink); }
  .tag-cat-style-grad .tag-icon svg { color: color-mix(in srgb, var(--apple-purple) 70%, var(--apple-blue)); }
  .tag-cat-style-cls .tag-icon svg { color: color-mix(in srgb, var(--apple-purple) 60%, var(--apple-pink)); }
  .tag-cat-style-cast .tag-icon svg { color: color-mix(in srgb, var(--apple-purple) 50%, var(--apple-orange)); }
  .tag-cat-style-temp .tag-icon svg { color: color-mix(in srgb, var(--apple-purple) 40%, var(--apple-orange)); }
  .tag-cat-style-exp .tag-icon svg { color: color-mix(in srgb, var(--apple-purple) 50%, var(--apple-blue)); }

  .tag-cat-depth .tag-icon svg { color: var(--apple-indigo); }
  .tag-cat-depth-comp .tag-icon svg { color: color-mix(in srgb, var(--apple-indigo) 70%, var(--apple-blue)); }
  .tag-cat-depth-ratio .tag-icon svg { color: color-mix(in srgb, var(--apple-indigo) 50%, var(--apple-teal)); }

  .tag-cat-camera .tag-icon svg { color: var(--muted); }
  .tag-cat-camera-time .tag-icon svg { color: var(--fg-secondary); }
  .tag-cat-camera-enh .tag-icon svg { color: var(--muted); opacity: 0.8; }
  .tag-cat-camera-rot .tag-icon svg { color: var(--fg-secondary); opacity: 0.8; }

  /* Color dot inside tags (for dominant colors) */
  .tag .tag-cdot {
    display: inline-block;
    width: 14px; height: 14px;
    border-radius: var(--radius-full);
    border: 1px solid var(--border-strong);
    flex-shrink: 0;
  }

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
  <button class="sb-hamburger" onclick="document.getElementById('sidebar').classList.toggle('open')" aria-label="Menu">&#9776;</button>
  <div class="sb-group sb-toggle" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('sb-collapsed')">
    State <span class="sb-arrow">&#9656;</span>
  </div>
  <div class="sb-collapsible">
    <a href="/" class="active sb-sub">Overview</a>
    <a href="#sec-gemini" class="sb-sub">Models</a>
    <a href="#sec-signals" class="sb-sub">Signals</a>
    <a href="#sec-vectors" class="sb-sub">Vector Store</a>
    <a href="#sec-cameras" class="sb-sub">Camera Fleet</a>
    <a href="#sec-tiers" class="sb-sub">Render Tiers</a>
    <a href="#sec-storage" class="sb-sub">Storage</a>
    <a href="#sec-runs" class="sb-sub">Pipeline Runs</a>
    <a href="#sec-sample" class="sb-sub">Sample Output</a>
  </div>
  <a href="/journal">Journal de Bord</a>
  <a href="/instructions">System Instructions</a>
  <div class="sb-sep"></div>
  <div class="sb-group">Experiments</div>
  <a href="/drift">Similarity</a>
  <a href="/creative-drift">Drift</a>
  <a href="/blind-test">Blind Test</a>
  <a href="/mosaics">Mosaics</a>
  <div class="sb-bottom">
    <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">
      <span class="theme-icon" id="themeIcon">&#9790;</span>
      <span id="themeLabel">Dark Mode</span>
    </button>
  </div>
</nav>

<div class="main-content">

<div class="state-hero">
  <h1>System State</h1>
  <p class="subtitle" id="subtitle">System Dashboard</p>
  <p class="manifesto">We started with 9,011 raw images and zero metadata.<br>We will create the best UX UIs on photos.<br>Game ON.</p>
</div>

<!-- ═══ MODELS ═══ -->
<div class="section" id="sec-gemini" style="margin-bottom:var(--space-8);">
  <div class="section-title">Models</div>
  <div class="el-section-sub" id="el-sub">17 models &middot; every image</div>
  <div class="el-grid" id="el-grid"></div>
</div>

<!-- ═══ SIGNALS — All tags grouped by meaning ═══ -->
<div class="section" id="sec-signals">
  <div class="section-title">Signals</div>

  <!-- Scene & Setting -->
  <div class="signal-group">
    <div class="signal-group-label">Scene & Setting</div>
    <div id="pills-scene-all" class="tag-row"></div>
  </div>

  <div class="signal-group">
    <div class="signal-group-label">Visual Style</div>
    <div id="pills-style-all" class="tag-row"></div>
  </div>

  <div class="signal-group">
    <div class="signal-group-label">Structure</div>
    <div id="pills-structure-all" class="tag-row"></div>
  </div>

  <div class="signal-group">
    <div class="signal-group-label">Context</div>
    <div id="pills-context-all" class="tag-row"></div>
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

<!-- ═══ RENDER TIERS ═══ -->
<div class="section" id="sec-tiers">
  <div class="section-title">Render Tiers</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Tier / Format</th><th class="num">Files</th><th class="num">Size</th></tr></thead>
    <tbody id="tbl-tiers"></tbody>
  </table></div>
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
    var s = localStorage.getItem('mad-theme');
    if (s) return s;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
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

  function tags(data, containerId, iconKey, category) {
    var container = el(containerId);
    if (!container) return;
    if (!data || !data.length) {
      container.innerHTML = '<span style="color:var(--muted);font-size:var(--text-xs)">No data</span>';
      return;
    }
    var svg = IC[iconKey] || IC.eye;
    var catClass = category ? ' tag-cat-' + category : '';
    container.innerHTML = data.map(function(r) {
      var label = r.name || r.value || "\u2014";
      return '<div class="tag' + catClass + '">' +
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

  /* Inline tag HTML builders (return strings, don't set innerHTML) */
  function tagHtml(data, iconKey, category) {
    if (!data || !data.length) return '';
    var svg = IC[iconKey] || IC.eye;
    var catClass = category ? ' tag-cat-' + category : '';
    return data.map(function(r) {
      var label = r.name || r.value || "\u2014";
      return '<div class="tag' + catClass + '">' +
        '<span class="tag-icon">' + svg + '</span>' +
        '<span class="tag-label">' + label + '</span>' +
        '<span class="tag-count">' + fmt(r.count) + '</span>' +
        '</div>';
    }).join("");
  }
  function colorTagHtml(data) {
    if (!data || !data.length) return '';
    return data.map(function(c) {
      var hex = c.hex || '#999';
      return '<div class="tag">' +
        '<span class="tag-cdot" style="background:' + hex + '"></span>' +
        '<span class="tag-count">' + fmt(c.count) + '</span>' +
        '</div>';
    }).join("");
  }
  function setTagRow(id, html) {
    var c = el(id);
    if (c) c.innerHTML = html || '<span style="color:var(--muted);font-size:var(--text-xs)">No data</span>';
  }

  /* ════════════════════════════════════════════════════════════
     UPDATE — main data binding
     ════════════════════════════════════════════════════════════ */
  function update(d) {
    el("subtitle").innerHTML =
      '<span class="live-dot"></span>' + d.timestamp;
    el("footer-ts").textContent = d.timestamp;

    /* ── Model intelligence grid ── */
    var mc = d.models_complete || 0;
    el("el-sub").textContent = fmt(d.total) + " images \u00D7 17 models = " + fmt(d.total_signals || 0) + " signals \u2014 " + mc + " complete";
    var sigFD = d.signals && d.signals.face_detections ? d.signals.face_detections : {rows:0, images:0};
    var sigOD = d.signals && d.signals.object_detections ? d.signals.object_detections : {rows:0, images:0};
    var sigDC = d.signals && d.signals.dominant_colors ? d.signals.dominant_colors : {rows:0, images:0};
    var sigEX = d.signals && d.signals.exif_metadata ? d.signals.exif_metadata : {rows:0, images:0};
    var models = [
      {n:'01', name:'Gemini 2.5 Pro', tech:'Vertex AI \u00B7 Google Cloud', desc:'Structured per-image analysis: vibes, exposure, composition, grading style, rotation, per-image edit prompts, semantic pops, alt text', count:d.analyzed},
      {n:'02', name:'Pixel Analysis', tech:'Python \u00B7 Pillow \u00B7 NumPy', desc:'Mean luminance, white balance shift (R/B channels), noise estimation, shadow/highlight clipping %, contrast ratio, estimated color temperature', count:d.pixel_analyzed},
      {n:'03', name:'DINOv2', tech:'PyTorch \u00B7 Meta FAIR \u00B7 ViT-B/14', desc:'Self-supervised vision transformer. 768-dim embeddings capturing composition, texture, spatial layout. The artistic eye of similarity search', count:d.vector_count},
      {n:'04', name:'SigLIP', tech:'PyTorch \u00B7 Google \u00B7 ViT-B/16', desc:'Sigmoid-loss image-language pre-training. 768-dim embeddings enabling text-to-image search across the entire collection', count:d.vector_count},
      {n:'05', name:'CLIP', tech:'PyTorch \u00B7 OpenAI \u00B7 ViT-B/32', desc:'Contrastive language-image pre-training. 512-dim embeddings for cross-modal matching, duplicate detection, subject similarity', count:d.vector_count},
      {n:'06', name:'YuNet', tech:'OpenCV DNN \u00B7 ONNX \u00B7 C++', desc:'Lightweight face detector. ' + fmt(d.face_total) + ' faces detected across ' + fmt(sigFD.images) + ' images with bounding box coordinates and confidence scores', count: sigFD.processed || sigFD.images},
      {n:'07', name:'YOLOv8n', tech:'PyTorch \u00B7 Ultralytics \u00B7 COCO', desc:'Real-time object detection. ' + fmt(sigOD.rows) + ' objects detected across 80 COCO classes with bounding boxes and confidence thresholds', count: sigOD.processed || sigOD.images},
      {n:'08', name:'NIMA', tech:'PyTorch \u00B7 TensorFlow origin \u00B7 MobileNet', desc:'Neural Image Assessment. Aesthetic quality scoring on 1\u201310 scale. Collection avg: ' + (d.aesthetic_avg || 0).toFixed(1) + ', range ' + (d.aesthetic_min || 0).toFixed(1) + '\u2013' + (d.aesthetic_max || 0).toFixed(1), count:d.aesthetic_count},
      {n:'09', name:'Depth Anything v2', tech:'PyTorch \u00B7 Hugging Face \u00B7 ViT', desc:'Monocular depth estimation. Near/mid/far zone percentages and depth complexity score per image. No stereo pair needed', count:d.depth_count},
      {n:'10', name:'Places365', tech:'PyTorch \u00B7 MIT CSAIL \u00B7 ResNet-50', desc:'Scene classification across 365 environment categories. Top-3 predictions + indoor/outdoor environment label per image', count:d.scene_count},
      {n:'11', name:'Style Net', tech:'PyTorch \u00B7 Custom classifier', desc:'Photographic style classification: street, portrait, landscape, architecture, macro, abstract, documentary, still life', count:d.style_count},
      {n:'12', name:'BLIP', tech:'PyTorch \u00B7 Salesforce \u00B7 ViT+LLM', desc:'Bootstrapped Language-Image Pre-training. Natural language captions generated per image for search and accessibility', count:d.caption_count},
      {n:'13', name:'EasyOCR', tech:'PyTorch \u00B7 CRAFT + CRNN', desc:'Text detection and recognition. ' + fmt(d.ocr_texts || 0) + ' text regions found across ' + fmt(d.ocr_images || 0) + ' images. English language model on CPU', count:d.ocr_images || 0},
      {n:'14', name:'Facial Emotions', tech:'PyTorch \u00B7 FER \u00B7 CNN', desc:'Emotion recognition on detected faces. 7 classes: angry, disgust, fear, happy, sad, surprise, neutral', count:d.emotion_count || 0},
      {n:'15', name:'Enhancement Engine', tech:'Python \u00B7 Pillow \u00B7 Camera-aware', desc:'6-step per-image editing pipeline: white balance, exposure, shadows/highlights, contrast, saturation, sharpening. Parameters derived from pixel analysis + camera body', count:d.enhancement_count},
      {n:'16', name:'K-means LAB', tech:'Python \u00B7 scikit-learn \u00B7 LAB space', desc:'Dominant color extraction via K-means clustering in perceptually uniform CIELAB space. ' + fmt(sigDC.rows) + ' color clusters with names mapped from nearest CSS4 colors', count:sigDC.images},
      {n:'17', name:'EXIF Parser', tech:'Python \u00B7 Pillow \u00B7 piexif', desc:'Full metadata extraction: camera body, lens, ISO, shutter speed, aperture, focal length, date/time, GPS coordinates (' + fmt(d.exif_gps || 0) + ' geolocated)', count:sigEX.images}
    ];
    var elHtml = models.map(function(m) {
      var pctVal = d.total > 0 ? (m.count / d.total * 100) : 0;
      var status = pctVal >= 99.5 ? 'done' : pctVal > 0 ? 'active' : 'pending';
      var bdg = status === 'done' ? '<span class="el-badge done">\u2713</span>' :
                status === 'active' ? '<span class="el-badge active">' + pctVal.toFixed(0) + '%</span>' :
                '<span class="el-badge pending">\u2014</span>';
      return '<div class="el-card status-' + status + '">' +
        '<div class="el-num">' + m.n + '</div>' +
        '<div class="el-model">' + m.name + '</div>' +
        '<div class="el-tech">' + m.tech + '</div>' +
        '<div class="el-desc">' + m.desc + '</div>' +
        '<div class="el-count">' + fmt(m.count) + ' ' + bdg + '</div>' +
        '<div class="el-bar"><div class="el-fill" style="width:' + Math.min(pctVal, 100) + '%"></div></div>' +
        '<div class="el-pct">' + fmt(m.count) + ' / ' + fmt(d.total) + '</div>' +
        '</div>';
    }).join('');
    el('el-grid').innerHTML = elHtml;

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

    /* Signal extraction table removed — data shown in model cards */

    /* ── Signals (flat inline layout, leaf categories removed) ── */

    /* Scene & Setting — teal family */
    setTagRow('pills-scene-all',
      tagHtml(d.top_scenes, 'scene', 'scene') +
      tagHtml(d.scene_environments, 'home', 'scene-env') +
      tagHtml(d.settings, 'scene', 'scene-set') +
      tagHtml(d.top_objects || [], 'eye', 'scene-obj') +
      tagHtml(d.location_sources, 'pin', 'scene-loc'));

    /* Visual Style — purple family (no cast / temp / exposure) */
    setTagRow('pills-style-all',
      tagHtml(d.vibes, 'sparkle', 'style') +
      tagHtml(d.top_emotions || [], 'sparkle', 'style-emo') +
      tagHtml(d.grading, 'star', 'style-grad') +
      tagHtml(d.top_styles || [], 'sparkle', 'style-cls') +
      colorTagHtml(d.top_color_names || []));

    /* Structure — composition only (no depth zones / complexity / aspect ratio) */
    setTagRow('pills-structure-all',
      tagHtml(d.composition, 'frame', 'depth-comp'));

    /* Context — camera + time only (no enhancement / rotation) */
    setTagRow('pills-context-all',
      tagHtml(d.subcategories, 'film', 'camera') +
      tagHtml(d.time_of_day, 'sunset', 'camera-time'));

    /* ── Vector store ── */
    el("vector-info").innerHTML =
      fmt(d.vector_count) + ' images \u00D7 3 models \u2014 ' + d.vector_size + ' on disk' +
      (d.vector_count >= d.total ? ' \u2014 <span class="badge done">complete</span>' :
       d.vector_count > 0 ? ' \u2014 <span class="badge partial">' + (d.vector_count / d.total * 100).toFixed(1) + '%</span>' :
       ' \u2014 <span class="badge empty">not started</span>');

    /* ── Render tiers ── */
    el("tbl-tiers").innerHTML = d.tiers.map(function(t) {
      return "<tr><td>" + t.name + "</td><td class='num'>" + fmt(t.count) + "</td><td class='num'>" + t.size_human + "</td></tr>";
    }).join("\n");

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
    --apple-purple: #AF52DE; --apple-pink: #FF2D55; --apple-orange: #FF9500;
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
  @keyframes ai-gradient {{
    0% {{ background-position: 0% 50%; }}
    50% {{ background-position: 100% 50%; }}
    100% {{ background-position: 0% 50%; }}
  }}
  @keyframes fade-up {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to {{ opacity: 1; transform: translateY(0); }}
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
    transition: width var(--duration-normal) var(--ease-default),
                min-width var(--duration-normal) var(--ease-default);
  }}
  .sidebar::after {{
    content: '';
    position: absolute; top: 0; right: 0; width: 2px; height: 100%;
    background: linear-gradient(180deg, var(--apple-blue) 0%, var(--apple-purple) 35%, var(--apple-pink) 65%, var(--apple-orange) 100%);
    opacity: 0.35; background-size: 100% 300%; animation: ai-gradient 8s ease infinite;
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
  }}
  .sidebar a.sb-sub {{ padding-left: var(--space-8); font-size: var(--text-xs); }}
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
  .sb-collapse {{
    display: flex; align-items: center; gap: var(--space-2);
    font-size: var(--text-sm); color: var(--muted); cursor: pointer;
    padding: var(--space-2) 0; background: none; border: none;
    font-family: inherit; width: 100%; transition: color var(--duration-fast);
    margin-bottom: var(--space-2); white-space: nowrap; overflow: hidden;
  }}
  .sb-collapse:hover {{ color: var(--fg); }}
  .sb-expand {{
    display: none; position: fixed; top: var(--space-4); left: var(--space-4);
    z-index: 50; width: 36px; height: 36px; border-radius: var(--radius-sm);
    border: 1px solid var(--border); background: var(--card-bg);
    cursor: pointer; color: var(--muted); box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    align-items: center; justify-content: center; font-size: 18px;
    transition: color var(--duration-fast), box-shadow var(--duration-fast);
  }}
  .sb-expand:hover {{ color: var(--fg); box-shadow: 0 4px 16px rgba(0,0,0,0.15); }}
  body.sb-collapsed .sidebar {{ width: 0; min-width: 0; overflow: hidden; padding: 0; border-right: none; }}
  body.sb-collapsed .sb-expand {{ display: flex; }}
  .sb-hamburger {{
    display: none; align-items: center; justify-content: center;
    width: 36px; height: 36px; background: none; border: none;
    cursor: pointer; color: var(--fg); font-size: 20px;
    border-radius: var(--radius-sm); flex-shrink: 0;
  }}
  .main-content {{
    flex: 1; padding: var(--space-10) var(--space-8);
    max-width: 900px; min-width: 0; margin: 0 auto;
    animation: fade-up 0.5s var(--ease-default) both;
  }}
  @media (max-width: 900px) {{
    body {{ flex-direction: column; }}
    body.sb-collapsed .sidebar {{
      width: 100%; min-width: unset; overflow: visible; padding: var(--space-2) var(--space-3);
      border-right: none; border-bottom: 1px solid var(--border);
    }}
    body.sb-collapsed .sb-expand {{ display: none; }}
    .sb-collapse {{ display: none !important; }}
    .sidebar {{ width: 100%; min-width: unset; height: auto; position: sticky; top: 0;
               z-index: 100; border-right: none; border-bottom: 1px solid var(--border);
               flex-direction: row; flex-wrap: wrap; padding: var(--space-2) var(--space-3);
               backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
               background: color-mix(in srgb, var(--sidebar-bg) 85%, transparent); }}
    .sidebar .sb-title {{ width: auto; border-bottom: none; padding: 0 var(--space-2) 0 0; margin-bottom: 0; font-size: var(--text-base); }}
    .sb-hamburger {{ display: flex; margin-left: auto; }}
    .sidebar > a, .sidebar .sb-group, .sidebar .sb-sep, .sidebar .sb-bottom {{ display: none; }}
    .sidebar.open > a {{ display: flex; width: 100%; }}
    .sidebar.open .sb-sep {{ display: block; width: 100%; }}
    .sidebar.open .sb-bottom {{ display: block; width: 100%; }}
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
<button class="sb-expand" onclick="toggleSidebar()" title="Show sidebar">&#9776;</button>
<nav class="sidebar" id="sidebar">
  <div class="sb-title">MADphotos</div>
  <button class="sb-hamburger" onclick="document.getElementById('sidebar').classList.toggle('open')" aria-label="Menu">&#9776;</button>
  <a href="/"{_active("status")}>State</a>
  <a href="/journal"{_active("journal")}>Journal de Bord</a>
  <a href="/instructions"{_active("instructions")}>System Instructions</a>
  <div class="sb-sep"></div>
  <div class="sb-group">Experiments</div>
  <a href="/drift"{_active("drift")}>Similarity</a>
  <a href="/creative-drift"{_active("creative-drift")}>Drift</a>
  <a href="/blind-test"{_active("blind-test")}>Blind Test</a>
  <a href="/mosaics"{_active("mosaics")}>Mosaics</a>
  <div class="sb-sep"></div>
  <div class="sb-bottom">
    <button class="sb-collapse" onclick="toggleSidebar()">&#x276E; Hide sidebar</button>
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
  function getTheme() {{
    var s = localStorage.getItem('mad-theme');
    if (s) return s;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }}
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
  window.toggleSidebar = function() {{
    document.body.classList.toggle('sb-collapsed');
    localStorage.setItem('mad-sidebar', document.body.classList.contains('sb-collapsed') ? 'collapsed' : 'expanded');
  }};
  applyTheme(getTheme());
  if (localStorage.getItem('mad-sidebar') === 'collapsed') {{
    document.body.classList.add('sb-collapsed');
  }}
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
    """Read README.md and render a card-based styled HTML page matching System Instructions."""
    if not README_PATH.exists():
        return "<p>No README.md found.</p>"
    raw = README_PATH.read_text()

    import re

    def md_inline(text):
        # type: (str) -> str
        text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        return text

    # Parse into sections: {heading, level, content_lines}
    sections = []  # type: list[dict]
    current = {"heading": "", "level": 0, "lines": []}  # type: dict
    for line in raw.split('\n'):
        m = re.match(r'^(#{1,4})\s+(.*)', line)
        if m:
            if current["heading"] or current["lines"]:
                sections.append(current)
            current = {"heading": m.group(2), "level": len(m.group(1)), "lines": []}
        else:
            current["lines"].append(line)
    if current["heading"] or current["lines"]:
        sections.append(current)

    def render_block(content_lines):
        # type: (list[str]) -> str
        """Render a block of markdown lines to HTML."""
        parts = []  # type: list[str]
        in_table = False
        in_list = False
        in_olist = False
        for ln in content_lines:
            s = ln.strip()
            if not s:
                if in_list:
                    parts.append('</ul>')
                    in_list = False
                if in_olist:
                    parts.append('</ol>')
                    in_olist = False
                if in_table:
                    parts.append('</tbody></table>')
                    in_table = False
                continue
            # Table
            if s.startswith('|'):
                cells = [c.strip() for c in s.strip('|').split('|')]
                if all(re.match(r'^[-:]+$', c) for c in cells):
                    continue
                if not in_table:
                    parts.append('<table><thead><tr>')
                    parts.append(''.join(f'<th>{md_inline(c)}</th>' for c in cells))
                    parts.append('</tr></thead><tbody>')
                    in_table = True
                else:
                    parts.append('<tr>' + ''.join(f'<td>{md_inline(c)}</td>' for c in cells) + '</tr>')
                continue
            if in_table:
                parts.append('</tbody></table>')
                in_table = False
            # Ordered list
            m_ol = re.match(r'^(\d+)\.\s+(.*)', s)
            if m_ol:
                if not in_olist:
                    parts.append('<ol>')
                    in_olist = True
                parts.append(f'<li>{md_inline(m_ol.group(2))}</li>')
                continue
            if in_olist:
                parts.append('</ol>')
                in_olist = False
            # Unordered list
            if re.match(r'^[-*]\s', s):
                if not in_list:
                    parts.append('<ul>')
                    in_list = True
                item_text = md_inline(re.sub(r'^[-*]\s+', '', s))
                parts.append(f'<li>{item_text}</li>')
                continue
            if in_list:
                parts.append('</ul>')
                in_list = False
            # Paragraph
            parts.append(f'<p>{md_inline(s)}</p>')
        if in_list:
            parts.append('</ul>')
        if in_olist:
            parts.append('</ol>')
        if in_table:
            parts.append('</tbody></table>')
        return '\n'.join(parts)

    # Map sections to card styles
    SECTION_STYLES = {
        "The Collection": ("orange", "Hardware", ""),
        "Three Apps": ("pink", "Creative", "inst-creative"),
        "The Pipeline": ("blue", "Architecture", "inst-accent"),
        "Infrastructure": ("teal", "Infrastructure", "inst-status"),
    }

    # Build HTML
    html_parts = []

    # Hero from first section (# MADphotos + intro paragraph)
    intro_sec = sections[0] if sections else None
    if intro_sec:
        intro_lines = [l for l in intro_sec["lines"] if l.strip()]
        html_parts.append(f'''<div class="inst-hero">
  <h1>MADphotos</h1>
  <p class="hero-sub">{md_inline(intro_lines[0].strip()) if intro_lines else ""}</p>
</div>''')
        if len(intro_lines) > 1:
            html_parts.append(render_block(intro_lines[1:]))

    # Build index for quick lookup
    skip_indices = set()  # type: set[int]

    # Render each ## section as a card
    for idx, sec in enumerate(sections[1:], 1):
        if idx in skip_indices:
            continue
        if sec["level"] == 1:
            continue
        # Level 3 sections outside a parent are rendered standalone
        if sec["level"] >= 3:
            continue
        heading = sec["heading"]
        clean_heading = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', heading)

        style_info = SECTION_STYLES.get(clean_heading)
        if style_info:
            pill_color, pill_label, card_class = style_info
        else:
            pill_color, pill_label, card_class = "blue", clean_heading[:12], ""

        # Collect child ### sections that follow this ## section
        child_secs = []  # type: list[dict]
        for j in range(idx + 1, len(sections)):
            if sections[j]["level"] <= 2:
                break
            child_secs.append(sections[j])
            skip_indices.add(j)

        if clean_heading == "Three Apps" and child_secs:
            boxes = []
            for cs in child_secs:
                body = render_block(cs["lines"])
                raw_name = cs["heading"]
                sub_name = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', raw_name)
                sub_link = re.search(r'\[.+?\]\((.+?)\)', raw_name)
                name = sub_name
                if sub_link:
                    name = f'<a href="{sub_link.group(1)}" style="text-decoration:none;color:inherit">{name}</a>'
                boxes.append(f'<div class="app-box"><strong>{name}</strong>{body}</div>')

            html_parts.append(f'''<div class="inst-card {card_class}">
  <span class="inst-pill inst-pill-{pill_color}">{pill_label}</span>
  <h2>{clean_heading}</h2>
  <div class="app-trio">
    {"".join(boxes)}
  </div>
</div>''')
        elif child_secs:
            # Render parent body + child subsections inside same card
            body = render_block(sec["lines"])
            for cs in child_secs:
                cs_name = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', cs["heading"])
                body += f'\n<h3>{cs_name}</h3>\n' + render_block(cs["lines"])
            html_parts.append(f'''<div class="inst-card {card_class}">
  <span class="inst-pill inst-pill-{pill_color}">{pill_label}</span>
  <h2>{clean_heading}</h2>
  {body}
</div>''')
        else:
            body = render_block(sec["lines"])
            html_parts.append(f'''<div class="inst-card {card_class}">
  <span class="inst-pill inst-pill-{pill_color}">{pill_label}</span>
  <h2>{clean_heading}</h2>
  {body}
</div>''')

    body = '\n'.join(html_parts)

    readme_style = """<style>
  .inst-hero { text-align: center; margin-bottom: var(--space-8); padding: var(--space-8) 0 var(--space-4); }
  .inst-hero h1 { font-size: 28px; font-weight: 800; letter-spacing: -0.02em; margin: 0; }
  .inst-hero .hero-sub, .inst-hero p { font-size: var(--text-sm); color: var(--muted); margin-top: var(--space-2); max-width: 640px; margin-left: auto; margin-right: auto; line-height: var(--leading-relaxed); }
  .inst-card {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius-lg);
    padding: var(--space-5) var(--space-6); margin-bottom: var(--space-4);
    transition: border-color var(--duration-fast) var(--ease-default);
  }
  .inst-card:hover { border-color: var(--border-strong); }
  .inst-card.inst-accent {
    border-color: var(--apple-indigo);
    background: linear-gradient(135deg, var(--card-bg) 0%, rgba(88,86,214,0.05) 100%);
  }
  .inst-card.inst-creative {
    border-color: var(--apple-pink);
    background: linear-gradient(135deg, var(--card-bg) 0%, rgba(255,55,95,0.04) 100%);
  }
  .inst-card.inst-status {
    border-color: var(--apple-green);
    background: linear-gradient(135deg, var(--card-bg) 0%, rgba(52,199,89,0.04) 100%);
  }
  .inst-card h2 { font-size: 16px; font-weight: 700; margin: 0 0 var(--space-3); letter-spacing: -0.01em; border-bottom: none; padding-bottom: 0; }
  .inst-card h3 { font-size: 13px; font-weight: 600; margin: var(--space-4) 0 var(--space-2); color: var(--fg); }
  .inst-card p, .inst-card li { font-size: var(--text-sm); color: var(--fg-secondary); line-height: var(--leading-relaxed); }
  .inst-card ul { list-style: none; padding: 0; margin: var(--space-2) 0; }
  .inst-card li { padding: var(--space-1) 0 var(--space-1) var(--space-4); position: relative; }
  .inst-card li::before { content: "\\2014"; position: absolute; left: 0; color: var(--muted); }
  .inst-card ol { padding-left: var(--space-5); margin: var(--space-2) 0; }
  .inst-card ol li { padding: var(--space-1) 0; position: static; }
  .inst-card ol li::before { content: none; }
  .inst-card table { width: 100%; border-collapse: collapse; font-size: var(--text-xs); margin: var(--space-2) 0; }
  .inst-card th, .inst-card td { padding: 6px 10px; text-align: left; border-bottom: 1px solid var(--border); }
  .inst-card th { font-weight: 600; color: var(--fg); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
  .inst-card code { font-family: var(--font-mono); font-size: 0.88em; color: var(--apple-blue); }
  .inst-pill {
    display: inline-block; font-size: 10px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; padding: 2px 8px; border-radius: var(--radius-full, 9999px);
    margin-bottom: var(--space-2);
  }
  .inst-pill-orange { color: var(--apple-orange); background: color-mix(in srgb, var(--apple-orange) 12%, transparent); }
  .inst-pill-pink { color: var(--apple-pink); background: color-mix(in srgb, var(--apple-pink) 12%, transparent); }
  .inst-pill-blue { color: var(--apple-blue); background: color-mix(in srgb, var(--apple-blue) 12%, transparent); }
  .inst-pill-teal { color: var(--apple-teal); background: color-mix(in srgb, var(--apple-teal) 12%, transparent); }
  .app-trio { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-3); margin: var(--space-3) 0; }
  .app-box { background: var(--hover-overlay); border-radius: var(--radius-md); padding: var(--space-3) var(--space-4); }
  .app-box strong { display: block; font-size: 14px; margin-bottom: 4px; }
  .app-box p { font-size: 12px; margin: 0; color: var(--muted); line-height: 1.5; }
  @media (max-width: 700px) { .app-trio { grid-template-columns: 1fr; } }
</style>
"""
    content = readme_style + body
    return page_shell("README", content, active="readme")


# ---------------------------------------------------------------------------
# System Instructions renderer
# ---------------------------------------------------------------------------

def render_instructions():
    # type: () -> str
    content = """<style>
  .inst-hero { text-align: center; margin-bottom: var(--space-8); padding: var(--space-8) 0 var(--space-4); }
  .inst-hero h1 { font-size: 28px; font-weight: 800; letter-spacing: -0.02em; margin: 0; }
  .inst-hero p { font-size: var(--text-sm); color: var(--muted); margin-top: var(--space-2); }
  .inst-card {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius-lg);
    padding: var(--space-5) var(--space-6); margin-bottom: var(--space-4);
    transition: border-color var(--duration-fast) var(--ease-default);
  }
  .inst-card:hover { border-color: var(--border-strong); }
  .inst-card.inst-accent {
    border-color: var(--apple-indigo);
    background: linear-gradient(135deg, var(--card-bg) 0%, rgba(88,86,214,0.05) 100%);
  }
  .inst-card.inst-creative {
    border-color: var(--apple-pink);
    background: linear-gradient(135deg, var(--card-bg) 0%, rgba(255,55,95,0.04) 100%);
  }
  .inst-card.inst-status {
    border-color: var(--apple-green);
    background: linear-gradient(135deg, var(--card-bg) 0%, rgba(52,199,89,0.04) 100%);
  }
  .inst-card h2 { font-size: 16px; font-weight: 700; margin: 0 0 var(--space-3); letter-spacing: -0.01em; }
  .inst-card h3 { font-size: 13px; font-weight: 600; margin: var(--space-4) 0 var(--space-2); color: var(--fg); }
  .inst-card p, .inst-card li { font-size: var(--text-sm); color: var(--fg-secondary); line-height: var(--leading-relaxed); }
  .inst-card ul { list-style: none; padding: 0; margin: var(--space-2) 0; }
  .inst-card li { padding: var(--space-1) 0 var(--space-1) var(--space-4); position: relative; }
  .inst-card li::before { content: "\\2014"; position: absolute; left: 0; color: var(--muted); }
  .inst-card table { width: 100%; border-collapse: collapse; font-size: var(--text-xs); margin: var(--space-2) 0; }
  .inst-card th, .inst-card td { padding: 6px 10px; text-align: left; border-bottom: 1px solid var(--border); }
  .inst-card th { font-weight: 600; color: var(--fg); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
  .inst-card code { font-family: var(--font-mono); font-size: 0.88em; color: var(--apple-blue); }
  .inst-card td.done { color: var(--apple-green); font-weight: 600; }
  .inst-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); }
  @media (max-width: 900px) { .inst-grid { grid-template-columns: 1fr; } }
  .inst-pill {
    display: inline-block; font-size: 10px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; padding: 2px 8px; border-radius: var(--radius-full);
    margin-bottom: var(--space-2);
  }
  .inst-pill-indigo { color: var(--apple-indigo); background: color-mix(in srgb, var(--apple-indigo) 12%, transparent); }
  .inst-pill-pink { color: var(--apple-pink); background: color-mix(in srgb, var(--apple-pink) 12%, transparent); }
  .inst-pill-green { color: var(--apple-green); background: color-mix(in srgb, var(--apple-green) 12%, transparent); }
  .inst-pill-blue { color: var(--apple-blue); background: color-mix(in srgb, var(--apple-blue) 12%, transparent); }
  .inst-pill-orange { color: var(--apple-orange); background: color-mix(in srgb, var(--apple-orange) 12%, transparent); }
  .inst-pill-teal { color: var(--apple-teal); background: color-mix(in srgb, var(--apple-teal) 12%, transparent); }
  .app-trio { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-3); margin: var(--space-3) 0; }
  .app-box { background: var(--hover-overlay); border-radius: var(--radius-md); padding: var(--space-3) var(--space-4); }
  .app-box strong { display: block; font-size: 14px; margin-bottom: 4px; }
  .app-box p { font-size: 12px; margin: 0; color: var(--muted); line-height: 1.5; }
  @media (max-width: 700px) { .app-trio { grid-template-columns: 1fr; } }
</style>

<div class="inst-hero">
  <h1>System Instructions</h1>
  <p>Everything needed to work on MADphotos effectively. Updated 2026-02-07.</p>
</div>

<!-- ═══ PROJECT BRIEFING ═══ -->
<div class="inst-card inst-accent">
  <span class="inst-pill inst-pill-indigo">Briefing</span>
  <h2>MADphotos</h2>
  <p>A solo art project by <strong>LAEH</strong>. 9,011 unedited photographs shot over a decade with five cameras, turned into the most richly-understood image collection ever built. Every image gets every possible signal. Then camera-aware enhancement.</p>

  <div class="app-trio">
    <div class="app-box">
      <strong>Show</strong>
      <p>Blow people&rsquo;s minds. Continuously release new experiences guided by signals and new ideas. Delightful, playful, elegant, smart, teasing, revealing, exciting &mdash; on every screen.</p>
    </div>
    <div class="app-box">
      <strong>State</strong>
      <p>The dashboard. The control room. Every signal, every model, every image &mdash; tracked, measured, monitored.</p>
    </div>
    <div class="app-box">
      <strong>See</strong>
      <p>The native power image viewer and editor. MADCurator &mdash; 55 fields, 21 filters with union/intersection modes, inline label editing (9 Gemini fields + vibes), full-resolution display. The human eye decides what&rsquo;s worth showing.</p>
    </div>
  </div>
</div>

<!-- ═══ CREATIVE DIRECTION ═══ -->
<div class="inst-card inst-creative">
  <span class="inst-pill inst-pill-pink">Creative Direction</span>
  <h2>Show Is an Art Experience</h2>
  <p>Not just a gallery. Not a tech demo. Every experience must be designed by someone who is simultaneously the best developer, architect, ML engineer, exigent Apple-level minimalist designer, and deeply creative, emotionally intelligent curator.</p>
  <ul>
    <li><strong>Signal-aware storytelling.</strong> Two laughing faces side by side IS funny. A rose-themed image next to rose-accent colors IS pretty. Two grumpy people together IS a statement. Signals create emotional moments &mdash; surprise, beauty, humor, mystery, melancholy.</li>
    <li><strong>Minimalist UI, maximally expressive content.</strong> Dark, sparse, no chrome. Let the images talk. Fewer images shown beautifully beats more images shown generically.</li>
    <li><strong>Every experience should feel designed by someone who LOVES photography.</strong> An experience that makes you want to look at every single image.</li>
  </ul>
</div>

<!-- ═══ STATUS ═══ -->
<div class="inst-card inst-status">
  <span class="inst-pill inst-pill-green">Status</span>
  <h2>What&rsquo;s Done vs. What&rsquo;s Next</h2>
  <p><strong>Done (17/20):</strong> Rendering (97,898 tiers). EXIF. Pixel Analysis. Dominant Colors. Image Hashes. Vectors (DINOv2+SigLIP+CLIP). Aesthetic Scoring. Depth Estimation. Scene Classification. Style Classification. BLIP Captions. Facial Emotions. Enhancement Plans (v1+v2). <strong>Gemini 2.5 Pro analysis (9,011/9,011 &mdash; 100%).</strong> OCR / Text Detection (16,704 detections). &mdash; Dashboard + Journal. MADCurator. 14 web experiences. GCS upload (135,518 files: 72k original + 63k enhanced). Gallery export with GCS public URLs.</p>
  <p><strong>Sparse signals (complete but partial by nature):</strong> Face Detections (1,676 images). Object Detections (5,363 images). OCR is also sparse &mdash; not every photo contains text.</p>
  <p><strong>In progress:</strong> Curate in MADCurator (accept/reject + inline editing of 9 Gemini fields + vibe add/remove now live).</p>
  <p><strong>Next:</strong> Imagen AI variants at scale. Location intelligence from EXIF GPS. Deploy Show to Firebase.</p>
</div>

<!-- ═══ CAMERAS + ARCHITECTURE ═══ -->
<div class="inst-grid">

<div class="inst-card">
  <span class="inst-pill inst-pill-orange">Hardware</span>
  <h2>Five Cameras</h2>
  <table>
    <thead><tr><th>Camera</th><th>Count</th><th>Rule</th></tr></thead>
    <tbody>
      <tr><td>Leica M8</td><td>3,533</td><td>CCD warmth is character. Correct WB only 50%.</td></tr>
      <tr><td>DJI Osmo Pro</td><td>3,032</td><td>1,459 have GPS. Best auto WB.</td></tr>
      <tr><td>Leica MP</td><td>1,126</td><td>Portra 400 VC. Film grain is sacred &mdash; never denoise.</td></tr>
      <tr><td>Leica Monochrom</td><td>1,099</td><td><strong>NEVER color-correct.</strong> Pure luminance sensor.</td></tr>
      <tr><td>G12 / Memo</td><td>221</td><td>Worst WB. Most aggressive correction (70%).</td></tr>
    </tbody>
  </table>
</div>

<div class="inst-card">
  <span class="inst-pill inst-pill-blue">Architecture</span>
  <h2>19 Python Scripts (backend/)</h2>
  <table>
    <thead><tr><th>Script</th><th>Purpose</th></tr></thead>
    <tbody>
      <tr><td><code>pipeline.py</code></td><td>Phase orchestrator</td></tr>
      <tr><td><code>completions.py</code></td><td>Master orchestrator &mdash; checks all 20 stages, fixes gaps, updates State</td></tr>
      <tr><td><code>render.py</code></td><td>6-tier resolution pyramid</td></tr>
      <tr><td><code>gemini.py</code></td><td>Gemini 2.5 Pro structured analysis</td></tr>
      <tr><td><code>imagen.py</code></td><td>4 AI variants via Imagen 3</td></tr>
      <tr><td><code>upload.py</code></td><td>Upload to GCS</td></tr>
      <tr><td><code>database.py</code></td><td>SQLite schema (24 tables)</td></tr>
      <tr><td><code>enhance.py</code></td><td>Camera-aware 6-step enhancement</td></tr>
      <tr><td><code>signals_advanced.py</code></td><td>11 ML models</td></tr>
      <tr><td><code>dashboard.py</code></td><td>Dashboard + Journal</td></tr>
      <tr><td><code>export_gallery.py</code></td><td>Gallery data export to JSON</td></tr>
      <tr><td><code>serve_show.py</code></td><td>Local dev server</td></tr>
      <tr><td><code>signals.py</code></td><td>EXIF, colors, faces, objects, hashes</td></tr>
      <tr><td><code>pixel_analysis.py</code></td><td>Pixel-level analysis for enhancement</td></tr>
      <tr><td><code>vectors.py</code></td><td>DINOv2/SigLIP/CLIP embeddings</td></tr>
      <tr><td><code>mosaics.py</code></td><td>4096px mosaic generator</td></tr>
      <tr><td><code>enhance_v2.py</code></td><td>Signal-aware enhancement v2</td></tr>
      <tr><td><code>render_enhanced.py</code></td><td>Enhanced image tier rendering</td></tr>
      <tr><td><code>prep_blind_test.py</code></td><td>A/B blind test preparation</td></tr>
    </tbody>
  </table>
</div>

</div>

<!-- ═══ TECHNICAL RULES ═══ -->
<div class="inst-card">
  <span class="inst-pill inst-pill-teal">Rules</span>
  <h2>Critical Technical Rules</h2>
  <div class="inst-grid" style="gap:var(--space-2);">
    <ul>
      <li><strong>Python 3.9.6</strong> &mdash; <code>from __future__ import annotations</code>, <code>Optional[X]</code> not <code>X | None</code></li>
      <li><strong>Vertex AI + ADC only</strong> &mdash; NEVER API keys</li>
      <li><strong>Flat layout</strong> &mdash; <code>images/rendered/{tier}/{format}/{uuid}.ext</code>. Never <code>rendered/originals/</code> (plural)</li>
      <li><strong>DNG color</strong> &mdash; <code>sips -m sRGB Profile.icc</code> to avoid P3 purple cast</li>
      <li><strong>UUID5</strong> &mdash; DNS namespace, deterministic from relative path</li>
    </ul>
    <ul>
      <li><strong>Tiers</strong>: full (3840), display (2048), mobile (1280), thumb (480), micro (64), gemini (2048)</li>
      <li><strong>GCS</strong> &mdash; <code>v/{version}/{tier}/{format}/{uuid}.ext</code></li>
      <li><strong>google-genai 1.47</strong> &mdash; <code>edit_image()</code> needs <code>vertexai=True</code></li>
      <li><strong>JPEGmini Pro</strong> &mdash; GUI app, serving tiers only (display/mobile/thumb/micro)</li>
      <li><strong>Monochrome</strong> &mdash; zero saturation, zero color correction, ever</li>
    </ul>
  </div>
</div>

<!-- ═══ HOSTING ═══ -->
<div class="inst-grid">

<div class="inst-card">
  <span class="inst-pill inst-pill-blue">Infrastructure</span>
  <h2>GCS Image Hosting Strategy</h2>
  <ul>
    <li><strong>GCP Project:</strong> laeh380to760 &mdash; account: laeh@madbits.ai</li>
    <li><strong>Bucket:</strong> <code>gs://myproject-public-assets/art/MADphotos/</code></li>
    <li><strong>URL pattern:</strong> <code>https://storage.googleapis.com/myproject-public-assets/art/MADphotos/v/{version}/{tier}/{format}/{uuid}.ext</code></li>
  </ul>
  <h3>Versioned Directory Structure</h3>
  <table>
    <thead><tr><th>Version</th><th>Content</th><th>Tiers Uploaded</th></tr></thead>
    <tbody>
      <tr><td><code>original</code></td><td>Unmodified rendered tiers</td><td>display, mobile, thumb, micro &times; jpeg + webp</td></tr>
      <tr><td><code>enhanced</code></td><td>Camera-aware enhanced</td><td>display, mobile, thumb, micro &times; jpeg + webp</td></tr>
      <tr><td><code>blind</code></td><td>Blind test comparison images</td><td>display/jpeg only</td></tr>
    </tbody>
  </table>
  <h3>Deployment Map</h3>
  <table>
    <thead><tr><th>App</th><th>Platform</th><th>URL</th></tr></thead>
    <tbody>
      <tr><td><strong>State</strong></td><td>GitHub Pages</td><td>laeh.github.io/MADphotos/</td></tr>
      <tr><td><strong>Show</strong></td><td>Firebase Hosting</td><td>madphotos-efbfb.web.app</td></tr>
      <tr><td><strong>Images</strong></td><td>GCS public bucket</td><td>storage.googleapis.com/myproject-public-assets/...</td></tr>
    </tbody>
  </table>
  <ul>
    <li><strong>Show does NOT host images.</strong> All image URLs point to GCS. Firebase only serves HTML/CSS/JS + data JSONs.</li>
    <li><strong>upload.py</strong> uploads serving tiers only. Full/gemini tiers stay local (AI pipeline input).</li>
    <li><strong>Upload command:</strong> <code>python3 backend/upload.py --version original</code> (or enhanced, blind)</li>
  </ul>
</div>

<div class="inst-card">
  <h2>Web Gallery (Show) &mdash; 14 Experiences</h2>
  <ul>
    <li><code>backend/export_gallery.py</code> &rarr; 5 JSON files (photos, faces, game_rounds, stream_sequence, drift_neighbors)</li>
    <li><code>backend/serve_show.py</code> &rarr; localhost:3000</li>
    <li>18 files: index.html, style.css, app.js + 14 experience modules + data/</li>
    <li>La Grille, Le Bento, La Similarit&eacute;, La D&eacute;rive, Les Couleurs, Le Jeu, Chambre Noire, Le Flot, Les Visages, La Boussole, L&rsquo;Observatoire, La Carte, Machine &Agrave; &Eacute;crire, Le Pendule</li>
    <li>Dark minimalist design system: 40+ CSS tokens (motion grammar, emotion colors, depth layers, category colors), Apple HIG curves, prefers-reduced-motion support</li>
    <li>Vanilla JS, no framework. 60fps animations via rAF, IntersectionObserver lazy loading, timer leak prevention</li>
  </ul>
</div>

</div>

<!-- ═══ SIGNAL INVENTORY ═══ -->
<div class="inst-card">
  <span class="inst-pill inst-pill-teal">Signals</span>
  <h2>Signal Inventory &mdash; 18 Signals per Image</h2>
  <table>
    <thead><tr><th>Signal</th><th>Source</th><th>Status</th><th>Key Fields</th></tr></thead>
    <tbody>
      <tr><td>EXIF</td><td>Pillow</td><td class="done">9,011 &check;</td><td>Camera, lens, focal, aperture, shutter, ISO, GPS</td></tr>
      <tr><td>Pixel Analysis</td><td>NumPy/OpenCV</td><td class="done">9,011 &check;</td><td>Brightness, saturation, contrast, noise, WB shifts</td></tr>
      <tr><td>Dominant Colors</td><td>K-means (LAB)</td><td class="done">9,011 &check;</td><td>5 clusters: hex, RGB, LAB, percentage</td></tr>
      <tr><td>Faces</td><td>YuNet</td><td class="done">1,676 images &check;</td><td>3,187 faces: boxes, landmarks, confidence, area %</td></tr>
      <tr><td>Objects</td><td>YOLOv8n</td><td class="done">5,363 images &check;</td><td>14,534 detections, 80 COCO classes</td></tr>
      <tr><td>Hashes</td><td>imagehash</td><td class="done">9,011 &check;</td><td>pHash, aHash, dHash, wHash, blur, sharpness</td></tr>
      <tr><td>Vectors</td><td>DINOv2+SigLIP+CLIP</td><td class="done">9,011 &check;</td><td>768d+768d+512d = 2,048 dims (LanceDB)</td></tr>
      <tr><td>Gemini</td><td>Gemini 2.5 Pro</td><td class="done">9,011 &check;</td><td>Alt, vibes, exposure, composition, grading, edit prompt</td></tr>
      <tr><td>Aesthetic</td><td>LAION (CLIP MLP)</td><td class="done">9,011 &check;</td><td>Score 1&ndash;10</td></tr>
      <tr><td>Depth</td><td>Depth Anything v2</td><td class="done">9,011 &check;</td><td>Near/mid/far %, complexity bucket</td></tr>
      <tr><td>Scenes</td><td>Places365</td><td class="done">9,011 &check;</td><td>Top 3 labels, indoor/outdoor</td></tr>
      <tr><td>Style</td><td>Derived</td><td class="done">9,011 &check;</td><td>street, portrait, landscape, macro, etc.</td></tr>
      <tr><td>OCR</td><td>EasyOCR</td><td class="done">16,704 detections &check;</td><td>Text regions, language, confidence (sparse &mdash; not all images have text)</td></tr>
      <tr><td>Captions</td><td>BLIP (Salesforce)</td><td class="done">9,011 &check;</td><td>Natural language description</td></tr>
      <tr><td>Emotions</td><td>ViT expression</td><td class="done">1,676 &check;</td><td>7-class scores per face (3,185 emotion entries)</td></tr>
      <tr><td>Enhancement</td><td>Camera engine</td><td class="done">9,011 &check;</td><td>WB, gamma, shadows, contrast, saturation, sharpening</td></tr>
      <tr><td>Enhancement v2</td><td>Camera engine v2</td><td class="done">9,011 &check;</td><td>Updated parameters</td></tr>
      <tr><td>AI Variants</td><td>Imagen 3</td><td>216/9,011</td><td>gemini_edit, pro_edit, nano_feel, cartoon</td></tr>
    </tbody>
  </table>
</div>

<!-- ═══ INCREMENTAL INGESTION ═══ -->
<div class="inst-card">
  <span class="inst-pill inst-pill-orange">Pipeline</span>
  <h2>New Image Ingestion</h2>
  <p>User will add more images over time. <strong>Every script MUST handle incremental ingestion.</strong> Full process for new images:</p>
  <p style="font-family:var(--font-mono);font-size:12px;color:var(--muted);line-height:1.8;">
    register &rarr; render tiers &rarr; pixel analysis &rarr; Gemini analysis &rarr; signal extraction &rarr; vector embeddings &rarr; enhancement &rarr; export gallery data &rarr; curation
  </p>
  <ul>
    <li>All scripts check for existing results and skip processed images</li>
    <li>Processing can be interrupted and resumed at any point</li>
    <li>After ingestion, re-run <code>backend/export_gallery.py</code> to update web data</li>
    <li>Consistency: same parameters, same models, same quality for all images</li>
  </ul>
</div>

<!-- ═══ JOURNAL ═══ -->
<div class="inst-card">
  <h2>Journal de Bord</h2>
  <p>File: <code>docs/journal.md</code>. Write after EVERY significant action. Format: <code>### HH:MM &mdash; Title</code> under <code>## YYYY-MM-DD</code> headers. Include intent, what happened, what was learned. Rendered as timeline with auto-classified event type labels.</p>
</div>
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
        return page_shell("Mosaics", "<h1>Mosaics</h1><p>No mosaics generated yet. Run <code>python3 backend/mosaics.py</code></p>", active="mosaics")

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

JOURNAL_PATH = PROJECT_ROOT / "docs" / "journal.md"


def render_journal():
    """Read journal.md and render a rich timeline with event type labels."""
    if not JOURNAL_PATH.exists():
        return "<p>No journal found.</p>"
    raw = JOURNAL_PATH.read_text()

    import re

    # -- Event type classification ----------------------------------------
    LABEL_RULES = [
        ("Deploy",       re.compile(r'GCS|GCP|bucket|upload|push|deploy|GitHub Pages|sync', re.I)),
        ("Infrastructure", re.compile(r'database|schema|table|migration|SQLite|column|UUID', re.I)),
        ("Pipeline",     re.compile(r'pipeline|engine|render|tier|enhancement|enhance|batch|process|worker|shard', re.I)),
        ("AI",           re.compile(r'Gemini|Imagen|BLIP|CLIP|DINO|SigLIP|YOLO|YuNet|OCR|emotion|vector|embedding|model|Places365|Depth|NIMA|aesthetic|caption', re.I)),
        ("Investigation", re.compile(r'discovered|blind test|audit|bug|broke|fix|root cause|debug|purple cast|crash', re.I)),
        ("UI/UX",        re.compile(r'dashboard|sidebar|card|design|CSS|layout|landing|hero|mosaic|responsive|mobile|pill|tag|icon|SVG|page|README|gallery|curator|app|SwiftUI', re.I)),
        ("Security",     re.compile(r'secret|API key|credential|redact|git-filter', re.I)),
        ("Architecture", re.compile(r'architecture|two-stage|vision|endgame|three experience|faceted|curation', re.I)),
        ("Signal",       re.compile(r'signal|pixel.level|analysis|extraction|EXIF|color|face|object|hash|depth|scene|style', re.I)),
    ]
    LABEL_COLORS = {
        "Deploy": "var(--apple-green)",
        "Infrastructure": "var(--apple-brown, #a2845e)",
        "Pipeline": "var(--apple-blue)",
        "AI": "var(--apple-purple)",
        "Investigation": "var(--apple-orange)",
        "UI/UX": "var(--apple-pink)",
        "Security": "var(--apple-red)",
        "Architecture": "var(--apple-indigo)",
        "Signal": "var(--apple-teal)",
    }

    def classify_event(title, body_text):
        """Return up to 2 labels for an event based on title + body content."""
        combined = title + " " + body_text
        labels = []
        for label, pattern in LABEL_RULES:
            if pattern.search(combined):
                labels.append(label)
                if len(labels) >= 2:
                    break
        return labels if labels else ["Note"]

    def label_html(labels):
        parts = []
        for lb in labels:
            color = LABEL_COLORS.get(lb, "var(--muted)")
            parts.append(
                f'<span class="ev-label" style="--label-color:{color}">{lb}</span>'
            )
        return "".join(parts)

    # -- Markdown inline formatting ---------------------------------------
    def md_inline(text):
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        return text

    # -- Parse journal.md -------------------------------------------------
    lines = raw.split("\n")
    date_sections = []          # type: list[dict]
    current_date = None         # type: Optional[dict]
    current_event = None        # type: Optional[dict]
    in_intro = True
    in_table = False
    in_code = False
    in_list = False

    def flush_event():
        nonlocal current_event
        if current_event and current_date is not None:
            current_date["events"].append(current_event)
        current_event = None

    for line in lines:
        stripped = line.strip()

        # Code fence toggle
        if stripped.startswith("```"):
            if current_event is not None:
                if not in_code:
                    in_code = True
                    current_event["body"].append("<pre><code>")
                else:
                    in_code = False
                    current_event["body"].append("</code></pre>")
            continue

        if in_code:
            if current_event is not None:
                from html import escape as html_escape
                current_event["body"].append(html_escape(line))
            continue

        # Blank line
        if not stripped:
            if in_list and current_event is not None:
                current_event["body"].append("</ul>")
                in_list = False
            if in_table and current_event is not None:
                current_event["body"].append("</tbody></table></div>")
                in_table = False
            continue

        # Top-level heading — skip
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue

        # Date heading (## 2026-02-06) or named section (## The Beginning)
        if stripped.startswith("## "):
            flush_event()
            header_text = stripped[3:]
            if re.match(r'\d{4}-\d{2}-\d{2}', header_text):
                in_intro = False
                current_date = {"header": header_text, "events": []}
                date_sections.append(current_date)
            # Skip intro sections entirely (The Beginning, The Numbers, etc.)
            continue

        # Intro content — skip entirely (user requested removal)
        if in_intro:
            continue

        # Horizontal rule
        if stripped.startswith("---"):
            flush_event()
            continue

        # Event heading (### HH:MM — Title)
        if stripped.startswith("### "):
            flush_event()
            heading = stripped[4:]
            m = re.match(r'(.+?)\s*\*\((.+?)\)\*\s*$', heading)
            if m:
                title = m.group(1).rstrip()
                quote = m.group(2)
            else:
                title = heading
                quote = None
            current_event = {
                "title": title,
                "quote": quote,
                "body": [],
                "raw_text": "",
            }
            continue

        # Table rows
        if stripped.startswith("|") and current_event is not None:
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # Separator row (|---|---|)
            if all(re.match(r'^[-:]+$', c) for c in cells):
                if not in_table:
                    # Previous row was the header — rewrite it
                    if current_event["body"] and current_event["body"][-1].startswith("<tr class=\"thead\">"):
                        header_row = current_event["body"].pop()
                        current_event["body"].append(
                            f'<div class="table-wrap"><table><thead>{header_row}</thead><tbody>'
                        )
                        in_table = True
                continue
            row_cls = "thead" if not in_table else ""
            tag = "th" if not in_table else "td"
            row_html = f'<tr class="{row_cls}">' + "".join(
                f"<{tag}>{md_inline(c)}</{tag}>" for c in cells
            ) + "</tr>"
            current_event["body"].append(row_html)
            continue

        # List items
        if stripped.startswith("- ") and current_event is not None:
            if not in_list:
                current_event["body"].append("<ul>")
                in_list = True
            current_event["body"].append(f"<li>{md_inline(stripped[2:])}</li>")
            current_event["raw_text"] += " " + stripped
            continue

        # Regular content lines inside an event — uniform style
        if current_event is not None:
            if stripped.startswith("> "):
                if in_list:
                    current_event["body"].append("</ul>")
                    in_list = False
                current_event["body"].append(f'<p>{md_inline(stripped[2:])}</p>')
            else:
                current_event["body"].append(f'<p>{md_inline(stripped)}</p>')
            current_event["raw_text"] += " " + stripped

    flush_event()
    if in_list and current_event:
        current_event["body"].append("</ul>")
    if in_table and current_event:
        current_event["body"].append("</tbody></table></div>")

    # -- Merge duplicate date sections ------------------------------------
    merged = []  # type: list[dict]
    seen_dates = {}  # type: dict[str, int]
    for ds in date_sections:
        if ds["header"] in seen_dates:
            merged[seen_dates[ds["header"]]]["events"].extend(ds["events"])
        else:
            seen_dates[ds["header"]] = len(merged)
            merged.append(ds)
    date_sections = merged

    # -- Genesis event (special card at the bottom) -----------------------
    genesis_html = """<div class="event event-genesis">
<div class="ev-labels"><span class="ev-label" style="--label-color:var(--apple-indigo)">Genesis</span></div>
<h3>The Vision</h3>
<p class="intent">9,011 unedited photographs taken over a decade with five cameras. The mission: augment every single image with every possible signal — AI analysis, pixel metrics, vector embeddings, depth maps, scene classification, object detection, face emotions, captions, color palettes. Then enhance each frame with camera-aware, signal-driven corrections.</p>
<p>Three apps, one pipeline. <strong>Show</strong> — blow people's minds with experiences that are playful, elegant, smart, teasing, revealing. Continuously release new ways to see photographs, guided by signals and new ideas. <strong>State</strong> — the dashboard, the control room. Every signal, every model, every image tracked. <strong>See</strong> (MADCurator) — the native power image viewer and editor. 55 fields, 21 filters with union/intersection modes, inline label editing, full-resolution. The human eye decides what's worth showing.</p>
<blockquote>We started with 9,011 raw images and zero metadata. We will create the best experience on photos. Game ON.</blockquote>
</div>"""

    # -- Build HTML -------------------------------------------------------
    html_parts = []
    for date_sec in reversed(date_sections):
        html_parts.append(f'<h2 class="date-header">{date_sec["header"]}</h2>')
        for ev in reversed(date_sec["events"]):
            labels = classify_event(ev["title"], ev["raw_text"])
            body_lines = ev["body"]
            body_html = "\n".join(body_lines)
            quote_html = f'<span class="quote">({ev["quote"]})</span>' if ev.get("quote") else ""
            # Extract the first paragraph as summary
            summary = ""
            for line in body_lines:
                if line.startswith("<p>"):
                    summary = line
                    break
            if not summary and body_lines:
                for line in body_lines:
                    if line.strip() and not line.startswith("</"):
                        summary = line
                        break
            html_parts.append(
                f'<div class="event ev-collapsed" onclick="this.classList.toggle(\'ev-collapsed\')">'
                f'<div class="ev-labels">{label_html(labels)}</div>'
                f'<h3>{ev["title"]} <span class="ev-expand-hint">&#9656;</span></h3>'
                f'{quote_html}'
                f'<div class="ev-summary">{summary}</div>'
                f'<div class="ev-body">{body_html}</div>'
                f'</div>'
            )

    # Append genesis at the very bottom
    html_parts.append('<h2 class="date-header">Origin</h2>')
    html_parts.append(genesis_html)

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
  .event-genesis {{
    border-color: var(--apple-indigo);
    background: linear-gradient(135deg, var(--card-bg) 0%, rgba(88,86,214,0.06) 100%);
  }}
  .event-genesis h3 {{
    font-size: var(--text-base) !important; font-weight: 800;
    letter-spacing: -0.01em;
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
  /* Event type labels */
  .ev-labels {{
    display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap;
  }}
  .ev-label {{
    font-size: 10px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 2px 8px; border-radius: var(--radius-full);
    color: var(--label-color);
    background: color-mix(in srgb, var(--label-color) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--label-color) 25%, transparent);
    line-height: 1.4;
  }}
  .main-content h3 {{
    font-size: var(--text-sm); font-weight: 700; margin: 0;
    color: var(--fg); display: block; line-height: var(--leading-normal);
  }}
  .quote {{
    font-size: var(--text-xs); color: var(--muted); font-style: italic;
    font-weight: 400; display: block; margin-top: 2px;
  }}
  /* Compact/expanded toggle */
  .event {{ cursor: pointer; }}
  .ev-expand-hint {{
    font-size: 10px; color: var(--muted); transition: transform 0.2s;
    display: inline-block; margin-left: 4px;
  }}
  .ev-collapsed .ev-body {{ display: none; }}
  .ev-collapsed .ev-summary {{ display: block; }}
  .event:not(.ev-collapsed) .ev-body {{ display: block; }}
  .event:not(.ev-collapsed) .ev-summary {{ display: none; }}
  .event:not(.ev-collapsed) .ev-expand-hint {{ transform: rotate(90deg); }}
  .ev-summary {{
    font-size: var(--text-sm); color: var(--muted);
    margin-top: var(--space-1); line-height: var(--leading-relaxed);
  }}
  .ev-summary p {{ margin: 0; }}
  .event p {{
    font-size: var(--text-sm); color: var(--fg-secondary);
    margin: var(--space-1) 0; line-height: var(--leading-relaxed);
  }}
  .event ul {{ list-style: none; margin: var(--space-2) 0; padding: 0; }}
  .event li {{
    font-size: var(--text-sm); color: var(--fg-secondary);
    padding: var(--space-1) 0 var(--space-1) var(--space-5); position: relative;
    line-height: var(--leading-relaxed);
  }}
  .event li::before {{ content: "\u2014"; position: absolute; left: 0; color: var(--muted); }}
  .event pre {{
    background: var(--hover-overlay); border-radius: var(--radius-sm);
    padding: var(--space-3); margin: var(--space-2) 0; overflow-x: auto;
    font-size: 11px; line-height: 1.5;
  }}
  .event code {{ font-family: var(--font-mono); font-size: 0.9em; }}
  .event .table-wrap {{ overflow-x: auto; margin: var(--space-2) 0; }}
  .event table {{
    width: 100%; border-collapse: collapse; font-size: var(--text-xs);
  }}
  .event th, .event td {{
    padding: var(--space-1) var(--space-2); text-align: left;
    border-bottom: 1px solid var(--border);
  }}
  .event th {{ font-weight: 600; color: var(--fg); }}
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
# Similarity — Interactive vector neighbor explorer
# ---------------------------------------------------------------------------

RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"

# Shared lancedb connection (lazy)
_lance_db = None  # type: Optional[object]
_lance_tbl = None  # type: Optional[object]


def _get_lance():
    """Lazy-load lancedb connection, returns (tbl, df) or (None, None)."""
    global _lance_db, _lance_tbl
    try:
        import lancedb as _ldb
    except ImportError:
        return None, None
    lance_path = Path(__file__).resolve().parent / "vectors.lance"
    if not lance_path.exists():
        return None, None
    if _lance_db is None:
        _lance_db = _ldb.connect(str(lance_path))
        _lance_tbl = _lance_db.open_table("image_vectors")
    return _lance_tbl, _lance_tbl.to_pandas()


def similarity_search(query_uuid):
    # type: (str) -> Optional[dict]
    """Find nearest neighbors for a UUID across all 3 models. Returns JSON-ready dict."""
    tbl, df = _get_lance()
    if tbl is None:
        return None
    matches = df[df["uuid"] == query_uuid]
    if matches.empty:
        return None
    query_row = matches.iloc[0]
    models = [
        ("dino", "DINOv2", "Texture & structure — finds images with similar visual geometry"),
        ("siglip", "SigLIP", "Semantic meaning — finds images about similar things"),
        ("clip", "CLIP", "Subject matching — finds images of similar objects"),
    ]
    result = {"uuid": query_uuid, "models": []}
    for col, name, desc in models:
        query_vec = query_row[col]
        results = tbl.search(query_vec, vector_column_name=col).limit(9).to_pandas()
        neighbors = results[results["uuid"] != query_uuid].head(8)
        nb_list = []
        for _, nb_row in neighbors.iterrows():
            nb_list.append({"uuid": nb_row["uuid"], "dist": round(float(nb_row["_distance"]), 4)})
        result["models"].append({"name": name, "desc": desc, "neighbors": nb_list})
    return result


def render_drift():
    # type: () -> str
    """Interactive similarity explorer — navigate through vector space."""
    import random
    tbl, df = _get_lance()
    if tbl is None:
        return page_shell("Similarity", "<h1>Similarity</h1><p>Vector store not available.</p>", active="drift")

    all_uuids = df["uuid"].tolist()
    start_uuid = random.choice(all_uuids)
    GCS = "https://storage.googleapis.com/myproject-public-assets/art/MADphotos/v/original"

    content = f"""<style>
  .sim-hero {{
    text-align: center;
    margin-bottom: var(--space-6);
  }}
  .sim-hero h1 {{
    font-size: 28px; font-weight: 800; letter-spacing: -0.02em; margin: 0;
  }}
  .sim-hero p {{
    font-size: var(--text-sm); color: var(--muted); margin-top: var(--space-2);
    max-width: 500px; margin-left: auto; margin-right: auto;
  }}
  .sim-controls {{
    display: flex; gap: var(--space-2); justify-content: center;
    margin-bottom: var(--space-6);
  }}
  .sim-btn {{
    font-family: var(--font-sans); font-size: var(--text-sm); font-weight: 600;
    padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm);
    border: 1px solid var(--border); background: var(--card-bg); color: var(--fg);
    cursor: pointer; transition: all var(--duration-fast);
  }}
  .sim-btn:hover {{ border-color: var(--border-strong); background: var(--hover-overlay); }}
  .sim-trail {{
    display: flex; gap: 4px; justify-content: center; align-items: center;
    margin-bottom: var(--space-6); flex-wrap: wrap;
  }}
  .sim-trail-item {{
    width: 40px; height: 40px; border-radius: var(--radius-sm);
    overflow: hidden; cursor: pointer; border: 2px solid transparent;
    transition: border-color var(--duration-fast);
    flex-shrink: 0;
  }}
  .sim-trail-item:hover {{ border-color: var(--muted); }}
  .sim-trail-item.current {{ border-color: var(--apple-blue); }}
  .sim-trail-item img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .sim-trail-arrow {{ color: var(--muted); font-size: 12px; flex-shrink: 0; }}
  .sim-query {{
    display: flex; justify-content: center; margin-bottom: var(--space-6);
  }}
  .sim-query img {{
    max-width: 100%; max-height: 420px; border-radius: var(--radius-md);
    box-shadow: 0 8px 32px rgba(0,0,0,0.15);
    transition: opacity 0.4s;
  }}
  .sim-model-section {{
    margin-bottom: var(--space-6);
  }}
  .sim-model-header {{
    display: flex; align-items: baseline; gap: var(--space-2);
    margin-bottom: var(--space-3);
  }}
  .sim-model-name {{
    font-size: var(--text-base); font-weight: 700; color: var(--fg);
  }}
  .sim-model-desc {{
    font-size: var(--text-xs); color: var(--muted);
  }}
  .sim-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-2);
  }}
  .sim-card {{
    position: relative; border-radius: var(--radius-sm);
    overflow: hidden; cursor: pointer; aspect-ratio: 1;
    border: 2px solid transparent;
    transition: border-color var(--duration-fast), transform var(--duration-fast);
  }}
  .sim-card:hover {{
    border-color: var(--apple-blue);
    transform: scale(1.03);
  }}
  .sim-card img {{
    width: 100%; height: 100%; object-fit: cover; display: block;
    opacity: 0; transition: opacity 0.5s;
  }}
  .sim-card img.loaded {{ opacity: 1; }}
  .sim-card .sim-dist {{
    position: absolute; bottom: 0; right: 0;
    font-family: var(--font-mono); font-size: 10px; font-weight: 600;
    color: rgba(255,255,255,0.9); background: rgba(0,0,0,0.5);
    padding: 2px 6px; border-radius: var(--radius-sm) 0 0 0;
    backdrop-filter: blur(4px);
  }}
  @media (max-width: 700px) {{
    .sim-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .sim-query img {{ max-height: 280px; }}
  }}
</style>

<div class="sim-hero">
  <h1>Similarity</h1>
  <p>Navigate vector space. Each image has neighbors in three dimensions: visual structure, semantic meaning, and subject matter. Click any image to drift there.</p>
</div>

<div class="sim-controls">
  <button class="sim-btn" onclick="simRandom()">Random</button>
  <button class="sim-btn" onclick="simBack()" id="sim-back-btn" style="display:none">Back</button>
</div>

<div class="sim-trail" id="sim-trail"></div>
<div class="sim-query" id="sim-query"></div>
<div id="sim-results"></div>

<script>
(function() {{
  var GCS = "{GCS}";
  var history = [];
  var currentUuid = "{start_uuid}";

  function thumbUrl(uuid) {{ return GCS + "/thumb/jpeg/" + uuid + ".jpg"; }}
  function displayUrl(uuid) {{ return GCS + "/display/jpeg/" + uuid + ".jpg"; }}

  function loadImg(img) {{
    img.onload = function() {{ img.classList.add("loaded"); }};
  }}

  function renderTrail() {{
    var el = document.getElementById("sim-trail");
    el.innerHTML = "";
    var trail = history.slice(-12);
    for (var i = 0; i < trail.length; i++) {{
      var item = document.createElement("div");
      item.className = "sim-trail-item";
      var img = document.createElement("img");
      img.src = thumbUrl(trail[i]);
      img.alt = "";
      item.appendChild(img);
      (function(uuid) {{
        item.onclick = function() {{ navigate(uuid); }};
      }})(trail[i]);
      el.appendChild(item);
      if (i < trail.length - 1) {{
        var arrow = document.createElement("span");
        arrow.className = "sim-trail-arrow";
        arrow.textContent = "\\u203a";
        el.appendChild(arrow);
      }}
    }}
    if (trail.length > 0) {{
      var arrow = document.createElement("span");
      arrow.className = "sim-trail-arrow";
      arrow.textContent = "\\u203a";
      el.appendChild(arrow);
    }}
    var cur = document.createElement("div");
    cur.className = "sim-trail-item current";
    var curImg = document.createElement("img");
    curImg.src = thumbUrl(currentUuid);
    curImg.alt = "";
    cur.appendChild(curImg);
    el.appendChild(cur);
    document.getElementById("sim-back-btn").style.display = history.length > 0 ? "" : "none";
  }}

  function navigate(uuid) {{
    if (uuid === currentUuid) return;
    history.push(currentUuid);
    currentUuid = uuid;
    load(uuid);
  }}

  window.simRandom = function() {{
    fetch("/api/similarity/random").then(function(r) {{ return r.json(); }}).then(function(d) {{
      if (d.uuid) navigate(d.uuid);
    }});
  }};

  window.simBack = function() {{
    if (history.length === 0) return;
    currentUuid = history.pop();
    load(currentUuid);
  }};

  function load(uuid) {{
    // Query image
    var qEl = document.getElementById("sim-query");
    qEl.innerHTML = "";
    var qImg = document.createElement("img");
    qImg.src = displayUrl(uuid);
    loadImg(qImg);
    qEl.appendChild(qImg);

    // Fetch neighbors
    var resEl = document.getElementById("sim-results");
    resEl.innerHTML = '<p style="text-align:center;color:var(--muted);padding:var(--space-4)">Loading neighbors...</p>';

    fetch("/api/similarity/" + uuid).then(function(r) {{ return r.json(); }}).then(function(data) {{
      resEl.innerHTML = "";
      if (!data.models) return;
      for (var m = 0; m < data.models.length; m++) {{
        var model = data.models[m];
        var section = document.createElement("div");
        section.className = "sim-model-section";
        var header = document.createElement("div");
        header.className = "sim-model-header";
        header.innerHTML = '<span class="sim-model-name">' + model.name + '</span><span class="sim-model-desc">' + model.desc + '</span>';
        section.appendChild(header);
        var grid = document.createElement("div");
        grid.className = "sim-grid";
        for (var n = 0; n < model.neighbors.length; n++) {{
          var nb = model.neighbors[n];
          var card = document.createElement("div");
          card.className = "sim-card";
          var img = document.createElement("img");
          img.src = thumbUrl(nb.uuid);
          img.alt = "";
          loadImg(img);
          card.appendChild(img);
          var dist = document.createElement("span");
          dist.className = "sim-dist";
          dist.textContent = nb.dist.toFixed(3);
          card.appendChild(dist);
          (function(nbuuid) {{
            card.onclick = function() {{ navigate(nbuuid); }};
          }})(nb.uuid);
          grid.appendChild(card);
        }}
        section.appendChild(grid);
        resEl.appendChild(section);
      }}
    }});
    renderTrail();
  }}

  // Initial load
  load(currentUuid);
  renderTrail();
}})();
</script>"""

    return page_shell("Similarity", content, active="drift")


# ---------------------------------------------------------------------------
# Creative Drift — Loose structural matches, different worlds
# ---------------------------------------------------------------------------

def drift_search(query_uuid):
    # type: (str) -> Optional[dict]
    """Find creative drift neighbors: structurally similar (DINOv2) but semantically different (SigLIP).
    Skip the closest matches to find surprising connections."""
    tbl, df = _get_lance()
    if tbl is None:
        return None
    matches = df[df["uuid"] == query_uuid]
    if matches.empty:
        return None
    query_row = matches.iloc[0]

    # Get DINOv2 neighbors (structural) — skip top 3 closest (too similar), take rank 4-20
    dino_vec = query_row["dino"]
    dino_results = tbl.search(dino_vec, vector_column_name="dino").limit(25).to_pandas()
    dino_results = dino_results[dino_results["uuid"] != query_uuid]

    # Also get SigLIP distances for these same images to find semantic divergence
    siglip_vec = query_row["siglip"]
    siglip_results = tbl.search(siglip_vec, vector_column_name="siglip").limit(100).to_pandas()
    siglip_dist_map = dict(zip(siglip_results["uuid"].tolist(), siglip_results["_distance"].tolist()))

    # Score: want LOW dino distance (similar structure) but HIGH siglip distance (different meaning)
    candidates = []
    for _, row in dino_results.iterrows():
        nb_uuid = row["uuid"]
        dino_dist = float(row["_distance"])
        siglip_dist = siglip_dist_map.get(nb_uuid, 1.0)
        # Creative score: penalize close semantic matches, reward structural similarity
        creativity = siglip_dist / max(dino_dist, 0.01)
        candidates.append({
            "uuid": nb_uuid,
            "dino_dist": round(dino_dist, 4),
            "siglip_dist": round(siglip_dist, 4),
            "creativity": round(creativity, 2),
        })

    # Sort by creativity score (highest = most interesting structural match with different meaning)
    candidates.sort(key=lambda x: -x["creativity"])
    return {"uuid": query_uuid, "neighbors": candidates[:8]}


def render_creative_drift():
    # type: () -> str
    """Creative drift — structurally similar but semantically different images."""
    import random
    tbl, df = _get_lance()
    if tbl is None:
        return page_shell("Drift", "<h1>Drift</h1><p>Vector store not available.</p>", active="creative-drift")

    all_uuids = df["uuid"].tolist()
    start_uuid = random.choice(all_uuids)
    GCS = "https://storage.googleapis.com/myproject-public-assets/art/MADphotos/v/original"

    content = f"""<style>
  .drift-hero {{
    text-align: center;
    margin-bottom: var(--space-6);
  }}
  .drift-hero h1 {{
    font-size: 28px; font-weight: 800; letter-spacing: -0.02em; margin: 0;
  }}
  .drift-hero p {{
    font-size: var(--text-sm); color: var(--muted); margin-top: var(--space-2);
    max-width: 520px; margin-left: auto; margin-right: auto; line-height: var(--leading-relaxed);
  }}
  .drift-controls {{
    display: flex; gap: var(--space-2); justify-content: center;
    margin-bottom: var(--space-6);
  }}
  .drift-btn {{
    font-family: var(--font-sans); font-size: var(--text-sm); font-weight: 600;
    padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm);
    border: 1px solid var(--border); background: var(--card-bg); color: var(--fg);
    cursor: pointer; transition: all var(--duration-fast);
  }}
  .drift-btn:hover {{ border-color: var(--border-strong); background: var(--hover-overlay); }}
  .drift-trail {{
    display: flex; gap: 4px; justify-content: center; align-items: center;
    margin-bottom: var(--space-6); flex-wrap: wrap;
  }}
  .drift-trail-item {{
    width: 40px; height: 40px; border-radius: var(--radius-sm);
    overflow: hidden; cursor: pointer; border: 2px solid transparent;
    transition: border-color var(--duration-fast); flex-shrink: 0;
  }}
  .drift-trail-item:hover {{ border-color: var(--muted); }}
  .drift-trail-item.current {{ border-color: var(--apple-purple); }}
  .drift-trail-item img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .drift-trail-arrow {{ color: var(--muted); font-size: 12px; flex-shrink: 0; }}
  .drift-pair {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4);
    margin-bottom: var(--space-6);
    align-items: start;
  }}
  .drift-query-wrap {{
    position: relative;
  }}
  .drift-query-wrap img {{
    width: 100%; border-radius: var(--radius-md);
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  }}
  .drift-query-label {{
    position: absolute; top: var(--space-2); left: var(--space-2);
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.05em; padding: 2px 8px; border-radius: var(--radius-full, 9999px);
    color: white; background: rgba(0,0,0,0.5); backdrop-filter: blur(4px);
  }}
  .drift-match-wrap {{
    position: relative; cursor: pointer;
    transition: transform var(--duration-fast);
  }}
  .drift-match-wrap:hover {{ transform: scale(1.02); }}
  .drift-match-wrap img {{
    width: 100%; border-radius: var(--radius-md);
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  }}
  .drift-match-score {{
    position: absolute; bottom: var(--space-2); right: var(--space-2);
    display: flex; gap: var(--space-1); align-items: center;
  }}
  .drift-match-score span {{
    font-family: var(--font-mono); font-size: 10px; font-weight: 600;
    padding: 2px 6px; border-radius: var(--radius-sm);
    backdrop-filter: blur(4px);
  }}
  .drift-score-close {{ color: white; background: rgba(52,199,89,0.8); }}
  .drift-score-far {{ color: white; background: rgba(255,55,95,0.8); }}
  .drift-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-3);
    margin-bottom: var(--space-4);
  }}
  .drift-card {{
    position: relative; border-radius: var(--radius-sm);
    overflow: hidden; cursor: pointer; aspect-ratio: 1;
    transition: transform var(--duration-fast);
  }}
  .drift-card:hover {{ transform: scale(1.05); }}
  .drift-card img {{
    width: 100%; height: 100%; object-fit: cover; display: block;
    opacity: 0; transition: opacity 0.5s;
  }}
  .drift-card img.loaded {{ opacity: 1; }}
  .drift-card .drift-card-scores {{
    position: absolute; bottom: 0; left: 0; right: 0;
    display: flex; justify-content: space-between;
    padding: 2px 4px; font-family: var(--font-mono); font-size: 9px; font-weight: 600;
    background: linear-gradient(transparent, rgba(0,0,0,0.6));
    color: white;
  }}
  .drift-explainer {{
    text-align: center; font-size: var(--text-xs); color: var(--muted);
    margin-bottom: var(--space-4);
  }}
  @media (max-width: 700px) {{
    .drift-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .drift-pair {{ grid-template-columns: 1fr; }}
  }}
</style>

<div class="drift-hero">
  <h1>Drift</h1>
  <p>A bridge matches a ribcage. A shoe matches a skateboard ramp. Same geometry, different worlds. These images share visual structure (DINOv2) but mean completely different things (SigLIP). The most creative connections in the collection.</p>
</div>

<div class="drift-controls">
  <button class="drift-btn" onclick="driftRandom()">Random</button>
  <button class="drift-btn" onclick="driftBack()" id="drift-back-btn" style="display:none">Back</button>
</div>

<div class="drift-trail" id="drift-trail"></div>
<div class="drift-explainer"><span style="color:var(--apple-green)">\\u25cf</span> structure &nbsp; <span style="color:var(--apple-pink)">\\u25cf</span> meaning &mdash; green = close, pink = far</div>
<div id="drift-content"></div>

<script>
(function() {{
  var GCS = "{GCS}";
  var history = [];
  var currentUuid = "{start_uuid}";

  function thumbUrl(uuid) {{ return GCS + "/thumb/jpeg/" + uuid + ".jpg"; }}
  function displayUrl(uuid) {{ return GCS + "/display/jpeg/" + uuid + ".jpg"; }}
  function loadImg(img) {{ img.onload = function() {{ img.classList.add("loaded"); }}; }}

  function renderTrail() {{
    var el = document.getElementById("drift-trail");
    el.innerHTML = "";
    var trail = history.slice(-10);
    for (var i = 0; i < trail.length; i++) {{
      var item = document.createElement("div");
      item.className = "drift-trail-item";
      var img = document.createElement("img");
      img.src = thumbUrl(trail[i]);
      item.appendChild(img);
      (function(uuid) {{ item.onclick = function() {{ navigate(uuid); }}; }})(trail[i]);
      el.appendChild(item);
      if (i < trail.length - 1) {{
        var arrow = document.createElement("span");
        arrow.className = "drift-trail-arrow";
        arrow.textContent = "\\u203a";
        el.appendChild(arrow);
      }}
    }}
    if (trail.length > 0) {{
      var arrow = document.createElement("span");
      arrow.className = "drift-trail-arrow";
      arrow.textContent = "\\u203a";
      el.appendChild(arrow);
    }}
    var cur = document.createElement("div");
    cur.className = "drift-trail-item current";
    var curImg = document.createElement("img");
    curImg.src = thumbUrl(currentUuid);
    cur.appendChild(curImg);
    el.appendChild(cur);
    document.getElementById("drift-back-btn").style.display = history.length > 0 ? "" : "none";
  }}

  function navigate(uuid) {{
    if (uuid === currentUuid) return;
    history.push(currentUuid);
    currentUuid = uuid;
    load(uuid);
  }}

  window.driftRandom = function() {{
    fetch("/api/drift/random").then(function(r) {{ return r.json(); }}).then(function(d) {{
      if (d.uuid) navigate(d.uuid);
    }});
  }};

  window.driftBack = function() {{
    if (history.length === 0) return;
    currentUuid = history.pop();
    load(currentUuid);
  }};

  function load(uuid) {{
    var content = document.getElementById("drift-content");
    content.innerHTML = '<p style="text-align:center;color:var(--muted);padding:var(--space-6)">Finding creative connections...</p>';

    fetch("/api/drift/" + uuid).then(function(r) {{ return r.json(); }}).then(function(data) {{
      content.innerHTML = "";
      if (!data.neighbors || data.neighbors.length === 0) return;

      // Top match: large side-by-side pair
      var top = data.neighbors[0];
      var pair = document.createElement("div");
      pair.className = "drift-pair";

      var queryWrap = document.createElement("div");
      queryWrap.className = "drift-query-wrap";
      var qImg = document.createElement("img");
      qImg.src = displayUrl(uuid);
      loadImg(qImg);
      queryWrap.appendChild(qImg);
      var qLabel = document.createElement("div");
      qLabel.className = "drift-query-label";
      qLabel.textContent = "query";
      queryWrap.appendChild(qLabel);
      pair.appendChild(queryWrap);

      var matchWrap = document.createElement("div");
      matchWrap.className = "drift-match-wrap";
      var mImg = document.createElement("img");
      mImg.src = displayUrl(top.uuid);
      loadImg(mImg);
      matchWrap.appendChild(mImg);
      var scores = document.createElement("div");
      scores.className = "drift-match-score";
      scores.innerHTML = '<span class="drift-score-close">\\u0394struct ' + top.dino_dist.toFixed(3) + '</span><span class="drift-score-far">\\u0394meaning ' + top.siglip_dist.toFixed(3) + '</span>';
      matchWrap.appendChild(scores);
      matchWrap.onclick = function() {{ navigate(top.uuid); }};
      pair.appendChild(matchWrap);

      content.appendChild(pair);

      // Remaining matches as grid
      if (data.neighbors.length > 1) {{
        var grid = document.createElement("div");
        grid.className = "drift-grid";
        for (var i = 1; i < data.neighbors.length; i++) {{
          var nb = data.neighbors[i];
          var card = document.createElement("div");
          card.className = "drift-card";
          var img = document.createElement("img");
          img.src = thumbUrl(nb.uuid);
          loadImg(img);
          card.appendChild(img);
          var sc = document.createElement("div");
          sc.className = "drift-card-scores";
          sc.innerHTML = '<span>\\u25b2' + nb.dino_dist.toFixed(2) + '</span><span>\\u25bc' + nb.siglip_dist.toFixed(2) + '</span>';
          card.appendChild(sc);
          (function(nbuuid) {{ card.onclick = function() {{ navigate(nbuuid); }}; }})(nb.uuid);
          grid.appendChild(card);
        }}
        content.appendChild(grid);
      }}
    }});
    renderTrail();
  }}

  load(currentUuid);
  renderTrail();
}})();
</script>"""

    return page_shell("Drift", content, active="creative-drift")


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
                f'<img src="https://storage.googleapis.com/myproject-public-assets/art/MADphotos/v/blind/{uid}_{method}.jpg" loading="lazy" alt="Option {letter}">'
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
var _cs = getComputedStyle(document.documentElement);
var METHOD_COLORS = { original: _cs.getPropertyValue('--muted').trim() || "#86868B", enhanced_v1: _cs.getPropertyValue('--apple-blue').trim() || "#007AFF", enhanced_v2: _cs.getPropertyValue('--apple-green').trim() || "#34C759" };

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
    html += '<div style="text-align:center;margin-top:16px;font-size:13px;color:var(--muted);">Skipped: ' + skipped + ' rows</div>';
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

def get_journal_html():
    """Return just the journal content HTML (styles + body) without page shell."""
    if not JOURNAL_PATH.exists():
        return "<p>No journal found.</p>"
    # render_journal() returns page_shell("Journal de Bord", content, active="journal")
    # We need to call the inner logic. Easier: call render_journal and extract <div class="main-content">
    # Actually, let's build the content directly by reusing the render_journal logic.
    # The render_journal function builds journal_content = f"""<style>...</style>{body}"""
    # and then returns page_shell("Journal de Bord", journal_content, active="journal")
    # We can just call it and extract what we need, or duplicate the content building.
    # Simplest approach: since render_journal() calls page_shell() which wraps in full HTML,
    # let's instead build a content-only version.
    full_html = render_journal()
    # Extract the main-content div contents
    import re as _re
    m = _re.search(r'<div class="main-content">(.*?)<footer', full_html, _re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: return everything between </nav> and </body>
    m = _re.search(r'</nav>\s*<div class="main-content">(.*?)</div>\s*<script', full_html, _re.DOTALL)
    if m:
        return m.group(1).strip()
    return "<p>Could not parse journal content.</p>"


def get_instructions_html():
    """Return just the instructions content HTML without page shell."""
    full_html = render_instructions()
    import re as _re
    m = _re.search(r'<div class="main-content">(.*?)<footer', full_html, _re.DOTALL)
    if m:
        return m.group(1).strip()
    return "<p>Could not parse instructions content.</p>"


def get_mosaics_data():
    """Return mosaics catalog as a list of dicts."""
    meta_path = MOSAIC_DIR / "mosaics.json"
    if meta_path.exists():
        mosaics = json.loads(meta_path.read_text())
        return [{"title": m["title"], "description": m["desc"],
                 "filename": m["file"], "count": m["count"]} for m in mosaics]
    return []


def get_cartoon_data():
    """Return cartoon pairs from the database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    pairs = []
    try:
        for r in conn.execute("""
            SELECT v.image_uuid, v.variant_id, i.category, i.subcategory,
                   COALESCE(g.alt_text, '') as caption
            FROM ai_variants v
            JOIN images i ON v.image_uuid = i.uuid
            LEFT JOIN gemini_analysis g ON v.image_uuid = g.image_uuid
            WHERE v.variant_type = 'cartoon' AND v.generation_status = 'success'
            ORDER BY i.category, i.subcategory, v.image_uuid
        """).fetchall():
            pairs.append({
                "uuid": r["image_uuid"],
                "variant_uuid": r["variant_id"],
                "category": r["category"],
                "subcategory": r["subcategory"] or "Landscape",
                "caption": r["caption"],
            })
    except Exception:
        pass
    conn.close()
    return pairs


def generate_signal_inspector_data():
    """Generate signal inspector data: 300 stratified images with all signals."""
    import random
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]

    # Get aesthetic quartile boundaries
    scores = [r[0] for r in conn.execute(
        "SELECT score FROM aesthetic_scores ORDER BY score"
    ).fetchall()]
    if scores:
        q1 = scores[len(scores)//4]
        q2 = scores[len(scores)//2]
        q3 = scores[3*len(scores)//4]
    else:
        q1, q2, q3 = 4, 6, 8

    # Get camera distribution
    cameras = conn.execute(
        "SELECT camera_body, COUNT(*) as cnt FROM images GROUP BY camera_body ORDER BY cnt DESC"
    ).fetchall()
    camera_counts = {r["camera_body"]: r["cnt"] for r in cameras}
    total_imgs = sum(camera_counts.values())

    # Sample 300 images: proportional by camera, even by quartile
    sample_uuids = set()
    target = 300
    per_quartile = target // 4

    for q_idx, (lo, hi) in enumerate([(0, q1), (q1, q2), (q2, q3), (q3, 11)]):
        # Get images in this quartile
        uuids_in_q = [r[0] for r in conn.execute("""
            SELECT i.uuid FROM images i
            JOIN aesthetic_scores a ON i.uuid = a.image_uuid
            WHERE a.score >= ? AND a.score < ?
        """, (lo, hi)).fetchall()]
        random.shuffle(uuids_in_q)
        # Take proportional per camera within this quartile
        needed = per_quartile
        for uuid in uuids_in_q:
            if len(sample_uuids) >= target:
                break
            sample_uuids.add(uuid)
            needed -= 1
            if needed <= 0:
                break

    # Fill remainder randomly if needed
    if len(sample_uuids) < target:
        all_uuids = [r[0] for r in conn.execute("SELECT uuid FROM images").fetchall()]
        random.shuffle(all_uuids)
        for u in all_uuids:
            if u not in sample_uuids:
                sample_uuids.add(u)
            if len(sample_uuids) >= target:
                break

    # Build full signal records
    images = []
    for uuid in sample_uuids:
        img = conn.execute("SELECT uuid, category, subcategory, camera_body, width, height FROM images WHERE uuid=?", (uuid,)).fetchone()
        if not img:
            continue

        rec = {
            "uuid": img["uuid"],
            "thumb": f"/rendered/thumb/jpeg/{img['uuid']}.jpg",
            "display": f"/rendered/display/jpeg/{img['uuid']}.jpg",
            "camera": img["camera_body"],
            "w": img["width"] or 0,
            "h": img["height"] or 0,
        }

        # Gemini analysis
        g = conn.execute("SELECT * FROM gemini_analysis WHERE image_uuid=?", (uuid,)).fetchone()
        if g:
            rec["caption"] = g["alt_text"] or ""
            rec["alt"] = g["alt_text"] or ""
            rec["style"] = g["grading_style"] or ""
            rec["grading"] = g["grading_style"] or ""
            rec["time"] = g["time_of_day"] or ""
            rec["setting"] = g["setting"] or ""
            rec["exposure"] = g["exposure"] or ""
            rec["composition"] = g["composition_technique"] or ""
            rec["weather"] = g["weather"] or ""
            rec["sharpness"] = g["sharpness"] or ""
            try:
                rec["vibes"] = json.loads(g["vibe"]) if g["vibe"] else []
            except:
                rec["vibes"] = []
        else:
            rec.update({"caption": "", "alt": "", "style": "", "grading": "",
                       "time": "", "setting": "", "exposure": "", "composition": "",
                       "weather": "", "sharpness": "",
                       "vibes": []})

        # Scene classification
        sc_row = conn.execute("SELECT scene_1, environment FROM scene_classification WHERE image_uuid=?", (uuid,)).fetchone()
        if sc_row:
            rec["scene"] = sc_row["scene_1"] or ""
            rec["environment"] = sc_row["environment"] or ""
        else:
            rec["scene"] = ""
            rec["environment"] = ""

        # Style classification
        sc = conn.execute("SELECT style FROM style_classification WHERE image_uuid=?", (uuid,)).fetchone()
        if sc:
            rec["style"] = sc["style"] or rec.get("style", "")

        # Aesthetic score
        ae = conn.execute("SELECT score FROM aesthetic_scores WHERE image_uuid=?", (uuid,)).fetchone()
        rec["aesthetic"] = round(float(ae["score"]), 1) if ae else 0

        # Dominant colors (top 5)
        colors = conn.execute(
            "SELECT hex, percentage, color_name FROM dominant_colors WHERE image_uuid=? ORDER BY percentage DESC LIMIT 5",
            (uuid,)
        ).fetchall()
        rec["colors"] = [{"hex": c["hex"] or "#000", "pct": round(float(c["percentage"] or 0), 1), "name": c["color_name"] or ""} for c in colors]

        # Depth
        de = conn.execute("SELECT near_pct, mid_pct, far_pct FROM depth_estimation WHERE image_uuid=?", (uuid,)).fetchone()
        if de:
            rec["depth"] = {"near": round(float(de["near_pct"] or 0), 1), "mid": round(float(de["mid_pct"] or 0), 1), "far": round(float(de["far_pct"] or 0), 1)}
        else:
            rec["depth"] = {"near": 0, "mid": 0, "far": 0}

        # Objects
        objs = conn.execute(
            "SELECT label, confidence FROM object_detections WHERE image_uuid=? ORDER BY confidence DESC LIMIT 10",
            (uuid,)
        ).fetchall()
        rec["objects"] = [{"label": o["label"], "conf": round(float(o["confidence"] or 0), 2)} for o in objs]

        # Faces
        faces = conn.execute(
            "SELECT confidence, face_area_pct FROM face_detections WHERE image_uuid=?",
            (uuid,)
        ).fetchall()
        face_list = []
        for f in faces:
            fe = conn.execute("SELECT dominant_emotion FROM facial_emotions WHERE image_uuid=?", (uuid,)).fetchone()
            face_list.append({
                "conf": round(float(f["confidence"] or 0), 2),
                "area": round(float(f["face_area_pct"] or 0), 3),
                "emotion": fe["dominant_emotion"] if fe else ""
            })
        rec["faces"] = face_list

        # OCR
        ocr = conn.execute(
            "SELECT text FROM ocr_detections WHERE image_uuid=? AND text != ''",
            (uuid,)
        ).fetchall()
        rec["ocr"] = [o["text"] for o in ocr]

        # EXIF
        ex = conn.execute("SELECT focal_length, aperture, shutter_speed, iso, make, model, lens, date_taken FROM exif_metadata WHERE image_uuid=?", (uuid,)).fetchone()
        if ex:
            rec["exif"] = {
                "focal": ex["focal_length"] or 0,
                "aperture": ex["aperture"] or 0,
                "shutter": ex["shutter_speed"] or "",
                "iso": ex["iso"] or 0,
                "make": ex["make"] or "",
                "model": ex["model"] or "",
                "lens": ex["lens"] or "",
                "date": ex["date_taken"] or "",
            }
        else:
            rec["exif"] = {"focal": 0, "aperture": 0, "shutter": "", "iso": 0}

        # Caption from BLIP
        cap = conn.execute("SELECT caption FROM image_captions WHERE image_uuid=?", (uuid,)).fetchone()
        if cap and cap["caption"]:
            rec["blip_caption"] = cap["caption"]

        # aesthetic_scores_v2
        av2 = conn.execute("SELECT topiq_score, musiq_score, laion_score, composite_score FROM aesthetic_scores_v2 WHERE image_uuid=?", (uuid,)).fetchone()
        if av2:
            rec["aesthetic_v2"] = {"topiq": round(float(av2["topiq_score"] or 0), 2), "musiq": round(float(av2["musiq_score"] or 0), 2), "laion": round(float(av2["laion_score"] or 0), 2), "composite": round(float(av2["composite_score"] or 0), 2)}

        # quality_scores
        qs = conn.execute("SELECT technical_score, clip_score, combined_score, sharpness, noise, exposure_quality, contrast FROM quality_scores WHERE image_uuid=?", (uuid,)).fetchone()
        if qs:
            rec["quality"] = {"technical": round(float(qs["technical_score"] or 0), 2), "clip": round(float(qs["clip_score"] or 0), 2), "combined": round(float(qs["combined_score"] or 0), 2)}

        # florence_captions
        fc = conn.execute("SELECT short_caption, detailed_caption FROM florence_captions WHERE image_uuid=?", (uuid,)).fetchone()
        if fc:
            rec["florence"] = {"short": fc["short_caption"] or "", "detailed": fc["detailed_caption"] or ""}

        # image_tags (pipe-delimited)
        tg = conn.execute("SELECT tags, tag_count FROM image_tags WHERE image_uuid=?", (uuid,)).fetchone()
        if tg and tg["tags"]:
            rec["tags"] = [t.strip() for t in tg["tags"].split("|")][:8]

        # open_detections (Grounding DINO)
        od = conn.execute("SELECT label, confidence FROM open_detections WHERE image_uuid=? ORDER BY confidence DESC LIMIT 8", (uuid,)).fetchall()
        rec["open_objects"] = [{"label": o["label"], "conf": round(float(o["confidence"] or 0), 2)} for o in od]

        # face_identities
        fi = conn.execute("SELECT DISTINCT identity_label FROM face_identities WHERE image_uuid=? AND identity_label IS NOT NULL", (uuid,)).fetchall()
        rec["identities"] = [f["identity_label"] for f in fi]

        # foreground_masks
        fg = conn.execute("SELECT foreground_pct, background_pct FROM foreground_masks WHERE image_uuid=?", (uuid,)).fetchone()
        if fg:
            rec["foreground"] = {"fg_pct": round(float(fg["foreground_pct"] or 0), 1), "bg_pct": round(float(fg["background_pct"] or 0), 1)}

        # segmentation_masks
        sg = conn.execute("SELECT segment_count, largest_segment_pct FROM segmentation_masks WHERE image_uuid=?", (uuid,)).fetchone()
        if sg:
            rec["segments"] = {"count": sg["segment_count"] or 0, "largest_pct": round(float(sg["largest_segment_pct"] or 0), 1)}

        # pose_detections
        pd_rows = conn.execute("SELECT pose_score FROM pose_detections WHERE image_uuid=?", (uuid,)).fetchall()
        rec["poses"] = len(pd_rows)

        # saliency_maps
        sal = conn.execute("SELECT peak_x, peak_y, spread, center_bias FROM saliency_maps WHERE image_uuid=?", (uuid,)).fetchone()
        if sal:
            rec["saliency"] = {"peak_x": round(float(sal["peak_x"] or 0), 2), "peak_y": round(float(sal["peak_y"] or 0), 2), "spread": round(float(sal["spread"] or 0), 2), "center_bias": round(float(sal["center_bias"] or 0), 2)}

        # image_locations
        loc = conn.execute("SELECT location_name, latitude, longitude FROM image_locations WHERE image_uuid=?", (uuid,)).fetchone()
        if loc:
            rec["location"] = {"name": loc["location_name"] or "", "lat": loc["latitude"], "lon": loc["longitude"]}

        # image_hashes
        ih = conn.execute("SELECT blur_score, sharpness_score, edge_density, entropy FROM image_hashes WHERE image_uuid=?", (uuid,)).fetchone()
        if ih:
            rec["hashes"] = {"blur": round(float(ih["blur_score"] or 0), 1), "sharpness": round(float(ih["sharpness_score"] or 0), 1), "edge_density": round(float(ih["edge_density"] or 0), 3), "entropy": round(float(ih["entropy"] or 0), 2)}

        # image_analysis
        ia = conn.execute("SELECT mean_brightness, dynamic_range, noise_estimate, est_color_temp FROM image_analysis WHERE image_uuid=?", (uuid,)).fetchone()
        if ia:
            rec["analysis"] = {"brightness": round(float(ia["mean_brightness"] or 0), 1), "dynamic_range": round(float(ia["dynamic_range"] or 0), 1), "noise": round(float(ia["noise_estimate"] or 0), 2), "color_temp": int(ia["est_color_temp"] or 0)}

        # border_crops
        bc = conn.execute("SELECT has_border, border_pct FROM border_crops WHERE image_uuid=?", (uuid,)).fetchone()
        if bc and bc["has_border"]:
            rec["border"] = round(float(bc["border_pct"] or 0), 1)

        images.append(rec)

    conn.close()
    return {
        "sample_size": len(images),
        "total": total,
        "images": images,
    }


def generate_embedding_audit_data():
    """Generate embedding audit data: 100 anchors with per-model neighbors."""
    import random
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    tbl, df = _get_lance()
    if tbl is None or df is None:
        conn.close()
        return {"anchor_count": 0, "neighbor_k": 6, "models": [], "anchors": []}

    # Get scenes for stratification
    scenes = conn.execute(
        "SELECT scene_1, COUNT(*) as cnt FROM scene_classification GROUP BY scene_1 ORDER BY cnt DESC LIMIT 20"
    ).fetchall()

    # Sample ~5 per scene to get ~100
    sample_uuids = []
    per_scene = max(3, 100 // max(len(scenes), 1))
    for scene_row in scenes:
        scene_name = scene_row["scene_1"]
        uuids = [r[0] for r in conn.execute(
            "SELECT image_uuid FROM scene_classification WHERE scene_1=? ORDER BY RANDOM() LIMIT ?",
            (scene_name, per_scene)
        ).fetchall()]
        # Only keep UUIDs that are in the vector store
        valid = [u for u in uuids if u in df["uuid"].values]
        sample_uuids.extend(valid)
        if len(sample_uuids) >= 100:
            break

    sample_uuids = sample_uuids[:100]

    models = ["DINOv2", "SigLIP", "CLIP", "Combined"]
    model_cols = [("dino", "DINOv2"), ("siglip", "SigLIP"), ("clip", "CLIP")]
    k = 6

    anchors = []
    for uuid in sample_uuids:
        matches = df[df["uuid"] == uuid]
        if matches.empty:
            continue
        query_row = matches.iloc[0]

        # Get metadata
        g = conn.execute("SELECT alt_text, vibe FROM gemini_analysis WHERE image_uuid=?", (uuid,)).fetchone()
        sc = conn.execute("SELECT scene_1 FROM scene_classification WHERE image_uuid=?", (uuid,)).fetchone()

        anchor = {
            "uuid": uuid,
            "thumb": f"/rendered/thumb/jpeg/{uuid}.jpg",
            "display": f"/rendered/display/jpeg/{uuid}.jpg",
            "caption": (g["alt_text"] or "") if g else "",
            "scene": (sc["scene_1"] or "") if sc else "",
            "vibes": [],
            "neighbors": {},
            "agreement": {},
        }
        if g and g["vibe"]:
            try:
                anchor["vibes"] = json.loads(g["vibe"])
            except:
                pass

        # Per-model neighbor search
        all_neighbor_sets = {}
        for col, name in model_cols:
            query_vec = query_row[col]
            results = tbl.search(query_vec, vector_column_name=col).limit(k + 1).to_pandas()
            neighbors = results[results["uuid"] != uuid].head(k)
            nb_list = []
            nb_uuids = set()
            for _, nb_row in neighbors.iterrows():
                nb_uuid = nb_row["uuid"]
                # Convert distance to similarity score (1 / (1 + dist))
                dist = float(nb_row["_distance"])
                score = round(1.0 / (1.0 + dist), 3)
                nb_list.append({
                    "uuid": nb_uuid,
                    "thumb": f"/rendered/thumb/jpeg/{nb_uuid}.jpg",
                    "score": score,
                })
                nb_uuids.add(nb_uuid)
            anchor["neighbors"][name] = nb_list
            all_neighbor_sets[name] = nb_uuids

        # Combined: average distances across models, re-rank
        try:
            import numpy as np
            combined_scores = {}
            for col, name in model_cols:
                query_vec = query_row[col]
                results = tbl.search(query_vec, vector_column_name=col).limit(30).to_pandas()
                for _, nb_row in results.iterrows():
                    nb_uuid = nb_row["uuid"]
                    if nb_uuid == uuid:
                        continue
                    dist = float(nb_row["_distance"])
                    score = 1.0 / (1.0 + dist)
                    combined_scores[nb_uuid] = combined_scores.get(nb_uuid, 0) + score / 3.0

            # Sort by combined score
            sorted_combined = sorted(combined_scores.items(), key=lambda x: -x[1])[:k]
            combined_list = []
            combined_uuids = set()
            for nb_uuid, score in sorted_combined:
                combined_list.append({
                    "uuid": nb_uuid,
                    "thumb": f"/rendered/thumb/jpeg/{nb_uuid}.jpg",
                    "score": round(score, 3),
                })
                combined_uuids.add(nb_uuid)
            anchor["neighbors"]["Combined"] = combined_list
            all_neighbor_sets["Combined"] = combined_uuids
        except Exception:
            anchor["neighbors"]["Combined"] = []
            all_neighbor_sets["Combined"] = set()

        # Agreement stats
        all_nb = set()
        for s in all_neighbor_sets.values():
            all_nb |= s
        shared_2plus = sum(1 for u in all_nb if sum(1 for s in all_neighbor_sets.values() if u in s) >= 2)
        shared_3plus = sum(1 for u in all_nb if sum(1 for s in all_neighbor_sets.values() if u in s) >= 3)
        anchor["agreement"] = {
            "shared_2plus": shared_2plus,
            "shared_3plus": shared_3plus,
            "unique_neighbors": len(all_nb),
        }

        anchors.append(anchor)

    conn.close()
    return {
        "anchor_count": len(anchors),
        "neighbor_k": k,
        "models": models,
        "anchors": anchors,
    }


def generate_collection_coverage_data():
    """Generate collection coverage data: which images appear in which experiences."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]

    # Load photos.json (exported gallery data)
    photos_path = PROJECT_ROOT / "frontend" / "show" / "data" / "photos.json"
    if not photos_path.exists():
        # Try alternate location
        photos_path = PROJECT_ROOT / "frontend" / "show" / "photos.json"

    photos = []
    if photos_path.exists():
        try:
            photos = json.loads(photos_path.read_text())
            if isinstance(photos, dict):
                photos = photos.get("photos", photos.get("images", []))
        except:
            pass

    # Define experience pools (approximate server-side)
    # Each experience filters differently
    experiences = []
    uuid_appearances = {}  # uuid -> count of experiences it appears in

    def count_pool(name, pool):
        """Register a pool of UUIDs for an experience."""
        uuids = set(p.get("uuid", p.get("id", "")) for p in pool if p.get("uuid") or p.get("id"))
        experiences.append({
            "name": name,
            "pool_size": len(uuids),
            "pct_of_collection": round(len(uuids) / total * 100, 1) if total else 0,
        })
        for u in uuids:
            uuid_appearances[u] = uuid_appearances.get(u, 0) + 1
        return uuids

    if photos:
        # Grid: all photos
        count_pool("Grid", photos)

        # Drift / Similarity: needs vectors — all photos with vectors
        count_pool("Drift", photos)

        # Colors: photos with palette data
        count_pool("Colors", [p for p in photos if p.get("palette") or p.get("colors")])

        # Bento: needs aspect ratio + aesthetic score > 6
        count_pool("Bento", [p for p in photos if (p.get("aesthetic") or p.get("score", 0)) >= 6])

        # Game: photos with multiple vibes
        count_pool("Game", [p for p in photos if len(p.get("vibes", [])) >= 2])

        # Stream: all photos (random stream)
        count_pool("Stream", photos)

        # Domino: photos with dominant colors
        count_pool("Domino", [p for p in photos if p.get("palette") or p.get("colors")])

        # Faces: photos with faces
        count_pool("Faces", [p for p in photos if p.get("faces") and len(p.get("faces", [])) > 0])

        # Compass: photos with scene data
        count_pool("Compass", [p for p in photos if p.get("scene")])

        # NYU: all photos (special layout)
        count_pool("NYU", photos)

        # Confetti: photos with aesthetic > 7
        count_pool("Confetti", [p for p in photos if (p.get("aesthetic") or p.get("score", 0)) >= 7])

        # Cinema: photos with cinematic style or high aesthetic
        count_pool("Cinema", [p for p in photos if (p.get("aesthetic") or p.get("score", 0)) >= 7.5 or p.get("style") == "cinematic"])

        # Reveal: all photos (random reveal)
        count_pool("Reveal", photos)

        # Sort By: uses photos.json (all)
        count_pool("Sort By", photos)

    # Sort experiences by pool size descending
    experiences.sort(key=lambda x: -x["pool_size"])

    # Distribution: how many images appear in N experiences
    max_appearances = max(uuid_appearances.values()) if uuid_appearances else 0
    distribution = []
    # Count images that appear in 0 experiences
    in_any = len(uuid_appearances)
    in_zero = total - in_any
    distribution.append({"appearances": 0, "count": in_zero})
    for n in range(1, max_appearances + 1):
        count = sum(1 for v in uuid_appearances.values() if v == n)
        if count > 0:
            distribution.append({"appearances": n, "count": count})

    # Dimension bias analysis
    dimensions = {}

    # Camera bias
    full_cameras = {}
    for r in conn.execute("SELECT camera_body, COUNT(*) as cnt FROM images GROUP BY camera_body ORDER BY cnt DESC").fetchall():
        full_cameras[r["camera_body"]] = round(r["cnt"] / total * 100, 1) if total else 0

    # Curated = photos that appear in at least one experience
    curated_uuids = set(uuid_appearances.keys())
    curated_total = len(curated_uuids)

    if curated_uuids and photos:
        curated_cameras = {}
        curated_scenes = {}
        curated_times = {}
        curated_styles = {}
        curated_gradings = {}

        photo_map = {p.get("uuid", p.get("id", "")): p for p in photos}
        for u in curated_uuids:
            p = photo_map.get(u, {})
            cam = p.get("camera", "")
            if cam:
                curated_cameras[cam] = curated_cameras.get(cam, 0) + 1
            scene = p.get("scene", "")
            if scene:
                curated_scenes[scene] = curated_scenes.get(scene, 0) + 1
            tod = p.get("time", p.get("time_of_day", ""))
            if tod:
                curated_times[tod] = curated_times.get(tod, 0) + 1
            st = p.get("style", "")
            if st:
                curated_styles[st] = curated_styles.get(st, 0) + 1
            gr = p.get("grading", "")
            if gr:
                curated_gradings[gr] = curated_gradings.get(gr, 0) + 1

        def to_pct(d, tot):
            return {k: round(v / tot * 100, 1) for k, v in sorted(d.items(), key=lambda x: -x[1])[:10]} if tot else {}

        # Full collection dimension distributions from DB
        full_scenes = {}
        for r in conn.execute("SELECT scene_1, COUNT(*) as cnt FROM scene_classification WHERE scene_1 IS NOT NULL GROUP BY scene_1 ORDER BY cnt DESC LIMIT 10").fetchall():
            full_scenes[r["scene_1"]] = round(r["cnt"] / total * 100, 1)

        full_times = {}
        for r in conn.execute("SELECT time_of_day, COUNT(*) as cnt FROM gemini_analysis WHERE time_of_day IS NOT NULL GROUP BY time_of_day ORDER BY cnt DESC").fetchall():
            full_times[r["time_of_day"]] = round(r["cnt"] / total * 100, 1)

        full_styles = {}
        for r in conn.execute("SELECT style, COUNT(*) as cnt FROM style_classification GROUP BY style ORDER BY cnt DESC LIMIT 10").fetchall():
            full_styles[r["style"]] = round(r["cnt"] / total * 100, 1)

        full_gradings = {}
        for r in conn.execute("SELECT grading_style, COUNT(*) as cnt FROM gemini_analysis WHERE grading_style IS NOT NULL AND raw_json != '' GROUP BY grading_style ORDER BY cnt DESC LIMIT 10").fetchall():
            full_gradings[r["grading_style"]] = round(r["cnt"] / total * 100, 1)

        dimensions = {
            "camera": {"full": full_cameras, "curated": to_pct(curated_cameras, curated_total)},
            "scene": {"full": full_scenes, "curated": to_pct(curated_scenes, curated_total)},
            "time_of_day": {"full": full_times, "curated": to_pct(curated_times, curated_total)},
            "style": {"full": full_styles, "curated": to_pct(curated_styles, curated_total)},
            "grading": {"full": full_gradings, "curated": to_pct(curated_gradings, curated_total)},
        }

    conn.close()
    return {
        "total": total,
        "in_at_least_one": in_any,
        "in_zero": in_zero,
        "pct_covered": round(in_any / total * 100, 1) if total else 0,
        "distribution": distribution,
        "experiences": experiences,
        "dimensions": dimensions,
    }


def generate_schema_data():
    """Return full DB schema: tables, columns, row counts, model attribution, sample values."""
    import os
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    db_size = os.path.getsize(str(DB_PATH))
    total_images = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]

    # Model attribution for each table
    model_map = {
        "images": {"model": "Import Pipeline", "category": "core", "description": "Master image table — one row per photograph with camera, format, dimensions, curation status"},
        "aesthetic_scores": {"model": "LAION Aesthetics (NIMA)", "category": "v1_signal", "description": "Aesthetic quality score 1-10. WARNING: nearly useless — avg 9.9, range 8.2-10.0, zero discrimination"},
        "aesthetic_scores_v2": {"model": "TOPIQ + MUSIQ + LAION", "category": "v2_signal", "description": "Three independent quality models combined into a composite score with real spread"},
        "quality_scores": {"model": "Technical + CLIP", "category": "v2_signal", "description": "Technical quality (sharpness, noise, exposure, contrast) + CLIP aesthetic alignment"},
        "depth_estimation": {"model": "Depth Anything v2 Large", "category": "v1_signal", "description": "Monocular depth estimation — near/mid/far percentages and scene complexity"},
        "scene_classification": {"model": "Places365", "category": "v1_signal", "description": "Scene type classification (top 3 scenes + environment label)"},
        "style_classification": {"model": "Rule-based classifier", "category": "v1_signal", "description": "Visual style labels (documentary, street, portrait, etc.)"},
        "image_captions": {"model": "BLIP2", "category": "v1_signal", "description": "Natural language image captions"},
        "florence_captions": {"model": "Florence-2-base", "category": "v2_signal", "description": "Three-tier captions: short, detailed, more detailed"},
        "ocr_detections": {"model": "EasyOCR", "category": "v1_signal", "description": "Text detected in images with bounding boxes and confidence"},
        "object_detections": {"model": "YOLOv8n", "category": "v1_signal", "description": "Object detection with labels, confidence, and bounding boxes"},
        "open_detections": {"model": "Grounding DINO tiny", "category": "v2_signal", "description": "Open-vocabulary object detection — no fixed label set, finds anything"},
        "face_detections": {"model": "YuNet / RetinaFace", "category": "v1_signal", "description": "Face locations with landmarks (eyes, nose, mouth) and area percentage"},
        "facial_emotions": {"model": "DeepFace", "category": "v1_signal", "description": "Dominant emotion per detected face with confidence scores"},
        "face_identities": {"model": "InsightFace ArcFace + DBSCAN", "category": "v2_signal", "description": "Face identity clustering — groups faces into identity clusters across images"},
        "dominant_colors": {"model": "K-means LAB clustering", "category": "v1_signal", "description": "Top 5 dominant colors per image with hex, RGB, LAB, percentage, and color name"},
        "image_tags": {"model": "CLIP zero-shot", "category": "v2_signal", "description": "Open-vocabulary tags via CLIP zero-shot classification (pipe-delimited)"},
        "exif_metadata": {"model": "EXIF Parser", "category": "v1_signal", "description": "Camera make/model, lens, focal length, aperture, shutter speed, ISO, GPS, date"},
        "image_hashes": {"model": "Perceptual Hashing", "category": "v1_signal", "description": "pHash, aHash, dHash, wHash for dedup + blur score, sharpness, edge density, entropy"},
        "image_analysis": {"model": "NumPy / OpenCV", "category": "v1_signal", "description": "Pixel-level stats: brightness, dynamic range, noise, color temperature, histogram"},
        "gemini_analysis": {"model": "Gemini 2.0 Flash", "category": "api_signal", "description": "Rich semantic analysis: exposure, composition, grading, time of day, weather, vibes, alt text"},
        "foreground_masks": {"model": "rembg u2net", "category": "v2_signal", "description": "Foreground/background segmentation with percentages and centroid"},
        "segmentation_masks": {"model": "SAM 2.1 hiera-tiny", "category": "v2_signal", "description": "Segment Anything — segment count, largest segment, complexity metrics"},
        "pose_detections": {"model": "YOLOv8n-pose", "category": "v2_signal", "description": "Human pose estimation with 17 keypoints per person"},
        "saliency_maps": {"model": "OpenCV Spectral Residual", "category": "v2_signal", "description": "Visual attention maps — peak saliency location, spread, center bias, rule-of-thirds"},
        "image_locations": {"model": "EXIF GPS extraction", "category": "v2_signal", "description": "Geocoded location names from GPS coordinates in EXIF data"},
        "border_crops": {"model": "OpenCV Edge Detection", "category": "v2_signal", "description": "Border/frame detection with crop suggestions and border percentage"},
        "enhancement_plans": {"model": "Signal-driven Engine v1", "category": "pipeline", "description": "Per-image enhancement strategy based on signal analysis"},
        "enhancement_plans_v2": {"model": "Signal-driven Engine v2", "category": "pipeline", "description": "V2 with depth/scene/style/vibe/face-aware adjustments"},
        "ai_variants": {"model": "Imagen 3 (Google)", "category": "api_signal", "description": "AI-generated image variants (cartoon style) from enhanced source images"},
        "tiers": {"model": "Render Pipeline", "category": "pipeline", "description": "Rendered image tiers (thumb, display, enhanced). WARNING: has duplicate rows per image"},
        "pipeline_runs": {"model": "Pipeline Orchestrator", "category": "pipeline", "description": "Pipeline execution history with status, timing, error messages"},
        "gcs_uploads": {"model": "GCS Upload Script", "category": "pipeline", "description": "Google Cloud Storage upload tracking"},
        "schema_version": {"model": "Database", "category": "core", "description": "Schema version tracking"},
    }

    tables = []
    total_rows = 0
    for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        name = t[0]
        cnt = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        total_rows += cnt

        columns = []
        for c in conn.execute(f"PRAGMA table_info([{name}])").fetchall():
            columns.append({"name": c[1], "type": c[2], "pk": bool(c[5])})

        meta = model_map.get(name, {"model": "Unknown", "category": "other", "description": ""})

        # Coverage: how many of 9011 images have data in this table
        has_uuid = any(col["name"] == "image_uuid" for col in columns)
        if has_uuid and name != "images":
            distinct = conn.execute(f"SELECT COUNT(DISTINCT image_uuid) FROM [{name}]").fetchone()[0]
            coverage = round(distinct / total_images * 100, 1) if total_images else 0
        elif name == "images":
            distinct = cnt
            coverage = 100.0
        else:
            distinct = None
            coverage = None

        # Sample values for interesting columns (skip blobs and long text)
        samples = {}
        skip_cols = {"raw_json", "raw_exif", "embedding", "plan_json", "exif_data",
                     "histogram_json", "keypoints_json", "segments_json", "bbox_json",
                     "emotion_scores", "confidence_json", "config", "error_message",
                     "prompt", "negative_prompt", "original_path", "local_path",
                     "gcs_url", "public_url", "gcs_path", "output_path"}
        for col in columns[:8]:  # First 8 columns max
            if col["name"] in skip_cols or col["name"].endswith("_at"):
                continue
            try:
                vals = conn.execute(
                    f"SELECT DISTINCT [{col['name']}] FROM [{name}] WHERE [{col['name']}] IS NOT NULL LIMIT 5"
                ).fetchall()
                if vals:
                    sample_vals = []
                    for v in vals:
                        val = v[0]
                        if isinstance(val, str) and len(val) > 60:
                            val = val[:60] + "..."
                        elif isinstance(val, bytes):
                            continue
                        sample_vals.append(val)
                    if sample_vals:
                        samples[col["name"]] = sample_vals
            except:
                pass

        tables.append({
            "name": name,
            "rows": cnt,
            "columns": columns,
            "col_count": len(columns),
            "model": meta["model"],
            "category": meta["category"],
            "description": meta["description"],
            "coverage": coverage,
            "distinct_images": distinct,
            "samples": samples,
        })

    conn.close()

    # Category summaries
    categories = {}
    for t in tables:
        cat = t["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "rows": 0, "tables": []}
        categories[cat]["count"] += 1
        categories[cat]["rows"] += t["rows"]
        categories[cat]["tables"].append(t["name"])

    return {
        "db_path": str(DB_PATH),
        "db_size": db_size,
        "total_images": total_images,
        "table_count": len(tables),
        "total_rows": total_rows,
        "categories": categories,
        "tables": tables,
    }


class Handler(BaseHTTPRequestHandler):
    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/stats":
            self._json_response(get_stats())
        elif self.path == "/api/journal":
            self._json_response({"html": get_journal_html()})
        elif self.path == "/api/instructions":
            self._json_response({"html": get_instructions_html()})
        elif self.path == "/api/mosaics":
            self._json_response({"mosaics": get_mosaics_data()})
        elif self.path == "/api/cartoon":
            self._json_response({"pairs": get_cartoon_data()})
        elif self.path == "/api/signal-inspector":
            self._json_response(generate_signal_inspector_data())
        elif self.path == "/api/embedding-audit":
            self._json_response(generate_embedding_audit_data())
        elif self.path == "/api/collection-coverage":
            self._json_response(generate_collection_coverage_data())
        elif self.path == "/api/schema":
            self._json_response(generate_schema_data())
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
                hero_cache = PROJECT_ROOT / "frontend" / "state" / "hero-mosaic.jpg"
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
        elif self.path.startswith("/api/similarity/"):
            uuid_part = self.path[16:]
            if uuid_part == "random":
                import random
                tbl, df = _get_lance()
                if tbl is not None:
                    rand_uuid = random.choice(df["uuid"].tolist())
                    data = json.dumps({"uuid": rand_uuid}).encode()
                else:
                    data = json.dumps({"error": "no vectors"}).encode()
            else:
                result = similarity_search(uuid_part)
                data = json.dumps(result or {"error": "not found"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith("/api/drift/"):
            uuid_part = self.path[11:]
            if uuid_part == "random":
                import random
                tbl, df = _get_lance()
                if tbl is not None:
                    rand_uuid = random.choice(df["uuid"].tolist())
                    data = json.dumps({"uuid": rand_uuid}).encode()
                else:
                    data = json.dumps({"error": "no vectors"}).encode()
            else:
                result = drift_search(uuid_part)
                data = json.dumps(result or {"error": "not found"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/creative-drift":
            html = render_creative_drift().encode()
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
        elif self.path == "/blind-test":
            html = render_blind_test().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
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

def _static_links(html):
    # type: (str) -> str
    """Rewrite server routes to static file paths for GitHub Pages."""
    html = html.replace('href="/"', 'href="state.html"')
    html = html.replace('href="/journal"', 'href="journal.html"')
    html = html.replace('href="/instructions"', 'href="instructions.html"')
    html = html.replace('href="/mosaics"', 'href="mosaics.html"')
    html = html.replace('href="/drift"', 'href="drift.html"')
    html = html.replace('href="/creative-drift"', 'href="creative-drift.html"')
    html = html.replace('href="/blind-test"', 'href="blind-test.html"')
    html = html.replace('src="/mosaic-hero"', 'src="hero-mosaic.jpg"')
    # Thumb and blind test images use absolute GCS URLs — no rewriting needed
    # Mosaic images: inline path
    import re
    html = re.sub(r'src="/mosaics/([^"]+)"', r'src="mosaics/\1"', html)
    # Blind test images use absolute GCS URLs — no rewriting needed
    return html


def generate_static():
    """Write self-contained static HTML files with embedded data for GitHub Pages."""
    docs_dir = OUT_PATH.parent
    docs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1. State (main dashboard)
    stats = get_stats()
    html = PAGE_HTML.replace("%%POLL_MS%%", "0")
    html = html.replace("%%API_URL%%", "inline")
    html = html.replace("%%INLINE_DATA%%", json.dumps(stats))
    html = html.replace('animation: blink 2s infinite;', 'display: none;')
    ts_pretty = datetime.now(timezone.utc).strftime("%B %-d, %Y at %H:%M UTC")
    html = html.replace('System Dashboard</p>',
                         f'As of {ts_pretty}</p>')
    html = _static_links(html)
    OUT_PATH.write_text(html)
    print(f"  state.html ({len(html):,} bytes)")

    # 2. Journal de Bord
    journal_html = _static_links(render_journal())
    (docs_dir / "journal.html").write_text(journal_html)
    print(f"  journal.html ({len(journal_html):,} bytes)")

    # 3. Instructions
    instructions_html = _static_links(render_instructions())
    (docs_dir / "instructions.html").write_text(instructions_html)
    print(f"  instructions.html ({len(instructions_html):,} bytes)")

    # 4. Drift
    drift_html = _static_links(render_drift())
    (docs_dir / "drift.html").write_text(drift_html)
    print(f"  drift.html ({len(drift_html):,} bytes)")

    # 5. Blind Test
    blind_html = _static_links(render_blind_test())
    (docs_dir / "blind-test.html").write_text(blind_html)
    print(f"  blind-test.html ({len(blind_html):,} bytes)")

    # 6. Mosaics
    mosaics_html = _static_links(render_mosaics())
    (docs_dir / "mosaics.html").write_text(mosaics_html)
    print(f"  mosaics.html ({len(mosaics_html):,} bytes)")

    print(f"\nGenerated 6 pages in frontend/state/ — snapshot {ts}")


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
