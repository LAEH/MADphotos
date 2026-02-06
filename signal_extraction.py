#!/usr/bin/env python3
"""
signal_extraction.py — Comprehensive signal extraction for MADphotos.

Extracts ALL possible programmatic signals from every image:
  Phase 1: EXIF metadata (camera, lens, GPS, dates, settings)
  Phase 2: Dominant colors via K-means in LAB space (5 clusters)
  Phase 3: Face detection with bounding boxes + landmarks (YuNet)
  Phase 4: Object detection with labels + boxes (YOLOv8)
  Phase 5: Perceptual hashes + quality scores (pHash, blur, sharpness)

Usage:
    python signal_extraction.py                  # Run all phases
    python signal_extraction.py --phase exif     # Run single phase
    python signal_extraction.py --phase colors faces objects hashes
    python signal_extraction.py --reprocess      # Redo already-processed
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import struct
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

import cv2
import numpy as np
from PIL import Image, ExifTags

DB_PATH = Path(__file__).resolve().parent / "mad_photos.db"
BASE_DIR = Path(__file__).resolve().parent
YUNET_MODEL = BASE_DIR / "face_detection_yunet_2023mar.onnx"

# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS exif_metadata (
    image_uuid TEXT PRIMARY KEY,
    make TEXT,
    model TEXT,
    lens TEXT,
    focal_length REAL,
    focal_length_35mm REAL,
    aperture REAL,
    shutter_speed TEXT,
    iso INTEGER,
    date_taken TEXT,
    gps_lat REAL,
    gps_lon REAL,
    gps_alt REAL,
    orientation INTEGER,
    pixel_width INTEGER,
    pixel_height INTEGER,
    software TEXT,
    flash TEXT,
    metering_mode TEXT,
    white_balance TEXT,
    exposure_program TEXT,
    exposure_bias REAL,
    color_space TEXT,
    raw_exif TEXT,
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS dominant_colors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid TEXT NOT NULL,
    cluster_index INTEGER NOT NULL,
    r INTEGER, g INTEGER, b INTEGER,
    hex TEXT,
    l REAL, a REAL, b_val REAL,
    percentage REAL,
    color_name TEXT,
    analyzed_at TEXT,
    UNIQUE(image_uuid, cluster_index)
);

CREATE TABLE IF NOT EXISTS face_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid TEXT NOT NULL,
    face_index INTEGER NOT NULL,
    x REAL, y REAL, w REAL, h REAL,
    confidence REAL,
    right_eye_x REAL, right_eye_y REAL,
    left_eye_x REAL, left_eye_y REAL,
    nose_x REAL, nose_y REAL,
    mouth_right_x REAL, mouth_right_y REAL,
    mouth_left_x REAL, mouth_left_y REAL,
    face_area_pct REAL,
    analyzed_at TEXT,
    UNIQUE(image_uuid, face_index)
);

CREATE TABLE IF NOT EXISTS object_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_uuid TEXT NOT NULL,
    detection_index INTEGER NOT NULL,
    label TEXT,
    confidence REAL,
    x REAL, y REAL, w REAL, h REAL,
    area_pct REAL,
    analyzed_at TEXT,
    UNIQUE(image_uuid, detection_index)
);

CREATE TABLE IF NOT EXISTS image_hashes (
    image_uuid TEXT PRIMARY KEY,
    phash TEXT,
    ahash TEXT,
    dhash TEXT,
    whash TEXT,
    blur_score REAL,
    sharpness_score REAL,
    edge_density REAL,
    entropy REAL,
    analyzed_at TEXT
);
"""

# ---------------------------------------------------------------------------
# Color name mapping (CSS named colors subset)
# ---------------------------------------------------------------------------

