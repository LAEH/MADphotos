#!/usr/bin/env python3
"""
signals_v2.py — Next-generation signal extraction for MADphotos.

12 phases: fix data corruption, populate missing signals, replace broken models,
upgrade weak ones, and add new CV signals. Each phase loads one model at a time,
processes incrementally, and commits to the database.

Phases:
  1.  fix-blobs        — Fix blob-corrupted exposure_quality in quality_scores
  2.  gps-locations    — Populate image_locations from EXIF GPS data
  3.  aesthetic-v2     — Triple-metric aesthetic scoring (TOPIQ + MUSIQ + LAION)
  4.  depth-large      — Upgrade Depth Anything v2 Small → Large
  5.  face-identity    — Face identity clustering via InsightFace ArcFace
  6.  florence-captions — Detailed captions via Florence-2-large
  7.  sam-segments     — Segmentation mask summary stats via SAM 2.1
  8.  grounding-dino   — Open-vocabulary detection
  9.  ram-tags         — Multi-label image tagging (RAM++ or CLIP fallback)
  10. rembg-foreground — Foreground isolation metrics
  11. pose-detection   — Body pose estimation for images with people
  12. saliency        — Visual saliency analysis (instant, no model download)

Usage:
    python signals_v2.py --list                          # Show all phases + status
    python signals_v2.py                                 # Run all phases sequentially
    python signals_v2.py --phase fix-blobs               # Single phase
    python signals_v2.py --phase aesthetic-v2 face-identity  # Multiple phases
    python signals_v2.py --phase florence-captions --limit 50  # Test run
    python signals_v2.py --phase depth-large --force     # Reprocess all
"""
from __future__ import annotations

import os
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"  # rembg u2net needs float64

import argparse
import gc
import json
import os
import struct
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

import database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = db.PROJECT_ROOT
BACKEND_DIR = Path(__file__).resolve().parent
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"

SOURCE_TIER = "display"
SOURCE_FORMAT = "jpeg"

DEVICE = os.environ.get("MAD_DEVICE", "mps")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _db_retry(conn, sql, params=(), retries=5, delay=1.0):
    for attempt in range(retries):
        try:
            conn.execute(sql, params)
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise


def _db_commit_retry(conn, retries=5, delay=1.0):
    for attempt in range(retries):
        try:
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise


def _free_gpu():
    gc.collect()
    try:
        import torch
        if hasattr(torch.mps, 'empty_cache'):
            torch.mps.empty_cache()
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Schema for v2 signal tables
# ---------------------------------------------------------------------------

V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS aesthetic_scores_v2 (
    image_uuid      TEXT PRIMARY KEY REFERENCES images(uuid),
    topiq_score     REAL,
    musiq_score     REAL,
    laion_score     REAL,
    composite_score REAL,
    score_label     TEXT,
    analyzed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS face_identities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid      TEXT NOT NULL REFERENCES images(uuid),
    face_index      INTEGER NOT NULL,
    embedding       BLOB,
    identity_id     INTEGER,
    identity_label  TEXT,
    analyzed_at     TEXT NOT NULL,
    UNIQUE(image_uuid, face_index)
);
CREATE INDEX IF NOT EXISTS idx_face_id_uuid ON face_identities(image_uuid);
CREATE INDEX IF NOT EXISTS idx_face_id_identity ON face_identities(identity_id);

