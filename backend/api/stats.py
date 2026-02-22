"""Dashboard statistics — the main /api/stats endpoint."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ._common import PROJECT_ROOT, DB_PATH, VECTOR_PATH, human_bytes, pct


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
            "medium": r["medium"] or "\u2014",
            "film": r["film_stock"] or "\u2014",
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
    vector_size_human = "\u2014"
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
    base_dir = PROJECT_ROOT / "backend"
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

    # ── Firestore feedback ─────────────────────────────────────
    def _table_exists(name):
        return conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()[0] > 0

    tinder_total = 0
    tinder_accepts = 0
    tinder_rejects = 0
    tinder_by_day = []
    tinder_top_accepted = []
    tinder_top_rejected = []
    couple_likes_total = 0
    couple_by_strategy = []
    couple_approves_total = 0
    couple_rejects_total = 0
    feedback_last_sync = None

    if _table_exists('firestore_tinder_votes'):
        tinder_total = conn.execute("SELECT COUNT(*) FROM firestore_tinder_votes").fetchone()[0]
        tinder_accepts = conn.execute(
            "SELECT COUNT(*) FROM firestore_tinder_votes WHERE vote='accept'"
        ).fetchone()[0]
        tinder_rejects = tinder_total - tinder_accepts
        tinder_by_day = [
            {"date": r[0], "accepts": r[1], "rejects": r[2]}
            for r in conn.execute("""
                SELECT DATE(ts) as d,
                       SUM(CASE WHEN vote='accept' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN vote='reject' THEN 1 ELSE 0 END)
                FROM firestore_tinder_votes
                WHERE ts IS NOT NULL
                GROUP BY d ORDER BY d
            """).fetchall()
        ]
        tinder_top_accepted = [
            {"photo": r[0], "count": r[1]}
            for r in conn.execute("""
                SELECT photo, COUNT(*) as c FROM firestore_tinder_votes
                WHERE vote='accept' GROUP BY photo ORDER BY c DESC LIMIT 10
            """).fetchall()
        ]
        tinder_top_rejected = [
            {"photo": r[0], "count": r[1]}
            for r in conn.execute("""
                SELECT photo, COUNT(*) as c FROM firestore_tinder_votes
                WHERE vote='reject' GROUP BY photo ORDER BY c DESC LIMIT 10
            """).fetchall()
        ]
        row = conn.execute(
            "SELECT MAX(synced_at) FROM firestore_tinder_votes"
        ).fetchone()
        if row and row[0]:
            feedback_last_sync = row[0]

    if _table_exists('firestore_couple_likes'):
        couple_likes_total = conn.execute("SELECT COUNT(*) FROM firestore_couple_likes").fetchone()[0]
        couple_by_strategy = [
            {"strategy": r[0] or "unknown", "count": r[1]}
            for r in conn.execute("""
                SELECT strategy, COUNT(*) as c FROM firestore_couple_likes
                GROUP BY strategy ORDER BY c DESC
            """).fetchall()
        ]
        row = conn.execute(
            "SELECT MAX(synced_at) FROM firestore_couple_likes"
        ).fetchone()
        if row and row[0] and (not feedback_last_sync or row[0] > feedback_last_sync):
            feedback_last_sync = row[0]

    if _table_exists('firestore_couple_approves'):
        couple_approves_total = conn.execute("SELECT COUNT(*) FROM firestore_couple_approves").fetchone()[0]

    if _table_exists('firestore_couple_rejects'):
        couple_rejects_total = conn.execute("SELECT COUNT(*) FROM firestore_couple_rejects").fetchone()[0]

    # ── Picks curation ────────────────────────────────────────
    picks_portrait = 0
    picks_landscape = 0
    picks_votes_total = 0
    picks_votes_accept = 0
    picks_votes_reject = 0
    picks_by_device = []

    picks_json = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
    picks_generated_uuids: set = set()
    if _table_exists('ai_variants'):
        picks_generated_uuids = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT image_uuid FROM ai_variants WHERE review_status='accepted'"
            ).fetchall()
        }
    picks_photography = 0
    picks_generated = 0
    if picks_json.exists():
        try:
            pdata = json.loads(picks_json.read_text())
            all_pick_uuids = set(pdata.get("portrait", [])) | set(pdata.get("landscape", []))
            picks_portrait = len(pdata.get("portrait", []))
            picks_landscape = len(pdata.get("landscape", []))
            picks_generated = len(all_pick_uuids & picks_generated_uuids)
            picks_photography = len(all_pick_uuids) - picks_generated
        except Exception:
            pass

    if _table_exists('firestore_picks_votes'):
        picks_votes_total = conn.execute("SELECT COUNT(*) FROM firestore_picks_votes").fetchone()[0]
        picks_votes_accept = conn.execute(
            "SELECT COUNT(*) FROM firestore_picks_votes WHERE vote='accept'"
        ).fetchone()[0]
        picks_votes_reject = picks_votes_total - picks_votes_accept
        picks_by_device = [
            {"device": r[0] or "unknown", "accepts": r[1], "rejects": r[2]}
            for r in conn.execute("""
                SELECT device,
                       SUM(CASE WHEN vote='accept' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN vote='reject' THEN 1 ELSE 0 END)
                FROM firestore_picks_votes
                GROUP BY device
            """).fetchall()
        ]

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

    from datetime import datetime, timezone
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
        # Picks curation
        "picks": {
            "portrait": picks_portrait,
            "landscape": picks_landscape,
            "total": picks_portrait + picks_landscape,
            "photography": picks_photography,
            "generated": picks_generated,
            "votes_total": picks_votes_total,
            "votes_accept": picks_votes_accept,
            "votes_reject": picks_votes_reject,
            "by_device": picks_by_device,
        },
        # Firestore feedback
        "feedback": {
            "last_sync": feedback_last_sync,
            "tinder": {
                "total": tinder_total,
                "accepts": tinder_accepts,
                "rejects": tinder_rejects,
                "by_day": tinder_by_day,
                "top_accepted": tinder_top_accepted,
                "top_rejected": tinder_top_rejected,
            },
            "couple": {
                "likes": couple_likes_total,
                "by_strategy": couple_by_strategy,
                "approves": couple_approves_total,
                "rejects": couple_rejects_total,
            },
        },
    }