NAMED_COLORS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "gray": (128, 128, 128),
    "silver": (192, 192, 192), "red": (255, 0, 0), "maroon": (128, 0, 0),
    "yellow": (255, 255, 0), "olive": (128, 128, 0), "lime": (0, 255, 0),
    "green": (0, 128, 0), "aqua": (0, 255, 255), "teal": (0, 128, 128),
    "blue": (0, 0, 255), "navy": (0, 0, 128), "fuchsia": (255, 0, 255),
    "purple": (128, 0, 128), "orange": (255, 165, 0), "brown": (139, 69, 19),
    "beige": (245, 245, 220), "ivory": (255, 255, 240), "coral": (255, 127, 80),
    "salmon": (250, 128, 114), "pink": (255, 192, 203), "gold": (255, 215, 0),
    "khaki": (240, 230, 140), "tan": (210, 180, 140), "crimson": (220, 20, 60),
    "indigo": (75, 0, 130), "violet": (238, 130, 238), "cyan": (0, 255, 255),
    "turquoise": (64, 224, 208), "slate": (112, 128, 144), "charcoal": (54, 69, 79),
    "cream": (255, 253, 208), "rust": (183, 65, 14), "burgundy": (128, 0, 32),
    "forest": (34, 139, 34), "sky": (135, 206, 235), "steel": (70, 130, 180),
    "peach": (255, 218, 185), "lavender": (230, 230, 250), "mint": (189, 252, 201),
}


def nearest_color_name(r, g, b):
    # type: (int, int, int) -> str
    best_name = "gray"
    best_dist = float("inf")
    for name, (nr, ng, nb) in NAMED_COLORS.items():
        d = (r - nr) ** 2 + (g - ng) ** 2 + (b - nb) ** 2
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_conn():
    # type: () -> sqlite3.Connection
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    return conn


def get_image_paths():
    # type: () -> List[Tuple[str, str]]
    """Return (uuid, display_tier_path) for all images with display tier."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.uuid, t.local_path
        FROM images i
        JOIN tiers t ON i.uuid = t.image_uuid
        WHERE t.tier_name = 'display' AND t.format = 'jpeg'
    """).fetchall()
    conn.close()
    result = []
    for uuid, path in rows:
        if path and os.path.exists(path):
            result.append((uuid, path))
    return result


def get_original_paths():
    # type: () -> List[Tuple[str, str]]
    """Return (uuid, original_path) for EXIF extraction."""
    originals_dir = BASE_DIR / "originals"
    conn = get_conn()
    rows = conn.execute("SELECT uuid, original_path FROM images").fetchall()
    conn.close()
    result = []
    for uuid, rel_path in rows:
        if not rel_path:
            continue
        full_path = str(originals_dir / rel_path)
        if os.path.exists(full_path):
            result.append((uuid, full_path))
    return result


def get_thumb_paths():
    # type: () -> List[Tuple[str, str]]
    """Return (uuid, thumb_path) for hash computation."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.uuid, t.local_path
        FROM images i
        JOIN tiers t ON i.uuid = t.image_uuid
        WHERE t.tier_name = 'thumb' AND t.format = 'jpeg'
    """).fetchall()
    conn.close()
    return [(uuid, path) for uuid, path in rows if path and os.path.exists(path)]


def timestamp():
    # type: () -> str
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Phase 1: EXIF Extraction
# ---------------------------------------------------------------------------

def _parse_gps(gps_info):
    # type: (dict) -> Tuple[Optional[float], Optional[float], Optional[float]]
    """Parse GPS IFD into (lat, lon, alt)."""
    def _to_degrees(vals):
        try:
            d = float(vals[0])
            m = float(vals[1])
            s = float(vals[2])
            return d + m / 60.0 + s / 3600.0
        except Exception:
            return None

    lat = lon = alt = None
    try:
        if 2 in gps_info and 1 in gps_info:
            lat = _to_degrees(gps_info[2])
            if lat and gps_info[1] == "S":
                lat = -lat
        if 4 in gps_info and 3 in gps_info:
            lon = _to_degrees(gps_info[4])
            if lon and gps_info[3] == "W":
                lon = -lon
        if 6 in gps_info:
            alt = float(gps_info[6])
            if 5 in gps_info and gps_info[5] == 1:
                alt = -alt
    except Exception:
        pass
    return lat, lon, alt