CREATE TABLE IF NOT EXISTS florence_captions (
    image_uuid      TEXT PRIMARY KEY REFERENCES images(uuid),
    short_caption   TEXT,
    detailed_caption TEXT,
    more_detailed   TEXT,
    model           TEXT DEFAULT 'florence-2-base',
    analyzed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segmentation_masks (
    image_uuid          TEXT PRIMARY KEY REFERENCES images(uuid),
    segment_count       INTEGER,
    largest_segment_pct REAL,
    figure_ground_ratio REAL,
    subject_area_pct    REAL,
    edge_complexity     REAL,
    mean_segment_area   REAL,
    segments_json       TEXT,
    analyzed_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS open_detections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid      TEXT NOT NULL REFERENCES images(uuid),
    detection_index INTEGER NOT NULL,
    label           TEXT,
    confidence      REAL,
    x               REAL,
    y               REAL,
    w               REAL,
    h               REAL,
    area_pct        REAL,
    analyzed_at     TEXT NOT NULL,
    UNIQUE(image_uuid, detection_index)
);
CREATE INDEX IF NOT EXISTS idx_open_det_uuid ON open_detections(image_uuid);
CREATE INDEX IF NOT EXISTS idx_open_det_label ON open_detections(label);

CREATE TABLE IF NOT EXISTS image_tags (
    image_uuid      TEXT PRIMARY KEY REFERENCES images(uuid),
    tags            TEXT,
    tag_count       INTEGER,
    confidence_json TEXT,
    model           TEXT DEFAULT 'ram-plus',
    analyzed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS foreground_masks (
    image_uuid      TEXT PRIMARY KEY REFERENCES images(uuid),
    foreground_pct  REAL,
    background_pct  REAL,
    edge_sharpness  REAL,
    centroid_x      REAL,
    centroid_y      REAL,
    bbox_x          REAL,
    bbox_y          REAL,
    bbox_w          REAL,
    bbox_h          REAL,
    analyzed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pose_detections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid      TEXT NOT NULL REFERENCES images(uuid),
    person_index    INTEGER NOT NULL,
    keypoints_json  TEXT,
    pose_score      REAL,
    bbox_x          REAL,
    bbox_y          REAL,
    bbox_w          REAL,
    bbox_h          REAL,
    analyzed_at     TEXT NOT NULL,
    UNIQUE(image_uuid, person_index)
);
CREATE INDEX IF NOT EXISTS idx_pose_uuid ON pose_detections(image_uuid);

CREATE TABLE IF NOT EXISTS saliency_maps (
    image_uuid      TEXT PRIMARY KEY REFERENCES images(uuid),
    peak_x          REAL,
    peak_y          REAL,
    peak_value      REAL,
    spread          REAL,
    center_bias     REAL,
    thirds_json     TEXT,
    quadrant_json   TEXT,
    analyzed_at     TEXT NOT NULL
);
"""


def ensure_schema(conn):
    conn.executescript(V2_SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_work_items(conn, table_name, limit=0, force=False, uuid_col="image_uuid"):
    """Get images needing processing — joins to tiers for source path."""
    if force:
        skip_clause = ""
    else:
        skip_clause = f"""AND NOT EXISTS (
            SELECT 1 FROM {table_name} t2 WHERE t2.{uuid_col} = i.uuid
        )"""

    rows = conn.execute(f"""
        SELECT i.uuid, i.camera_body, i.is_monochrome, i.category, i.subcategory,
               t.local_path as source_path
        FROM images i
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = ? AND t.format = ? AND t.variant_id IS NULL
        WHERE t.local_path IS NOT NULL
            {skip_clause}
        ORDER BY i.uuid
    """, (SOURCE_TIER, SOURCE_FORMAT)).fetchall()

    work = [dict(r) for r in rows]
    if limit:
        work = work[:limit]
    return work


def _source_path(uuid):
    """Construct display tier path from UUID."""
    return str(RENDERED_DIR / SOURCE_TIER / SOURCE_FORMAT / f"{uuid}.jpg")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: fix-blobs
# ═══════════════════════════════════════════════════════════════════════════

def run_fix_blobs(conn, limit=0, force=False):
    """Fix blob-corrupted exposure_quality values in quality_scores."""
    print("\n[Phase 1] fix-blobs — Fix quality_scores.exposure_quality blobs")

    # Check if quality_scores table exists
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "quality_scores" not in tables:
        print("  quality_scores table does not exist. Skipping.")
        return 0

    # Find blob rows
    rows = conn.execute("""
        SELECT image_uuid, exposure_quality, technical_score, clip_score
        FROM quality_scores
        WHERE typeof(exposure_quality) = 'blob'
    """).fetchall()

    if not rows:
        print("  No blob-corrupted rows found.")
        return 0

    print(f"  Found {len(rows)} blob-corrupted rows. Fixing...")
    fixed = 0

    for row in rows:
        uuid = row["image_uuid"]
        blob = row["exposure_quality"]
        tech = row["technical_score"]
        clip_s = row["clip_score"]

        try:
            # Unpack numpy float32 bytes
            value = struct.unpack('<f', bytes(blob))[0]
            if not (0.0 <= value <= 100.0):
                value = None  # Out of range, set NULL

            # Recompute combined_score with the fixed value
            combined = None
            if tech is not None and clip_s is not None:
                combined = round(0.6 * tech + 0.4 * clip_s, 2)

            conn.execute("""
                UPDATE quality_scores
                SET exposure_quality = ?, combined_score = ?
                WHERE image_uuid = ?
            """, (value, combined, uuid))
            fixed += 1
        except (struct.error, TypeError) as e:
            # Can't unpack — set to NULL
            conn.execute("""
                UPDATE quality_scores SET exposure_quality = NULL WHERE image_uuid = ?
            """, (uuid,))
            fixed += 1

    _db_commit_retry(conn)
    print(f"  Fixed {fixed} rows.")

    # Verify
    remaining = conn.execute(
        "SELECT COUNT(*) FROM quality_scores WHERE typeof(exposure_quality) = 'blob'"
    ).fetchone()[0]
    print(f"  Remaining blobs: {remaining}")
    return fixed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: gps-locations
# ═══════════════════════════════════════════════════════════════════════════

def run_gps_locations(conn, limit=0, force=False):
    """Populate image_locations from exif_metadata GPS data."""
    print("\n[Phase 2] gps-locations — Populate from EXIF GPS")

    if force:
        conn.execute("DELETE FROM image_locations WHERE source = 'gps_exif'")
        _db_commit_retry(conn)

    skip_clause = "" if force else """
        AND NOT EXISTS (
            SELECT 1 FROM image_locations il WHERE il.image_uuid = e.image_uuid
        )
    """

    rows = conn.execute(f"""
        SELECT e.image_uuid, e.gps_lat, e.gps_lon
        FROM exif_metadata e
        WHERE e.gps_lat IS NOT NULL AND e.gps_lon IS NOT NULL
            {skip_clause}
        ORDER BY e.image_uuid
    """).fetchall()

    if not rows:
        print("  No new GPS data to populate.")
        return 0

    work = [dict(r) for r in rows]
    if limit:
        work = work[:limit]

    print(f"  Inserting {len(work)} GPS locations...")
    now_str = _now()
    inserted = 0

    for row in work:
        try:
            lat = float(row["gps_lat"])
            lon = float(row["gps_lon"])
            # Basic validation
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            conn.execute("""
                INSERT INTO image_locations
                    (image_uuid, latitude, longitude, source, confidence, accepted, created_at)
                VALUES (?, ?, ?, 'gps_exif', 1.0, 0, ?)
                ON CONFLICT(image_uuid) DO UPDATE SET
                    latitude=excluded.latitude, longitude=excluded.longitude,
                    source=excluded.source, confidence=excluded.confidence,
                    created_at=excluded.created_at
            """, (row["image_uuid"], lat, lon, now_str))
            inserted += 1
        except (ValueError, TypeError):
            continue

    _db_commit_retry(conn)
    print(f"  Inserted {inserted} locations.")
    return inserted


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: aesthetic-v2
# ═══════════════════════════════════════════════════════════════════════════

def run_aesthetic_v2(conn, limit=0, force=False):
    """Triple-metric aesthetic scoring: TOPIQ + MUSIQ + LAION CLIP aesthetic."""
    import torch

    print("\n[Phase 3] aesthetic-v2 — TOPIQ + MUSIQ + LAION CLIP")
    work = get_work_items(conn, "aesthetic_scores_v2", limit, force)
    if not work:
        print("  Nothing to process.")
        return 0

    print(f"  {len(work)} images to score...")
    start = time.time()
    completed = 0
    now_str = _now()

    # --- Sub-phase A: TOPIQ ---
    # TOPIQ uses adaptive pooling which requires divisible sizes on MPS.
    # Resize to fixed 384x384 square to avoid MPS compatibility issues.
    print("  Loading TOPIQ (no-reference)...")
    topiq_scores = {}
    try:
        import pyiqa
        import torchvision.transforms.functional as TF
        topiq = pyiqa.create_metric('topiq_nr', device=DEVICE)

        for item in work:
            try:
                img = Image.open(item["source_path"]).convert("RGB")
                # Resize to fixed 384x384 — avoids MPS adaptive pool issues
                img = img.resize((384, 384), Image.LANCZOS)

                tensor = TF.to_tensor(img).unsqueeze(0).to(DEVICE)
                with torch.no_grad():
                    score = topiq(tensor).item()
                topiq_scores[item["uuid"]] = float(score)
            except Exception as e:
                print(f"    TOPIQ error {item['uuid'][:8]}: {e}", file=sys.stderr)

            if len(topiq_scores) % 200 == 0 and len(topiq_scores) > 0:
                elapsed = time.time() - start
                print(f"    TOPIQ: {len(topiq_scores)}/{len(work)} ({len(topiq_scores)/elapsed:.1f}/s)")

        del topiq
        _free_gpu()
        print(f"  TOPIQ done: {len(topiq_scores)} scores")
    except ImportError:
        print("  pyiqa not installed — skipping TOPIQ (pip install pyiqa)")
    except Exception as e:
        print(f"  TOPIQ failed: {e}")

    # --- Sub-phase B: MUSIQ ---
    # MUSIQ also uses adaptive pooling — fixed 384x384.
    print("  Loading MUSIQ-AVA...")
    musiq_scores = {}
    try:
        import pyiqa
        import torchvision.transforms.functional as TF
        musiq = pyiqa.create_metric('musiq-ava', device=DEVICE)

        for item in work:
            try:
                img = Image.open(item["source_path"]).convert("RGB")
                img = img.resize((384, 384), Image.LANCZOS)

                tensor = TF.to_tensor(img).unsqueeze(0).to(DEVICE)
                with torch.no_grad():
                    score = musiq(tensor).item()
                musiq_scores[item["uuid"]] = float(score)
            except Exception as e:
                print(f"    MUSIQ error {item['uuid'][:8]}: {e}", file=sys.stderr)

            if len(musiq_scores) % 200 == 0 and len(musiq_scores) > 0:
                elapsed = time.time() - start
                print(f"    MUSIQ: {len(musiq_scores)}/{len(work)} ({len(musiq_scores)/elapsed:.1f}/s)")

        del musiq
        _free_gpu()
        print(f"  MUSIQ done: {len(musiq_scores)} scores")
    except ImportError:
        print("  pyiqa not installed — skipping MUSIQ")
    except Exception as e:
        print(f"  MUSIQ failed: {e}")

    # --- Sub-phase C: LAION CLIP aesthetic ---
    print("  Loading CLIP ViT-L/14 + LAION aesthetic MLP...")
    laion_scores = {}
    try:
        from transformers import CLIPModel, CLIPProcessor
        import urllib.request

        model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
        model = model.to(DEVICE).eval()

        # Download LAION aesthetic predictor MLP
        mlp_path = BACKEND_DIR / "models" / ".laion_aesthetic_v2.pth"
        mlp_path.parent.mkdir(parents=True, exist_ok=True)
        if not mlp_path.exists():
            print("  Downloading LAION aesthetic MLP weights...")
            urllib.request.urlretrieve(
                "https://github.com/christophschuhmann/improved-aesthetic-predictor/raw/main/sac%2Blogos%2Bava1-l14-linearMSE.pth",
                str(mlp_path)
            )

        # Build MLP head
        import torch.nn as nn
        class AestheticMLP(nn.Module):
            def __init__(self):
                super().__init__()
                self.layers = nn.Sequential(
                    nn.Linear(768, 1024),
                    nn.Dropout(0.2),
                    nn.Linear(1024, 128),
                    nn.Dropout(0.2),
                    nn.Linear(128, 64),
                    nn.Dropout(0.1),
                    nn.Linear(64, 16),
                    nn.Linear(16, 1),
                )
            def forward(self, x):
                return self.layers(x)

        mlp = AestheticMLP()
        state = torch.load(str(mlp_path), map_location="cpu", weights_only=True)
        mlp.load_state_dict(state)
        mlp = mlp.to(DEVICE).eval()

        batch_size = 8
        for i in range(0, len(work), batch_size):
            batch = work[i:i + batch_size]
            images = []
            valid = []
            for item in batch:
                try:
                    img = Image.open(item["source_path"]).convert("RGB")
                    images.append(img)
                    valid.append(item)
                except Exception:
                    continue

            if not images:
                continue

            with torch.no_grad():
                inputs = processor(images=images, return_tensors="pt", padding=True)
                inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
                features = model.get_image_features(**inputs)
                features = features / features.norm(dim=-1, keepdim=True)
                scores = mlp(features).squeeze(-1)

                for j, item in enumerate(valid):
                    laion_scores[item["uuid"]] = float(scores[j].cpu())

            if len(laion_scores) % 200 == 0 and len(laion_scores) > 0:
                elapsed = time.time() - start
                print(f"    LAION: {len(laion_scores)}/{len(work)} ({len(laion_scores)/elapsed:.1f}/s)")

        del model, processor, mlp
        _free_gpu()
        print(f"  LAION done: {len(laion_scores)} scores")
    except Exception as e:
        print(f"  LAION aesthetic failed: {e}")
        import traceback
        traceback.print_exc()

    # --- Combine and write ---
    print("  Writing composite scores...")
    for item in work:
        uuid = item["uuid"]
        t_score = topiq_scores.get(uuid)
        m_score = musiq_scores.get(uuid)
        l_score = laion_scores.get(uuid)

        # Compute composite: 0.35*(topiq*100) + 0.35*musiq + 0.30*(laion*10)
        parts = []
        weights = []
        if t_score is not None:
            parts.append(t_score * 100)
            weights.append(0.35)
        if m_score is not None:
            parts.append(m_score)
            weights.append(0.35)
        if l_score is not None:
            parts.append(l_score * 10)
            weights.append(0.30)

        if parts:
            # Normalize weights
            total_w = sum(weights)
            composite = sum(p * w for p, w in zip(parts, weights)) / total_w
        else:
            composite = None

        # Label
        label = None
        if composite is not None:
            if composite < 30:
                label = "poor"
            elif composite < 45:
                label = "below_avg"
            elif composite < 60:
                label = "average"
            elif composite < 75:
                label = "good"
            else:
                label = "excellent"

        conn.execute("""
            INSERT INTO aesthetic_scores_v2
                (image_uuid, topiq_score, musiq_score, laion_score, composite_score,
                 score_label, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(image_uuid) DO UPDATE SET
                topiq_score=excluded.topiq_score, musiq_score=excluded.musiq_score,
                laion_score=excluded.laion_score, composite_score=excluded.composite_score,
                score_label=excluded.score_label, analyzed_at=excluded.analyzed_at
        """, (uuid,
              round(t_score, 4) if t_score is not None else None,
              round(m_score, 2) if m_score is not None else None,
              round(l_score, 4) if l_score is not None else None,
              round(composite, 2) if composite is not None else None,
              label, now_str))
        completed += 1

        if completed % 500 == 0:
            _db_commit_retry(conn)

    _db_commit_retry(conn)
    elapsed = time.time() - start
    print(f"  Done: {completed} scored in {elapsed:.1f}s")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: depth-large
# ═══════════════════════════════════════════════════════════════════════════

def run_depth_large(conn, limit=0, force=False):
    """Upgrade Depth Anything v2 Small → Large."""
    import torch
    from transformers import pipeline as hf_pipeline

    print("\n[Phase 4] depth-large — Depth Anything v2 Large (ViT-L)")
    work = get_work_items(conn, "depth_estimation", limit, force)
    if not work:
        print("  Nothing to process.")
        return 0

    print(f"  Loading Depth Anything v2 Large on {DEVICE}...")
    depth_pipe = hf_pipeline(
        "depth-estimation",
        model="depth-anything/Depth-Anything-V2-Large-hf",
        device=DEVICE,
    )

    print(f"  Processing {len(work)} images...")
    start = time.time()
    completed = 0
    now_str = _now()

    for item in work:
        try:
            img = Image.open(item["source_path"]).convert("RGB")
            w, h = img.size
            scale = min(1.0, 518.0 / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            result = depth_pipe(img)
            depth_map = np.array(result["depth"], dtype=np.float32)

            d_min = float(depth_map.min())
            d_max = float(depth_map.max())
            if d_max > d_min:
                normalized = (depth_map - d_min) / (d_max - d_min)
            else:
                normalized = np.zeros_like(depth_map)

            d_mean = float(np.mean(normalized))
            d_std = float(np.std(normalized))
            total_px = normalized.size
            near_pct = float(np.sum(normalized < 0.33) / total_px * 100)
            mid_pct = float(np.sum((normalized >= 0.33) & (normalized < 0.66)) / total_px * 100)
            far_pct = float(np.sum(normalized >= 0.66) / total_px * 100)

            hist, _ = np.histogram(normalized, bins=20, range=(0, 1))
            hist = hist / hist.sum()
            hist = hist[hist > 0]
            complexity = float(-np.sum(hist * np.log2(hist)))

            conn.execute("""
                INSERT INTO depth_estimation
                    (image_uuid, depth_min, depth_max, depth_mean, depth_std,
                     near_pct, mid_pct, far_pct, depth_complexity, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_uuid) DO UPDATE SET
                    depth_min=excluded.depth_min, depth_max=excluded.depth_max,
                    depth_mean=excluded.depth_mean, depth_std=excluded.depth_std,
                    near_pct=excluded.near_pct, mid_pct=excluded.mid_pct,
                    far_pct=excluded.far_pct, depth_complexity=excluded.depth_complexity,
                    analyzed_at=excluded.analyzed_at
            """, (item["uuid"], d_min, d_max, round(d_mean, 4), round(d_std, 4),
                  round(near_pct, 1), round(mid_pct, 1), round(far_pct, 1),
                  round(complexity, 3), now_str))
            completed += 1

        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 100 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            rate = completed / elapsed
            remaining = (len(work) - completed) / rate if rate > 0 else 0
            print(f"    {completed}/{len(work)} ({rate:.1f}/s, ~{remaining:.0f}s)")

    _db_commit_retry(conn)
    del depth_pipe
    _free_gpu()

    elapsed = time.time() - start
    print(f"  Done: {completed} in {elapsed:.1f}s ({completed/max(1,elapsed):.1f}/s)")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5: face-identity
# ═══════════════════════════════════════════════════════════════════════════

def run_face_identity(conn, limit=0, force=False):
    """Face identity clustering via InsightFace ArcFace."""
    print("\n[Phase 5] face-identity — InsightFace ArcFace + DBSCAN")

    if force:
        conn.execute("DELETE FROM face_identities")
        _db_commit_retry(conn)

    # Only process images with face detections that don't already have identities
    skip_clause = "" if force else """
        AND NOT EXISTS (
            SELECT 1 FROM face_identities fi WHERE fi.image_uuid = fd.image_uuid
        )
    """

    rows = conn.execute(f"""
        SELECT DISTINCT fd.image_uuid as uuid, t.local_path as source_path
        FROM face_detections fd
        JOIN tiers t ON fd.image_uuid = t.image_uuid
            AND t.tier_name = ? AND t.format = ? AND t.variant_id IS NULL
        WHERE t.local_path IS NOT NULL {skip_clause}
        ORDER BY fd.image_uuid
    """, (SOURCE_TIER, SOURCE_FORMAT)).fetchall()

    work = [dict(r) for r in rows]
    if limit:
        work = work[:limit]

    if not work:
        print("  Nothing to process.")
        return 0

    print(f"  {len(work)} images with faces to process...")

    try:
        from insightface.app import FaceAnalysis
    except ImportError:
        print("  insightface not installed — skipping (pip install insightface onnxruntime)")
        return 0

    # Initialize InsightFace
    print("  Loading InsightFace buffalo_l...")
    app = FaceAnalysis(name='buffalo_l', providers=['CoreMLExecutionProvider', 'CPUExecutionProvider'])
    app.prepare(ctx_id=0, det_size=(640, 640))

    start = time.time()
    completed = 0
    all_embeddings = []  # (uuid, face_index, embedding)
    now_str = _now()

    for item in work:
        try:
            import cv2
            img = cv2.imread(item["source_path"])
            if img is None:
                continue

            faces = app.get(img)
            face_dets = conn.execute("""
                SELECT face_index, x, y, w, h FROM face_detections
                WHERE image_uuid = ? ORDER BY face_index
            """, (item["uuid"],)).fetchall()

            for fi, face in enumerate(faces):
                if face.embedding is not None:
                    emb = face.embedding.astype(np.float32)
                    emb_blob = emb.tobytes()

                    conn.execute("""
                        INSERT INTO face_identities
                            (image_uuid, face_index, embedding, analyzed_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(image_uuid, face_index) DO UPDATE SET
                            embedding=excluded.embedding, analyzed_at=excluded.analyzed_at
                    """, (item["uuid"], fi, emb_blob, now_str))

                    all_embeddings.append((item["uuid"], fi, emb))

            completed += 1
        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 100 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            print(f"    {completed}/{len(work)} ({completed/elapsed:.1f}/s)")

    _db_commit_retry(conn)
    del app
    _free_gpu()

    # --- Clustering ---
    if all_embeddings:
        print(f"  Clustering {len(all_embeddings)} face embeddings with DBSCAN...")
        from sklearn.cluster import DBSCAN

        emb_matrix = np.array([e[2] for e in all_embeddings])
        # Normalize for cosine distance
        norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
        emb_matrix = emb_matrix / (norms + 1e-8)

        clustering = DBSCAN(eps=0.6, min_samples=3, metric='cosine').fit(emb_matrix)
        labels = clustering.labels_

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        print(f"  Found {n_clusters} identity clusters ({sum(labels == -1)} unclustered)")

        for (uuid, fi, _), label in zip(all_embeddings, labels):
            identity_id = int(label) if label >= 0 else None
            identity_label = f"person_{label}" if label >= 0 else None
            conn.execute("""
                UPDATE face_identities
                SET identity_id = ?, identity_label = ?
                WHERE image_uuid = ? AND face_index = ?
            """, (identity_id, identity_label, uuid, fi))

        _db_commit_retry(conn)

    elapsed = time.time() - start
    print(f"  Done: {completed} images, {len(all_embeddings)} faces in {elapsed:.1f}s")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6: florence-captions
# ═══════════════════════════════════════════════════════════════════════════

def run_florence_captions(conn, limit=0, force=False):
    """Detailed captions via Florence-2-large."""
    import torch

    print("\n[Phase 6] florence-captions — Florence-2-base")
    work = get_work_items(conn, "florence_captions", limit, force)
    if not work:
        print("  Nothing to process.")
        return 0

    # Florence-2 needs use_cache=False + num_beams=1 for transformers 4.57+ compat
    fl_device = DEVICE
    print(f"  Loading Florence-2-large on {fl_device}...")
    from transformers import AutoProcessor, AutoModelForCausalLM

    processor = AutoProcessor.from_pretrained(
        "microsoft/Florence-2-base", trust_remote_code=True
    )
    model = AutoModelForCausalLM.from_pretrained(
        "microsoft/Florence-2-base", trust_remote_code=True,
        torch_dtype=torch.float32, attn_implementation="eager"
    ).to(fl_device).eval()

    def florence_task(img, task_prompt):
        inputs = processor(text=task_prompt, images=img, return_tensors="pt")
        inputs = {k: v.to(fl_device) for k, v in inputs.items()}
        with torch.no_grad():
            generated = model.generate(
                **inputs, max_new_tokens=256, num_beams=1, use_cache=False
            )
        result = processor.batch_decode(generated, skip_special_tokens=False)[0]
        parsed = processor.post_process_generation(
            result, task=task_prompt, image_size=(img.width, img.height)
        )
        return parsed.get(task_prompt, "")

    print(f"  Processing {len(work)} images (3 captions each)...")
    start = time.time()
    completed = 0
    now_str = _now()

    for item in work:
        try:
            img = Image.open(item["source_path"]).convert("RGB")
            w, h = img.size
            scale = min(1.0, 384.0 / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            short = florence_task(img, "<CAPTION>")
            detailed = florence_task(img, "<DETAILED_CAPTION>")
            more_detailed = florence_task(img, "<MORE_DETAILED_CAPTION>")

            conn.execute("""
                INSERT INTO florence_captions
                    (image_uuid, short_caption, detailed_caption, more_detailed,
                     model, analyzed_at)
                VALUES (?, ?, ?, ?, 'florence-2-base', ?)
                ON CONFLICT(image_uuid) DO UPDATE SET
                    short_caption=excluded.short_caption,
                    detailed_caption=excluded.detailed_caption,
                    more_detailed=excluded.more_detailed,
                    analyzed_at=excluded.analyzed_at
            """, (item["uuid"], short, detailed, more_detailed, now_str))
            completed += 1

        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 50 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            rate = completed / elapsed
            remaining = (len(work) - completed) / rate if rate > 0 else 0
            print(f"    {completed}/{len(work)} ({rate:.1f}/s, ~{remaining:.0f}s)")

    _db_commit_retry(conn)
    del model, processor
    _free_gpu()

    elapsed = time.time() - start
    print(f"  Done: {completed} captioned in {elapsed:.1f}s ({completed/max(1,elapsed):.1f}/s)")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 7: sam-segments
# ═══════════════════════════════════════════════════════════════════════════

def run_sam_segments(conn, limit=0, force=False):
    """Segmentation mask summary stats via SAM 2.1."""
    import torch

    print("\n[Phase 7] sam-segments — SAM 2.1 Hiera Tiny")
    work = get_work_items(conn, "segmentation_masks", limit, force)
    if not work:
        print("  Nothing to process.")
        return 0

    # SAM inputs have float64 — cast to float32 for MPS, post-process on CPU
    sam_device = DEVICE
    print(f"  Loading SAM on {sam_device}...")
    from transformers import SamModel, SamProcessor

    processor = SamProcessor.from_pretrained("facebook/sam-vit-base")
    model = SamModel.from_pretrained("facebook/sam-vit-base").to(sam_device).eval()

    print(f"  Processing {len(work)} images...")
    start = time.time()
    completed = 0
    now_str = _now()

    for item in work:
        try:
            img = Image.open(item["source_path"]).convert("RGB")
            w, h = img.size
            scale = min(1.0, 512.0 / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            # Use grid points for automatic segmentation
            rw, rh = img.size
            points_per_side = 16
            xs = np.linspace(0, rw - 1, points_per_side)
            ys = np.linspace(0, rh - 1, points_per_side)
            grid_points = [[int(x), int(y)] for y in ys for x in xs]

            # Process in chunks to avoid OOM
            all_masks = []
            chunk_size = 64
            for ci in range(0, len(grid_points), chunk_size):
                chunk = grid_points[ci:ci + chunk_size]
                inputs = processor(
                    img, input_points=[chunk], return_tensors="pt"
                )
                # Cast float64→float32 for MPS compat, keep sizes on CPU
                orig_sizes = inputs.pop("original_sizes")
                reshaped_sizes = inputs.pop("reshaped_input_sizes")
                mps_inputs = {}
                for k, v in inputs.items():
                    if v.dtype == torch.float64:
                        v = v.float()
                    mps_inputs[k] = v.to(sam_device)
                mps_inputs["original_sizes"] = orig_sizes.to(sam_device)
                mps_inputs["reshaped_input_sizes"] = reshaped_sizes.to(sam_device)

                with torch.no_grad():
                    outputs = model(**mps_inputs)

                masks = processor.image_processor.post_process_masks(
                    outputs.pred_masks.cpu(),
                    orig_sizes,
                    reshaped_sizes
                )
                if masks and len(masks) > 0:
                    for mask_set in masks:
                        for m in range(mask_set.shape[0]):
                            mask_np = mask_set[m, 0].numpy().astype(bool)
                            area = float(mask_np.sum()) / mask_np.size
                            if area > 0.001 and area < 0.99:  # Filter trivial masks
                                all_masks.append({
                                    "area_pct": round(area * 100, 2),
                                    "mask": mask_np,
                                })

            # Deduplicate overlapping masks (keep unique by area)
            all_masks.sort(key=lambda x: -x["area_pct"])
            unique_masks = []
            for m in all_masks:
                is_dup = False
                for existing in unique_masks:
                    if abs(m["area_pct"] - existing["area_pct"]) < 1.0:
                        is_dup = True
                        break
                if not is_dup:
                    unique_masks.append(m)
                if len(unique_masks) >= 30:
                    break

            segment_count = len(unique_masks)
            total_area = rw * rh

            if segment_count > 0:
                areas = [m["area_pct"] for m in unique_masks]
                largest = max(areas)
                mean_area = sum(areas) / len(areas)

                # Subject area: largest non-background segment
                subject_area = areas[0] if areas[0] < 80 else (areas[1] if len(areas) > 1 else areas[0])
                bg_area = 100.0 - subject_area
                fg_ratio = subject_area / max(bg_area, 0.1)

                # Edge complexity: perimeter of largest mask / sqrt(area)
                largest_mask = unique_masks[0]["mask"]
                from scipy import ndimage
                perimeter = ndimage.binary_dilation(largest_mask).astype(int) - largest_mask.astype(int)
                edge_len = float(perimeter.sum())
                edge_complexity = edge_len / (np.sqrt(largest_mask.sum()) + 1)

                segments_json = json.dumps([
                    {"area_pct": m["area_pct"]} for m in unique_masks[:10]
                ])
            else:
                largest = 0
                mean_area = 0
                subject_area = 0
                fg_ratio = 0
                edge_complexity = 0
                segments_json = "[]"

            conn.execute("""
                INSERT INTO segmentation_masks
                    (image_uuid, segment_count, largest_segment_pct,
                     figure_ground_ratio, subject_area_pct, edge_complexity,
                     mean_segment_area, segments_json, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_uuid) DO UPDATE SET
                    segment_count=excluded.segment_count,
                    largest_segment_pct=excluded.largest_segment_pct,
                    figure_ground_ratio=excluded.figure_ground_ratio,
                    subject_area_pct=excluded.subject_area_pct,
                    edge_complexity=excluded.edge_complexity,
                    mean_segment_area=excluded.mean_segment_area,
                    segments_json=excluded.segments_json,
                    analyzed_at=excluded.analyzed_at
            """, (item["uuid"], segment_count, round(largest, 2),
                  round(fg_ratio, 3), round(subject_area, 2),
                  round(edge_complexity, 2), round(mean_area, 2),
                  segments_json, now_str))
            completed += 1

        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 50 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            rate = completed / elapsed
            remaining = (len(work) - completed) / rate if rate > 0 else 0
            print(f"    {completed}/{len(work)} ({rate:.1f}/s, ~{remaining:.0f}s)")

    _db_commit_retry(conn)
    del model, processor
    _free_gpu()

    elapsed = time.time() - start
    print(f"  Done: {completed} in {elapsed:.1f}s ({completed/max(1,elapsed):.1f}/s)")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 8: grounding-dino
# ═══════════════════════════════════════════════════════════════════════════

def run_grounding_dino(conn, limit=0, force=False):
    """Open-vocabulary detection via Grounding DINO."""
    import torch

    print("\n[Phase 8] grounding-dino — IDEA-Research/grounding-dino-tiny")

    if force:
        conn.execute("DELETE FROM open_detections")
        _db_commit_retry(conn)

    # Get images not yet processed
    skip_clause = "" if force else """
        AND NOT EXISTS (
            SELECT 1 FROM open_detections od WHERE od.image_uuid = i.uuid
        )
    """

    rows = conn.execute(f"""
        SELECT i.uuid, t.local_path as source_path
        FROM images i
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = ? AND t.format = ? AND t.variant_id IS NULL
        WHERE t.local_path IS NOT NULL {skip_clause}
        ORDER BY i.uuid
    """, (SOURCE_TIER, SOURCE_FORMAT)).fetchall()

    work = [dict(r) for r in rows]
    if limit:
        work = work[:limit]

    if not work:
        print("  Nothing to process.")
        return 0

    print(f"  Loading Grounding DINO tiny on {DEVICE}...")
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

    processor = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-tiny")
    model = AutoModelForZeroShotObjectDetection.from_pretrained(
        "IDEA-Research/grounding-dino-tiny"
    ).to(DEVICE).eval()

    PROMPT = "person . car . bicycle . sign . graffiti . shadow . reflection . silhouette . umbrella . building . staircase . fire escape . mural . neon . tree . bridge . fence . window . door . lamp"
    CONF_THRESHOLD = 0.25

    print(f"  Processing {len(work)} images...")
    start = time.time()
    completed = 0
    now_str = _now()

    for item in work:
        try:
            img = Image.open(item["source_path"]).convert("RGB")
            w, h = img.size

            inputs = processor(images=img, text=PROMPT, return_tensors="pt")
            inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = model(**inputs)

            results = processor.post_process_grounded_object_detection(
                outputs,
                inputs["input_ids"],
                threshold=CONF_THRESHOLD,
                target_sizes=[(h, w)]
            )[0]

            boxes = results["boxes"].cpu().numpy()
            scores = results["scores"].cpu().numpy()
            labels = results.get("text_labels", results.get("labels", []))

            # Sort by confidence, keep top 30
            indices = np.argsort(-scores)[:30]

            det_idx = 0
            for idx in indices:
                box = boxes[idx]
                x1, y1, x2, y2 = box
                bx = float(x1 / w)
                by = float(y1 / h)
                bw = float((x2 - x1) / w)
                bh = float((y2 - y1) / h)
                area_pct = bw * bh * 100

                conn.execute("""
                    INSERT INTO open_detections
                        (image_uuid, detection_index, label, confidence,
                         x, y, w, h, area_pct, analyzed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(image_uuid, detection_index) DO UPDATE SET
                        label=excluded.label, confidence=excluded.confidence,
                        x=excluded.x, y=excluded.y, w=excluded.w, h=excluded.h,
                        area_pct=excluded.area_pct, analyzed_at=excluded.analyzed_at
                """, (item["uuid"], det_idx, labels[idx],
                      round(float(scores[idx]), 3),
                      round(bx, 4), round(by, 4),
                      round(bw, 4), round(bh, 4),
                      round(area_pct, 2), now_str))
                det_idx += 1

            completed += 1

        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 100 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            rate = completed / elapsed
            remaining = (len(work) - completed) / rate if rate > 0 else 0
            print(f"    {completed}/{len(work)} ({rate:.1f}/s, ~{remaining:.0f}s)")

    _db_commit_retry(conn)
    del model, processor
    _free_gpu()

    elapsed = time.time() - start
    print(f"  Done: {completed} in {elapsed:.1f}s ({completed/max(1,elapsed):.1f}/s)")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9: ram-tags
# ═══════════════════════════════════════════════════════════════════════════

def run_ram_tags(conn, limit=0, force=False):
    """Multi-label image tagging via RAM++ or CLIP zero-shot fallback."""
    import torch

    print("\n[Phase 9] ram-tags — Multi-label tagging")
    work = get_work_items(conn, "image_tags", limit, force)
    if not work:
        print("  Nothing to process.")
        return 0

    # Try RAM++ first, fall back to CLIP zero-shot
    use_ram = False
    try:
        from ram.models import ram_plus
        from ram import inference_ram as inference
        use_ram = True
    except ImportError:
        print("  RAM++ not available — using CLIP zero-shot tagging fallback")

    if use_ram:
        return _run_ram_plus(conn, work, torch)
    else:
        return _run_clip_tags(conn, work, torch)


def _run_ram_plus(conn, work, torch):
    """RAM++ multi-label tagging."""
    from ram.models import ram_plus
    from ram import inference_ram as inference
    import torchvision.transforms as T

    print(f"  Loading RAM++ on {DEVICE}...")
    model = ram_plus(pretrained='xinyu1205/recognize-anything-plus-model',
                     image_size=384, vit='swin_l')
    model = model.to(DEVICE).eval()

    transform = T.Compose([
        T.Resize((384, 384)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    start = time.time()
    completed = 0
    now_str = _now()

    for item in work:
        try:
            img = Image.open(item["source_path"]).convert("RGB")
            tensor = transform(img).unsqueeze(0).to(DEVICE)

            with torch.no_grad():
                tags = inference.inference(tensor, model)

            tag_list = [t.strip() for t in tags.split("|") if t.strip()]
            conn.execute("""
                INSERT INTO image_tags
                    (image_uuid, tags, tag_count, model, analyzed_at)
                VALUES (?, ?, ?, 'ram-plus', ?)
                ON CONFLICT(image_uuid) DO UPDATE SET
                    tags=excluded.tags, tag_count=excluded.tag_count,
                    analyzed_at=excluded.analyzed_at
            """, (item["uuid"], " | ".join(tag_list), len(tag_list), now_str))
            completed += 1

        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 200 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            print(f"    {completed}/{len(work)} ({completed/elapsed:.1f}/s)")

    _db_commit_retry(conn)
    del model
    _free_gpu()

    elapsed = time.time() - start
    print(f"  Done: {completed} tagged in {elapsed:.1f}s")
    return completed


def _run_clip_tags(conn, work, torch):
    """CLIP zero-shot tagging fallback when RAM++ is unavailable."""
    from transformers import CLIPModel, CLIPProcessor

    TAGS = [
        "person", "people", "crowd", "face", "portrait", "selfie",
        "car", "vehicle", "bicycle", "motorcycle", "bus", "truck",
        "building", "architecture", "skyscraper", "house", "bridge",
        "street", "road", "sidewalk", "crosswalk", "alley",
        "tree", "flower", "plant", "garden", "forest", "park",
        "water", "ocean", "river", "lake", "rain", "puddle", "reflection",
        "sky", "cloud", "sunset", "sunrise", "night", "dawn",
        "mountain", "hill", "cliff", "beach", "desert",
        "food", "restaurant", "cafe", "shop", "market",
        "sign", "text", "graffiti", "mural", "neon",
        "animal", "dog", "cat", "bird",
        "shadow", "silhouette", "light", "window", "door",
        "staircase", "fence", "wall", "lamp", "umbrella",
        "snow", "fog", "smoke",
    ]

    print(f"  Loading CLIP ViT-B/32 for zero-shot tagging on {DEVICE}...")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(DEVICE).eval()
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    # Pre-encode text prompts
    text_inputs = processor(text=[f"a photo of {t}" for t in TAGS],
                            return_tensors="pt", padding=True)
    text_inputs = {k: v.to(DEVICE) for k, v in text_inputs.items()}
    with torch.no_grad():
        text_features = model.get_text_features(**text_inputs)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    start = time.time()
    completed = 0
    now_str = _now()
    batch_size = 16

    for i in range(0, len(work), batch_size):
        batch = work[i:i + batch_size]
        images = []
        valid = []
        for item in batch:
            try:
                img = Image.open(item["source_path"]).convert("RGB")
                images.append(img)
                valid.append(item)
            except Exception:
                continue

        if not images:
            continue

        with torch.no_grad():
            inputs = processor(images=images, return_tensors="pt", padding=True)
            inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
            image_features = model.get_image_features(**inputs)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # Cosine similarity
            similarities = (image_features @ text_features.T).cpu().numpy()

            for j, item in enumerate(valid):
                scores = similarities[j]
                # Tags with similarity > 0.25
                matches = [(TAGS[k], float(scores[k])) for k in range(len(TAGS))
                           if scores[k] > 0.25]
                matches.sort(key=lambda x: -x[1])
                matches = matches[:20]

                tag_list = [m[0] for m in matches]
                conf_json = json.dumps({m[0]: round(m[1], 3) for m in matches})

                conn.execute("""
                    INSERT INTO image_tags
                        (image_uuid, tags, tag_count, confidence_json, model, analyzed_at)
                    VALUES (?, ?, ?, ?, 'clip-zero-shot', ?)
                    ON CONFLICT(image_uuid) DO UPDATE SET
                        tags=excluded.tags, tag_count=excluded.tag_count,
                        confidence_json=excluded.confidence_json, model=excluded.model,
                        analyzed_at=excluded.analyzed_at
                """, (item["uuid"], " | ".join(tag_list), len(tag_list),
                      conf_json, now_str))
                completed += 1

        if completed % 200 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            print(f"    {completed}/{len(work)} ({completed/elapsed:.1f}/s)")

    _db_commit_retry(conn)
    del model, processor
    _free_gpu()

    elapsed = time.time() - start
    print(f"  Done: {completed} tagged in {elapsed:.1f}s")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 10: rembg-foreground
# ═══════════════════════════════════════════════════════════════════════════

def run_rembg_foreground(conn, limit=0, force=False):
    """Foreground isolation metrics via rembg (u2net)."""
    print("\n[Phase 10] rembg-foreground — u2net foreground mask")

    try:
        from rembg import remove, new_session
    except ImportError:
        print("  rembg not installed — skipping (pip install rembg)")
        return 0

    work = get_work_items(conn, "foreground_masks", limit, force)
    if not work:
        print("  Nothing to process.")
        return 0

    # Force CPU — u2net needs float64 which MPS doesn't support
    import torch
    _orig_mps_avail = torch.backends.mps.is_available
    _orig_mps_built = torch.backends.mps.is_built
    torch.backends.mps.is_available = lambda: False
    torch.backends.mps.is_built = lambda: False
    session = new_session("u2net", providers=["CPUExecutionProvider"])

    print(f"  Processing {len(work)} images...")
    start = time.time()
    completed = 0
    now_str = _now()

    for item in work:
        try:
            img = Image.open(item["source_path"]).convert("RGB")
            w, h = img.size
            scale = min(1.0, 512.0 / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            # Get binary mask
            mask = remove(img, only_mask=True, session=session)
            mask_np = np.array(mask).astype(np.float32) / 255.0
            binary = (mask_np > 0.5).astype(np.float32)

            total_px = binary.size
            fg_px = float(binary.sum())
            fg_pct = fg_px / total_px * 100
            bg_pct = 100.0 - fg_pct

            # Edge sharpness: gradient magnitude at mask boundary
            from scipy import ndimage
            gradient = ndimage.sobel(mask_np)
            edge_sharpness = float(gradient[binary > 0.3].mean()) if fg_px > 0 else 0

            # Centroid (normalized 0-1)
            if fg_px > 0:
                ys, xs = np.where(binary > 0.5)
                centroid_x = float(xs.mean()) / mask_np.shape[1]
                centroid_y = float(ys.mean()) / mask_np.shape[0]

                # Bounding box (normalized)
                bbox_x = float(xs.min()) / mask_np.shape[1]
                bbox_y = float(ys.min()) / mask_np.shape[0]
                bbox_w = float(xs.max() - xs.min()) / mask_np.shape[1]
                bbox_h = float(ys.max() - ys.min()) / mask_np.shape[0]
            else:
                centroid_x = centroid_y = 0.5
                bbox_x = bbox_y = bbox_w = bbox_h = 0

            conn.execute("""
                INSERT INTO foreground_masks
                    (image_uuid, foreground_pct, background_pct, edge_sharpness,
                     centroid_x, centroid_y, bbox_x, bbox_y, bbox_w, bbox_h, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_uuid) DO UPDATE SET
                    foreground_pct=excluded.foreground_pct,
                    background_pct=excluded.background_pct,
                    edge_sharpness=excluded.edge_sharpness,
                    centroid_x=excluded.centroid_x, centroid_y=excluded.centroid_y,
                    bbox_x=excluded.bbox_x, bbox_y=excluded.bbox_y,
                    bbox_w=excluded.bbox_w, bbox_h=excluded.bbox_h,
                    analyzed_at=excluded.analyzed_at
            """, (item["uuid"], round(fg_pct, 2), round(bg_pct, 2),
                  round(edge_sharpness, 4),
                  round(centroid_x, 4), round(centroid_y, 4),
                  round(bbox_x, 4), round(bbox_y, 4),
                  round(bbox_w, 4), round(bbox_h, 4), now_str))
            completed += 1

        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 100 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            rate = completed / elapsed
            remaining = (len(work) - completed) / rate if rate > 0 else 0
            print(f"    {completed}/{len(work)} ({rate:.1f}/s, ~{remaining:.0f}s)")

    _db_commit_retry(conn)
    _free_gpu()
    torch.backends.mps.is_available = _orig_mps_avail
    torch.backends.mps.is_built = _orig_mps_built

    elapsed = time.time() - start
    print(f"  Done: {completed} in {elapsed:.1f}s ({completed/max(1,elapsed):.1f}/s)")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 11: pose-detection
# ═══════════════════════════════════════════════════════════════════════════

def run_pose_detection(conn, limit=0, force=False):
    """Body pose estimation for images with people (YOLOv8n-pose)."""
    print("\n[Phase 11] pose-detection — YOLOv8n-pose")

    if force:
        conn.execute("DELETE FROM pose_detections")
        _db_commit_retry(conn)

    # Only process images with 'person' in object_detections
    skip_clause = "" if force else """
        AND NOT EXISTS (
            SELECT 1 FROM pose_detections pd WHERE pd.image_uuid = od.image_uuid
        )
    """

    rows = conn.execute(f"""
        SELECT DISTINCT od.image_uuid as uuid, t.local_path as source_path
        FROM object_detections od
        JOIN tiers t ON od.image_uuid = t.image_uuid
            AND t.tier_name = ? AND t.format = ? AND t.variant_id IS NULL
        WHERE od.label = 'person' AND t.local_path IS NOT NULL
            {skip_clause}
        ORDER BY od.image_uuid
    """, (SOURCE_TIER, SOURCE_FORMAT)).fetchall()

    work = [dict(r) for r in rows]
    if limit:
        work = work[:limit]

    if not work:
        print("  Nothing to process.")
        return 0

    print(f"  Loading YOLOv8n-pose...")
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  ultralytics not installed — skipping")
        return 0

    model = YOLO("yolov8n-pose.pt")

    print(f"  Processing {len(work)} images with people...")
    start = time.time()
    completed = 0
    now_str = _now()

    COCO_KEYPOINT_NAMES = [
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle"
    ]

    for item in work:
        try:
            results = model(item["source_path"], verbose=False)

            if not results or len(results) == 0:
                completed += 1
                continue

            result = results[0]
            if result.keypoints is None or result.boxes is None:
                completed += 1
                continue

            img_w = result.orig_shape[1]
            img_h = result.orig_shape[0]

            keypoints_data = result.keypoints.data.cpu().numpy()
            boxes = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()

            for pi in range(min(len(keypoints_data), 10)):  # Max 10 people
                kps = keypoints_data[pi]
                # Build keypoints dict (normalized)
                kp_dict = {}
                for ki, name in enumerate(COCO_KEYPOINT_NAMES):
                    if ki < len(kps):
                        kp_dict[name] = {
                            "x": round(float(kps[ki][0]) / img_w, 4),
                            "y": round(float(kps[ki][1]) / img_h, 4),
                            "conf": round(float(kps[ki][2]), 3) if len(kps[ki]) > 2 else 0
                        }

                box = boxes[pi] if pi < len(boxes) else [0, 0, 0, 0]
                bx = float(box[0]) / img_w
                by = float(box[1]) / img_h
                bw = float(box[2] - box[0]) / img_w
                bh = float(box[3] - box[1]) / img_h

                conn.execute("""
                    INSERT INTO pose_detections
                        (image_uuid, person_index, keypoints_json, pose_score,
                         bbox_x, bbox_y, bbox_w, bbox_h, analyzed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(image_uuid, person_index) DO UPDATE SET
                        keypoints_json=excluded.keypoints_json,
                        pose_score=excluded.pose_score,
                        bbox_x=excluded.bbox_x, bbox_y=excluded.bbox_y,
                        bbox_w=excluded.bbox_w, bbox_h=excluded.bbox_h,
                        analyzed_at=excluded.analyzed_at
                """, (item["uuid"], pi, json.dumps(kp_dict),
                      round(float(confs[pi]), 3) if pi < len(confs) else 0,
                      round(bx, 4), round(by, 4),
                      round(bw, 4), round(bh, 4), now_str))

            completed += 1

        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 200 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            print(f"    {completed}/{len(work)} ({completed/elapsed:.1f}/s)")

    _db_commit_retry(conn)
    del model
    _free_gpu()

    elapsed = time.time() - start
    print(f"  Done: {completed} in {elapsed:.1f}s ({completed/max(1,elapsed):.1f}/s)")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 12: saliency
# ═══════════════════════════════════════════════════════════════════════════

def _spectral_residual_saliency(gray):
    """Compute spectral residual saliency map (Hou & Zhang 2007).
    Pure numpy/OpenCV implementation — no contrib module needed."""
    import cv2

    # Resize to fixed size for FFT
    small = cv2.resize(gray, (64, 64)).astype(np.float64)

    # FFT
    spectrum = np.fft.fft2(small)
    amplitude = np.abs(spectrum)
    phase = np.angle(spectrum)
    log_amplitude = np.log(amplitude + 1e-10)

    # Spectral residual: log amplitude - smoothed log amplitude
    avg_filter = np.ones((3, 3)) / 9.0
    from scipy.signal import convolve2d
    smooth_log = convolve2d(log_amplitude, avg_filter, mode='same', boundary='wrap')
    spectral_residual = log_amplitude - smooth_log

    # Reconstruct with spectral residual
    saliency = np.abs(np.fft.ifft2(np.exp(spectral_residual + 1j * phase))) ** 2

    # Gaussian blur for smoothing
    saliency = cv2.GaussianBlur(saliency.astype(np.float32), (0, 0), sigmaX=2.5)

    # Resize back to original dimensions
    saliency = cv2.resize(saliency, (gray.shape[1], gray.shape[0]))

    return saliency


def run_saliency(conn, limit=0, force=False):
    """Visual saliency analysis via spectral residual method."""
    import cv2

    print("\n[Phase 12] saliency — Spectral Residual Saliency")
    work = get_work_items(conn, "saliency_maps", limit, force)
    if not work:
        print("  Nothing to process.")
        return 0

    print(f"  Processing {len(work)} images...")
    start = time.time()
    completed = 0
    now_str = _now()

    for item in work:
        try:
            img = cv2.imread(item["source_path"])
            if img is None:
                continue

            h, w = img.shape[:2]
            # Resize for speed
            scale = min(1.0, 512.0 / max(w, h))
            if scale < 1.0:
                img = cv2.resize(img, (int(w * scale), int(h * scale)))

            rh, rw = img.shape[:2]
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sal = _spectral_residual_saliency(gray)
            if sal.max() > 0:
                sal = sal / sal.max()

            # Peak location (normalized)
            peak_idx = np.unravel_index(sal.argmax(), sal.shape)
            peak_y = float(peak_idx[0]) / rh
            peak_x = float(peak_idx[1]) / rw
            peak_value = float(sal.max())

            # Spread (entropy)
            sal_flat = sal.flatten()
            sal_flat = sal_flat[sal_flat > 0.01]
            if len(sal_flat) > 0:
                sal_norm = sal_flat / sal_flat.sum()
                spread = float(-np.sum(sal_norm * np.log2(sal_norm + 1e-10)))
            else:
                spread = 0

            # Center bias: mean saliency in center 50% vs edges
            cy1, cy2 = rh // 4, 3 * rh // 4
            cx1, cx2 = rw // 4, 3 * rw // 4
            center_mean = float(sal[cy1:cy2, cx1:cx2].mean())
            edge_mean = float(sal.mean())
            center_bias = center_mean / max(edge_mean, 0.001)

            # Rule of thirds grid (3x3)
            thirds = {}
            for r in range(3):
                for c in range(3):
                    ry1 = r * rh // 3
                    ry2 = (r + 1) * rh // 3
                    rx1 = c * rw // 3
                    rx2 = (c + 1) * rw // 3
                    thirds[f"{r}_{c}"] = round(float(sal[ry1:ry2, rx1:rx2].mean()), 4)

            # Quadrants
            quadrants = {
                "top_left": round(float(sal[:rh//2, :rw//2].mean()), 4),
                "top_right": round(float(sal[:rh//2, rw//2:].mean()), 4),
                "bottom_left": round(float(sal[rh//2:, :rw//2].mean()), 4),
                "bottom_right": round(float(sal[rh//2:, rw//2:].mean()), 4),
            }

            conn.execute("""
                INSERT INTO saliency_maps
                    (image_uuid, peak_x, peak_y, peak_value, spread,
                     center_bias, thirds_json, quadrant_json, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(image_uuid) DO UPDATE SET
                    peak_x=excluded.peak_x, peak_y=excluded.peak_y,
                    peak_value=excluded.peak_value, spread=excluded.spread,
                    center_bias=excluded.center_bias,
                    thirds_json=excluded.thirds_json,
                    quadrant_json=excluded.quadrant_json,
                    analyzed_at=excluded.analyzed_at
            """, (item["uuid"], round(peak_x, 4), round(peak_y, 4),
                  round(peak_value, 4), round(spread, 3),
                  round(center_bias, 3),
                  json.dumps(thirds), json.dumps(quadrants), now_str))
            completed += 1

        except Exception as e:
            print(f"    Error {item['uuid'][:8]}: {e}", file=sys.stderr)

        if completed % 500 == 0 and completed > 0:
            _db_commit_retry(conn)
            elapsed = time.time() - start
            print(f"    {completed}/{len(work)} ({completed/elapsed:.1f}/s)")

    _db_commit_retry(conn)

    elapsed = time.time() - start
    print(f"  Done: {completed} in {elapsed:.1f}s ({completed/max(1,elapsed):.1f}/s)")
    return completed


# ═══════════════════════════════════════════════════════════════════════════
# Phase registry
# ═══════════════════════════════════════════════════════════════════════════

ALL_PHASES = [
    ("fix-blobs",         "Fix quality_scores blobs",          run_fix_blobs),
    ("gps-locations",     "GPS → image_locations",             run_gps_locations),
    ("aesthetic-v2",      "Aesthetic v2 (TOPIQ+MUSIQ+LAION)",  run_aesthetic_v2),
    ("depth-large",       "Depth Anything v2 Large",           run_depth_large),
    ("face-identity",     "Face Identity (InsightFace)",       run_face_identity),
    ("florence-captions", "Florence-2 Captions",               run_florence_captions),
    ("sam-segments",      "SAM Segmentation Stats",            run_sam_segments),
    ("grounding-dino",    "Grounding DINO Detection",          run_grounding_dino),
    ("ram-tags",          "RAM++ / CLIP Tags",                 run_ram_tags),
    ("rembg-foreground",  "Foreground Mask (rembg)",           run_rembg_foreground),
    ("pose-detection",    "Pose Detection (YOLOv8)",           run_pose_detection),
    ("saliency",          "Saliency Analysis (OpenCV)",        run_saliency),
]

PHASE_TABLE_MAP = {
    "fix-blobs":         ("quality_scores",      "image_uuid"),
    "gps-locations":     ("image_locations",      "image_uuid"),
    "aesthetic-v2":      ("aesthetic_scores_v2",   "image_uuid"),
    "depth-large":       ("depth_estimation",      "image_uuid"),
    "face-identity":     ("face_identities",       "image_uuid"),
    "florence-captions": ("florence_captions",      "image_uuid"),
    "sam-segments":      ("segmentation_masks",     "image_uuid"),
    "grounding-dino":    ("open_detections",        "image_uuid"),
    "ram-tags":          ("image_tags",             "image_uuid"),
    "rembg-foreground":  ("foreground_masks",       "image_uuid"),
    "pose-detection":    ("pose_detections",        "image_uuid"),
    "saliency":          ("saliency_maps",          "image_uuid"),
}


def show_status(conn):
    """Show status of all v2 phases."""
    total = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    print(f"\nSignals V2 Status ({total} images)")
    print(f"{'='*60}")

    for key, name, _ in ALL_PHASES:
        tbl, col = PHASE_TABLE_MAP[key]
        if tbl in tables:
            if key in ("grounding-dino", "face-identity", "pose-detection"):
                count = conn.execute(
                    f"SELECT COUNT(DISTINCT {col}) FROM {tbl}"
                ).fetchone()[0]
            elif key == "fix-blobs":
                count = conn.execute(
                    "SELECT COUNT(*) FROM quality_scores WHERE typeof(exposure_quality) != 'blob'"
                ).fetchone()[0]
                blob_count = conn.execute(
                    "SELECT COUNT(*) FROM quality_scores WHERE typeof(exposure_quality) = 'blob'"
                ).fetchone()[0]
                qstotal = conn.execute("SELECT COUNT(*) FROM quality_scores").fetchone()[0]
                pct_done = count / qstotal * 100 if qstotal else 0
                status = "DONE" if blob_count == 0 else f"{blob_count} blobs remain"
                print(f"  {name:40} {count:>6}/{qstotal}  {status}")
                continue
            elif key == "gps-locations":
                count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                gps_total = conn.execute(
                    "SELECT COUNT(*) FROM exif_metadata WHERE gps_lat IS NOT NULL"
                ).fetchone()[0]
                status = "DONE" if count >= gps_total else f"{gps_total - count} pending"
                print(f"  {name:40} {count:>6}/{gps_total}  {status}")
                continue
            else:
                count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]

            pct_done = count / total * 100 if total else 0
            status = "DONE" if count >= total else f"{pct_done:.0f}%"
            print(f"  {name:40} {count:>6}/{total}  {status}")
        else:
            denom = total
            if key == "gps-locations":
                try:
                    denom = conn.execute(
                        "SELECT COUNT(*) FROM exif_metadata WHERE gps_lat IS NOT NULL"
                    ).fetchone()[0]
                except Exception:
                    pass
            print(f"  {name:40}      0/{denom}  NOT STARTED")

    print()


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Signals V2 — Next-generation signal extraction"
    )
    parser.add_argument("--phase", nargs="+", type=str, default=None,
                        choices=[p[0] for p in ALL_PHASES],
                        help="Run specific phase(s)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only N images per phase")
    parser.add_argument("--force", action="store_true",
                        help="Re-process existing results")
    parser.add_argument("--list", action="store_true",
                        help="Show phase status and exit")
    args = parser.parse_args()

    conn = db.get_connection()
    ensure_schema(conn)

    if args.list:
        show_status(conn)
        conn.close()
        return

    # Acquire pipeline lock for mutating runs
    from pipeline_lock import acquire_lock, release_lock
    try:
        acquire_lock("signals_v2.py")
    except RuntimeError as e:
        print(f"\n  Lock error: {e}")
        conn.close()
        sys.exit(1)

    try:
        total_start = time.time()
        phases_to_run = ALL_PHASES
        if args.phase:
            phase_set = set(args.phase)
            phases_to_run = [(k, n, f) for k, n, f in ALL_PHASES if k in phase_set]

        print(f"Signals V2 — {len(phases_to_run)} phase(s)")
        print(f"{'='*60}")

        total_processed = 0
        for key, name, func in phases_to_run:
            run_id = db.start_run(conn, f"signals_v2:{key}")
            try:
                count = func(conn, limit=args.limit, force=args.force)
                total_processed += count
                db.finish_run(conn, run_id, images_processed=count)
            except Exception as e:
                print(f"\n  ERROR in {name}: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                db.finish_run(conn, run_id, status="failed",
                              error_message=str(e)[:500])

        total_elapsed = time.time() - total_start
        print(f"\n{'='*60}")
        print(f"All phases complete in {total_elapsed:.1f}s")
        print(f"Total processed: {total_processed}")

        show_status(conn)
    finally:
        release_lock()
        conn.close()


if __name__ == "__main__":
    main()