def extract_exif(reprocess=False):
    # type: (bool) -> None
    """Extract EXIF metadata from all original images."""
    conn = get_conn()
    if reprocess:
        conn.execute("DELETE FROM exif_metadata")
        conn.commit()

    existing = set(
        r[0] for r in conn.execute("SELECT image_uuid FROM exif_metadata").fetchall()
    )
    paths = get_original_paths()
    todo = [(u, p) for u, p in paths if u not in existing]

    print(f"[EXIF] {len(todo)} images to process ({len(existing)} already done)")
    if not todo:
        return

    ts = timestamp()
    count = 0
    gps_count = 0
    t0 = time.time()

    for uuid, path in todo:
        try:
            img = Image.open(path)
            exif_raw = img.getexif()
            if not exif_raw:
                # Still insert a row so we don't retry
                conn.execute(
                    "INSERT OR REPLACE INTO exif_metadata (image_uuid, extracted_at) VALUES (?, ?)",
                    (uuid, ts)
                )
                count += 1
                continue

            # Build tag name dict
            tags = {}
            for tag_id, value in exif_raw.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                # Convert IFDRational and other special types
                try:
                    json.dumps(value)
                    tags[tag_name] = value
                except (TypeError, ValueError):
                    tags[tag_name] = str(value)

            # GPS
            gps_ifd = exif_raw.get_ifd(ExifTags.IFD.GPSInfo)
            lat, lon, alt = _parse_gps(gps_ifd) if gps_ifd else (None, None, None)
            if lat is not None:
                gps_count += 1

            # EXIF sub-IFD
            exif_ifd = exif_raw.get_ifd(ExifTags.IFD.Exif)
            exif_tags = {}
            for tag_id, value in exif_ifd.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                try:
                    json.dumps(value)
                    exif_tags[tag_name] = value
                except (TypeError, ValueError):
                    exif_tags[tag_name] = str(value)

            # Merge for raw dump
            all_tags = {**tags, **exif_tags}

            # Extract specific fields
            make = tags.get("Make", "")
            model = tags.get("Model", "")
            software = tags.get("Software", "")
            orientation = tags.get("Orientation")
            date_taken = exif_tags.get("DateTimeOriginal") or tags.get("DateTime")

            focal_length = None
            fl = exif_tags.get("FocalLength")
            if fl is not None:
                try:
                    focal_length = float(fl)
                except (TypeError, ValueError):
                    pass

            focal_35 = None
            fl35 = exif_tags.get("FocalLengthIn35mmFilm")
            if fl35 is not None:
                try:
                    focal_35 = float(fl35)
                except (TypeError, ValueError):
                    pass

            aperture = None
            fn = exif_tags.get("FNumber")
            if fn is not None:
                try:
                    aperture = float(fn)
                except (TypeError, ValueError):
                    pass

            iso = exif_tags.get("ISOSpeedRatings")
            if isinstance(iso, tuple):
                iso = iso[0] if iso else None

            shutter = None
            et = exif_tags.get("ExposureTime")
            if et is not None:
                try:
                    etf = float(et)
                    if etf < 1:
                        shutter = f"1/{int(round(1/etf))}"
                    else:
                        shutter = f"{etf}s"
                except (TypeError, ValueError, ZeroDivisionError):
                    shutter = str(et)

            flash = exif_tags.get("Flash")
            if flash is not None:
                flash = str(flash)

            metering = exif_tags.get("MeteringMode")
            metering_map = {0: "Unknown", 1: "Average", 2: "CenterWeighted",
                           3: "Spot", 4: "MultiSpot", 5: "Pattern", 6: "Partial"}
            metering_str = metering_map.get(metering, str(metering)) if metering is not None else None

            wb = exif_tags.get("WhiteBalance")
            wb_str = {0: "Auto", 1: "Manual"}.get(wb, str(wb)) if wb is not None else None

            exp_program = exif_tags.get("ExposureProgram")
            exp_map = {0: "Undefined", 1: "Manual", 2: "Auto", 3: "Aperture Priority",
                       4: "Shutter Priority", 5: "Creative", 6: "Action", 7: "Portrait", 8: "Landscape"}
            exp_str = exp_map.get(exp_program, str(exp_program)) if exp_program is not None else None

            exp_bias = None
            eb = exif_tags.get("ExposureBiasValue")
            if eb is not None:
                try:
                    exp_bias = float(eb)
                except (TypeError, ValueError):
                    pass

            color_space = exif_tags.get("ColorSpace")
            cs_str = {1: "sRGB", 65535: "Uncalibrated"}.get(color_space, str(color_space)) if color_space is not None else None

            lens = exif_tags.get("LensModel") or exif_tags.get("LensMake", "")

            pw = tags.get("ImageWidth") or exif_tags.get("PixelXDimension")
            ph = tags.get("ImageLength") or exif_tags.get("PixelYDimension")

            # Serialize raw exif
            try:
                raw_json = json.dumps(all_tags, default=str, ensure_ascii=False)
            except Exception:
                raw_json = "{}"

            conn.execute("""
                INSERT OR REPLACE INTO exif_metadata (
                    image_uuid, make, model, lens, focal_length, focal_length_35mm,
                    aperture, shutter_speed, iso, date_taken, gps_lat, gps_lon, gps_alt,
                    orientation, pixel_width, pixel_height, software, flash, metering_mode,
                    white_balance, exposure_program, exposure_bias, color_space,
                    raw_exif, extracted_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                uuid, make, model, lens, focal_length, focal_35,
                aperture, shutter, iso, date_taken, lat, lon, alt,
                orientation, pw, ph, software, flash, metering_str,
                wb_str, exp_str, exp_bias, cs_str,
                raw_json, ts
            ))

            count += 1
            if count % 500 == 0:
                conn.commit()
                elapsed = time.time() - t0
                rate = count / elapsed
                print(f"  {count}/{len(todo)} ({rate:.0f}/s) — {gps_count} with GPS")

        except Exception as e:
            # Insert empty row to avoid retrying
            conn.execute(
                "INSERT OR REPLACE INTO exif_metadata (image_uuid, extracted_at) VALUES (?, ?)",
                (uuid, ts)
            )
            count += 1

    conn.commit()
    conn.close()
    elapsed = time.time() - t0
    print(f"[EXIF] Done: {count} images in {elapsed:.1f}s ({count/elapsed:.0f}/s), {gps_count} with GPS")


# ---------------------------------------------------------------------------
# Phase 2: Dominant Colors (K-means in LAB)
# ---------------------------------------------------------------------------

def extract_colors(reprocess=False, n_clusters=5):
    # type: (bool, int) -> None
    """Extract dominant colors using K-means clustering in LAB color space."""
    from sklearn.cluster import KMeans

    conn = get_conn()
    if reprocess:
        conn.execute("DELETE FROM dominant_colors")
        conn.commit()

    existing = set(
        r[0] for r in conn.execute("SELECT DISTINCT image_uuid FROM dominant_colors").fetchall()
    )
    paths = get_image_paths()
    todo = [(u, p) for u, p in paths if u not in existing]

    print(f"[Colors] {len(todo)} images to process ({len(existing)} already done)")
    if not todo:
        return

    ts = timestamp()
    count = 0
    t0 = time.time()

    for uuid, path in todo:
        try:
            # Load and resize for speed
            img = cv2.imread(path)
            if img is None:
                count += 1
                continue

            # Resize to ~200px wide for clustering speed
            h, w = img.shape[:2]
            scale = 200.0 / max(w, h)
            if scale < 1:
                img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

            # Convert to LAB
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            pixels = lab.reshape(-1, 3).astype(np.float32)

            # K-means
            km = KMeans(n_clusters=n_clusters, n_init=3, max_iter=100, random_state=42)
            km.fit(pixels)

            # Get cluster sizes
            labels, counts_arr = np.unique(km.labels_, return_counts=True)
            total_px = len(km.labels_)

            # Sort by cluster size (largest first)
            order = np.argsort(-counts_arr)

            for idx, cluster_idx in enumerate(order):
                center_lab = km.cluster_centers_[cluster_idx]
                pct = counts_arr[cluster_idx] / total_px

                # Convert LAB center back to RGB
                lab_pixel = np.uint8([[center_lab]])
                bgr_pixel = cv2.cvtColor(lab_pixel, cv2.COLOR_LAB2BGR)
                b_val, g_val, r_val = int(bgr_pixel[0, 0, 0]), int(bgr_pixel[0, 0, 1]), int(bgr_pixel[0, 0, 2])
                hex_str = f"#{r_val:02x}{g_val:02x}{b_val:02x}"
                name = nearest_color_name(r_val, g_val, b_val)

                conn.execute("""
                    INSERT OR REPLACE INTO dominant_colors (
                        image_uuid, cluster_index, r, g, b, hex, l, a, b_val,
                        percentage, color_name, analyzed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    uuid, idx, r_val, g_val, b_val, hex_str,
                    float(center_lab[0]), float(center_lab[1]), float(center_lab[2]),
                    float(pct), name, ts
                ))

            count += 1
            if count % 200 == 0:
                conn.commit()
                elapsed = time.time() - t0
                rate = count / elapsed
                print(f"  {count}/{len(todo)} ({rate:.0f}/s)")

        except Exception as e:
            count += 1

    conn.commit()
    conn.close()
    elapsed = time.time() - t0
    print(f"[Colors] Done: {count} images in {elapsed:.1f}s ({count/elapsed:.0f}/s)")


# ---------------------------------------------------------------------------
# Phase 3: Face Detection (YuNet)
# ---------------------------------------------------------------------------

def extract_faces(reprocess=False):
    # type: (bool) -> None
    """Detect faces with YuNet, store bounding boxes + 5 landmarks."""
    if not YUNET_MODEL.exists():
        print(f"[Faces] ERROR: YuNet model not found at {YUNET_MODEL}")
        return

    conn = get_conn()
    if reprocess:
        conn.execute("DELETE FROM face_detections")
        conn.commit()

    existing = set(
        r[0] for r in conn.execute("SELECT DISTINCT image_uuid FROM face_detections").fetchall()
    )
    # Also track images with zero faces (store nothing but mark as processed)
    zero_face_marker = set(
        r[0] for r in conn.execute("""
            SELECT image_uuid FROM image_hashes WHERE image_uuid NOT IN
            (SELECT DISTINCT image_uuid FROM face_detections)
        """).fetchall()
    )
    # We need a separate tracking mechanism for "processed but zero faces"
    # Use a simple approach: check if uuid is in existing OR in a temp table
    # For simplicity, keep a local set of processed UUIDs
    processed_file = BASE_DIR / ".faces_processed.json"
    processed_uuids = set()
    if not reprocess and processed_file.exists():
        try:
            processed_uuids = set(json.loads(processed_file.read_text()))
        except Exception:
            pass

    paths = get_image_paths()
    todo = [(u, p) for u, p in paths if u not in existing and u not in processed_uuids]

    print(f"[Faces] {len(todo)} images to process ({len(existing)} with faces, {len(processed_uuids)} zero-face)")
    if not todo:
        return

    # Create face detector
    fd = cv2.FaceDetectorYN.create(str(YUNET_MODEL), "", (320, 320), 0.6, 0.3, 5000)

    ts = timestamp()
    count = 0
    face_count = 0
    t0 = time.time()
    all_processed = set(processed_uuids)

    for uuid, path in todo:
        try:
            img = cv2.imread(path)
            if img is None:
                all_processed.add(uuid)
                count += 1
                continue

            h, w = img.shape[:2]
            # Resize for detection (YuNet works best at moderate sizes)
            scale = min(1.0, 1024.0 / max(w, h))
            if scale < 1:
                det_img = cv2.resize(img, (int(w * scale), int(h * scale)))
            else:
                det_img = img
            dh, dw = det_img.shape[:2]

            fd.setInputSize((dw, dh))
            _, faces = fd.detect(det_img)

            if faces is not None and len(faces) > 0:
                for i, face in enumerate(faces):
                    # face: [x, y, w, h, right_eye_x, right_eye_y, left_eye_x, left_eye_y,
                    #        nose_x, nose_y, mouth_right_x, mouth_right_y, mouth_left_x, mouth_left_y, confidence]
                    fx, fy, fw, fh = face[0]/dw, face[1]/dh, face[2]/dw, face[3]/dh
                    conf = float(face[14])
                    face_area = fw * fh

                    conn.execute("""
                        INSERT OR REPLACE INTO face_detections (
                            image_uuid, face_index, x, y, w, h, confidence,
                            right_eye_x, right_eye_y, left_eye_x, left_eye_y,
                            nose_x, nose_y, mouth_right_x, mouth_right_y,
                            mouth_left_x, mouth_left_y, face_area_pct, analyzed_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        uuid, i,
                        float(fx), float(fy), float(fw), float(fh), conf,
                        float(face[4]/dw), float(face[5]/dh),
                        float(face[6]/dw), float(face[7]/dh),
                        float(face[8]/dw), float(face[9]/dh),
                        float(face[10]/dw), float(face[11]/dh),
                        float(face[12]/dw), float(face[13]/dh),
                        float(face_area), ts
                    ))
                    face_count += 1
            else:
                all_processed.add(uuid)

            count += 1
            if count % 200 == 0:
                conn.commit()
                # Save processed set periodically
                processed_file.write_text(json.dumps(list(all_processed)))
                elapsed = time.time() - t0
                rate = count / elapsed
                print(f"  {count}/{len(todo)} ({rate:.0f}/s) — {face_count} faces found")

        except Exception as e:
            all_processed.add(uuid)
            count += 1

    conn.commit()
    processed_file.write_text(json.dumps(list(all_processed)))
    conn.close()
    elapsed = time.time() - t0
    print(f"[Faces] Done: {count} images in {elapsed:.1f}s ({count/elapsed:.0f}/s), {face_count} faces detected")


# ---------------------------------------------------------------------------
# Phase 4: Object Detection (YOLOv8)
# ---------------------------------------------------------------------------

def extract_objects(reprocess=False, conf_threshold=0.35):
    # type: (bool, float) -> None
    """Detect objects using YOLOv8, keep high-confidence detections."""
    from ultralytics import YOLO

    conn = get_conn()
    if reprocess:
        conn.execute("DELETE FROM object_detections")
        conn.commit()

    existing = set(
        r[0] for r in conn.execute("SELECT DISTINCT image_uuid FROM object_detections").fetchall()
    )
    # Track zero-detection images
    processed_file = BASE_DIR / ".objects_processed.json"
    processed_uuids = set()
    if not reprocess and processed_file.exists():
        try:
            processed_uuids = set(json.loads(processed_file.read_text()))
        except Exception:
            pass

    paths = get_image_paths()
    todo = [(u, p) for u, p in paths if u not in existing and u not in processed_uuids]

    print(f"[Objects] {len(todo)} images to process ({len(existing)} with objects, {len(processed_uuids)} zero-detect)")
    if not todo:
        return

    # Load YOLO model
    model = YOLO("yolov8n.pt")
    print(f"[Objects] YOLOv8n loaded, {len(model.names)} classes, conf>{conf_threshold}")

    ts = timestamp()
    count = 0
    det_count = 0
    t0 = time.time()
    all_processed = set(processed_uuids)

    # Process in batches for efficiency
    batch_size = 16
    for batch_start in range(0, len(todo), batch_size):
        batch = todo[batch_start:batch_start + batch_size]
        batch_paths = [p for _, p in batch]
        batch_uuids = [u for u, _ in batch]

        try:
            results = model(batch_paths, verbose=False, conf=conf_threshold, device="mps")

            for uuid, result in zip(batch_uuids, results):
                boxes = result.boxes
                if boxes is not None and len(boxes) > 0:
                    # Sort by confidence descending
                    confs = boxes.conf.cpu().numpy()
                    order = np.argsort(-confs)

                    for det_idx, idx in enumerate(order):
                        if det_idx >= 20:  # Max 20 detections per image
                            break
                        box = boxes.xyxyn[idx].cpu().numpy()  # normalized x1,y1,x2,y2
                        cls = int(boxes.cls[idx].cpu().numpy())
                        conf = float(confs[idx])
                        label = model.names[cls]

                        x1, y1, x2, y2 = box
                        bw = x2 - x1
                        bh = y2 - y1
                        area = bw * bh

                        conn.execute("""
                            INSERT OR REPLACE INTO object_detections (
                                image_uuid, detection_index, label, confidence,
                                x, y, w, h, area_pct, analyzed_at
                            ) VALUES (?,?,?,?,?,?,?,?,?,?)
                        """, (
                            uuid, det_idx, label, conf,
                            float(x1), float(y1), float(bw), float(bh),
                            float(area), ts
                        ))
                        det_count += 1
                else:
                    all_processed.add(uuid)

                count += 1

        except Exception as e:
            for uuid in batch_uuids:
                all_processed.add(uuid)
                count += 1

        if count % 200 == 0 and count > 0:
            conn.commit()
            processed_file.write_text(json.dumps(list(all_processed)))
            elapsed = time.time() - t0
            rate = count / elapsed
            print(f"  {count}/{len(todo)} ({rate:.0f}/s) — {det_count} detections")

    conn.commit()
    processed_file.write_text(json.dumps(list(all_processed)))
    conn.close()
    elapsed = time.time() - t0
    print(f"[Objects] Done: {count} images in {elapsed:.1f}s ({count/elapsed:.0f}/s), {det_count} detections")


# ---------------------------------------------------------------------------
# Phase 5: Perceptual Hashes + Quality Metrics
# ---------------------------------------------------------------------------

def extract_hashes(reprocess=False):
    # type: (bool) -> None
    """Compute perceptual hashes, blur score, sharpness, edge density, entropy."""
    import imagehash

    conn = get_conn()
    if reprocess:
        conn.execute("DELETE FROM image_hashes")
        conn.commit()

    existing = set(
        r[0] for r in conn.execute("SELECT image_uuid FROM image_hashes").fetchall()
    )
    paths = get_thumb_paths()
    todo = [(u, p) for u, p in paths if u not in existing]

    print(f"[Hashes] {len(todo)} images to process ({len(existing)} already done)")
    if not todo:
        return

    ts = timestamp()
    count = 0
    t0 = time.time()

    for uuid, path in todo:
        try:
            # Perceptual hashes via PIL
            pil_img = Image.open(path)
            ph = str(imagehash.phash(pil_img))
            ah = str(imagehash.average_hash(pil_img))
            dh = str(imagehash.dhash(pil_img))
            wh = str(imagehash.whash(pil_img))

            # Quality metrics via OpenCV
            img = cv2.imread(path)
            if img is None:
                count += 1
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Blur score (Laplacian variance — higher = sharper)
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            blur_score = float(laplacian.var())

            # Sharpness (mean absolute Laplacian)
            sharpness = float(np.mean(np.abs(laplacian)))

            # Edge density (Canny edge pixels / total pixels)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = float(np.count_nonzero(edges) / edges.size)

            # Entropy (information content)
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
            hist = hist / hist.sum()
            hist = hist[hist > 0]
            entropy = float(-np.sum(hist * np.log2(hist)))

            conn.execute("""
                INSERT OR REPLACE INTO image_hashes (
                    image_uuid, phash, ahash, dhash, whash,
                    blur_score, sharpness_score, edge_density, entropy,
                    analyzed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                uuid, ph, ah, dh, wh,
                blur_score, sharpness, edge_density, entropy, ts
            ))

            count += 1
            if count % 500 == 0:
                conn.commit()
                elapsed = time.time() - t0
                rate = count / elapsed
                print(f"  {count}/{len(todo)} ({rate:.0f}/s)")

        except Exception as e:
            count += 1

    conn.commit()
    conn.close()
    elapsed = time.time() - t0
    print(f"[Hashes] Done: {count} images in {elapsed:.1f}s ({count/elapsed:.0f}/s)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_PHASES = ["exif", "colors", "faces", "objects", "hashes"]

PHASE_MAP = {
    "exif": extract_exif,
    "colors": extract_colors,
    "faces": extract_faces,
    "objects": extract_objects,
    "hashes": extract_hashes,
}


def main():
    parser = argparse.ArgumentParser(description="Signal extraction for MADphotos")
    parser.add_argument("--phase", nargs="*", choices=ALL_PHASES, default=None,
                        help="Phases to run (default: all)")
    parser.add_argument("--reprocess", action="store_true",
                        help="Reprocess already-analyzed images")
    args = parser.parse_args()

    phases = args.phase if args.phase else ALL_PHASES

    print(f"{'=' * 60}")
    print(f"Signal Extraction — {len(phases)} phases")
    print(f"{'=' * 60}")
    t0 = time.time()

    for phase in phases:
        print(f"\n{'─' * 40}")
        fn = PHASE_MAP[phase]
        fn(reprocess=args.reprocess)

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"All done in {elapsed:.1f}s ({elapsed/60:.1f}m)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
