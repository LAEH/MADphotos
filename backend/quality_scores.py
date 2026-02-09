#!/usr/bin/env python3
"""
Quality scoring pipeline for MADphotos.
Runs two quality scorers on all images and stores results in quality_scores table.

Approach 1: Technical quality (sharpness, noise, exposure, contrast) — no model needed
Approach 2: CLIP semantic quality ("good photo" vs "bad photo" prompts)

Usage: python3 quality_scores.py [--skip-existing] [--limit N]
"""

import sys
import os
import time
import sqlite3
import argparse
import numpy as np

# Paths
BASE_PATH = "/Users/laeh/Github/MADphotos"
DB_PATH = os.path.join(BASE_PATH, "images/mad_photos.db")
DISPLAY_DIR = os.path.join(BASE_PATH, "images/rendered/display/jpeg")


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quality_scores (
            image_uuid       TEXT PRIMARY KEY REFERENCES images(uuid),
            technical_score  REAL,
            clip_score       REAL,
            combined_score   REAL,
            sharpness        REAL,
            noise            REAL,
            exposure_quality REAL,
            contrast         REAL,
            analyzed_at      TEXT NOT NULL
        )
    """)
    conn.commit()


def compute_technical_score(img_path):
    """Compute technical quality metrics from image file."""
    import cv2
    from skimage.restoration import estimate_sigma

    img = cv2.imread(img_path)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. Sharpness (Laplacian variance)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    sharpness_raw = lap.var()

    # 2. Noise estimation
    try:
        noise_raw = estimate_sigma(gray, channel_axis=None)
    except Exception:
        noise_raw = 5.0

    # 3. Exposure quality (histogram entropy + clipping penalty)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    hist_norm = hist / hist.sum()
    entropy = -np.sum(hist_norm[hist_norm > 0] * np.log2(hist_norm[hist_norm > 0]))
    max_entropy = 8.0  # log2(256)
    clip_low = hist_norm[:5].sum()
    clip_high = hist_norm[251:].sum()
    clip_penalty = min(1.0, (clip_low + clip_high) * 5)
    exposure_raw = (entropy / max_entropy) * (1 - clip_penalty)

    # 4. Contrast (std dev of luminance)
    contrast_raw = gray.std()

    # Normalize to 0-100 scales
    sharpness_score = min(100, max(0, np.log1p(sharpness_raw) / np.log1p(2000) * 100))
    noise_score = min(100, max(0, 100 - noise_raw * 8))
    exposure_score = min(100, max(0, exposure_raw * 120))
    contrast_score = min(100, max(0, contrast_raw / 80 * 100))

    # Weighted composite
    technical = (
        sharpness_score * 0.35 +
        noise_score * 0.20 +
        exposure_score * 0.25 +
        contrast_score * 0.20
    )

    return {
        "technical_score": round(technical, 2),
        "sharpness": round(sharpness_raw, 2),
        "noise": round(noise_raw, 4),
        "exposure_quality": round(exposure_score, 2),
        "contrast": round(contrast_raw, 2),
    }


def load_clip_model():
    """Load CLIP model for semantic quality scoring."""
    import torch
    from transformers import CLIPProcessor, CLIPModel

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading CLIP model on {device}...")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    model.eval()

    positive = [
        "a high quality photograph",
        "a beautiful photograph with great composition",
        "a professional photograph",
        "an award winning photograph",
        "a stunning photograph with excellent lighting",
    ]
    negative = [
        "a low quality photograph",
        "a blurry out of focus photograph",
        "a poorly exposed photograph",
        "an amateur snapshot",
        "a boring photograph",
    ]
    all_prompts = positive + negative
    text_inputs = processor(text=all_prompts, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        text_features = model.get_text_features(**text_inputs)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    return model, processor, text_features, len(positive), device


def compute_clip_score(img_path, model, processor, text_features, n_positive, device):
    """Compute CLIP-based semantic quality score."""
    import torch
    from PIL import Image

    try:
        img = Image.open(img_path).convert("RGB")
        # Resize for speed if very large
        if max(img.size) > 1024:
            ratio = 1024 / max(img.size)
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)), Image.LANCZOS)

        inputs = processor(images=img, return_tensors="pt").to(device)
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        similarities = (image_features @ text_features.T).squeeze().cpu().numpy()
        pos_score = similarities[:n_positive].mean()
        neg_score = similarities[n_positive:].mean()
        raw = pos_score - neg_score

        # Sigmoid mapping to 0-100
        clip_score = 100 / (1 + np.exp(-raw * 15))
        return round(float(clip_score), 2)
    except Exception as e:
        print(f"  CLIP error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-existing", action="store_true", help="Skip images already scored")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of images (0=all)")
    parser.add_argument("--technical-only", action="store_true", help="Skip CLIP, technical only")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    create_table(conn)

    # Get all UUIDs
    if args.skip_existing:
        uuids = [r[0] for r in conn.execute(
            "SELECT uuid FROM images WHERE uuid NOT IN (SELECT image_uuid FROM quality_scores)"
        ).fetchall()]
    else:
        uuids = [r[0] for r in conn.execute("SELECT uuid FROM images").fetchall()]

    if args.limit > 0:
        uuids = uuids[:args.limit]

    total = len(uuids)
    print(f"Scoring {total} images...")

    # Load CLIP model
    clip_model = clip_proc = clip_text = clip_device = None
    n_positive = 0
    if not args.technical_only:
        try:
            clip_model, clip_proc, clip_text, n_positive, clip_device = load_clip_model()
            print("CLIP model loaded.")
        except Exception as e:
            print(f"CLIP load failed: {e} — running technical only")

    start = time.time()
    batch = []
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    for idx, uuid in enumerate(uuids):
        img_path = os.path.join(DISPLAY_DIR, f"{uuid}.jpg")
        if not os.path.exists(img_path):
            continue

        # Technical score
        tech = compute_technical_score(img_path)
        if tech is None:
            continue

        # CLIP score
        clip_score = None
        if clip_model is not None:
            clip_score = compute_clip_score(img_path, clip_model, clip_proc, clip_text, n_positive, clip_device)

        # Combined score (average if both available)
        if clip_score is not None:
            combined = round((tech["technical_score"] + clip_score) / 2, 2)
        else:
            combined = tech["technical_score"]

        batch.append((
            uuid,
            tech["technical_score"],
            clip_score,
            combined,
            tech["sharpness"],
            tech["noise"],
            tech["exposure_quality"],
            tech["contrast"],
            now,
        ))

        # Batch insert every 100
        if len(batch) >= 100:
            conn.executemany(
                """INSERT OR REPLACE INTO quality_scores
                   (image_uuid, technical_score, clip_score, combined_score,
                    sharpness, noise, exposure_quality, contrast, analyzed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                batch,
            )
            conn.commit()
            elapsed = time.time() - start
            rate = (idx + 1) / elapsed
            eta = (total - idx - 1) / rate if rate > 0 else 0
            print(f"  {idx + 1}/{total} ({rate:.1f}/s, ETA {eta:.0f}s)")
            batch = []

    # Final batch
    if batch:
        conn.executemany(
            """INSERT OR REPLACE INTO quality_scores
               (image_uuid, technical_score, clip_score, combined_score,
                sharpness, noise, exposure_quality, contrast, analyzed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            batch,
        )
        conn.commit()

    elapsed = time.time() - start
    count = conn.execute("SELECT COUNT(*) FROM quality_scores").fetchone()[0]
    print(f"\nDone! {count} images scored in {elapsed:.1f}s ({total/elapsed:.1f}/s)")

    # Stats
    for col_name in ["technical_score", "clip_score", "combined_score"]:
        row = conn.execute(f"""
            SELECT AVG({col_name}), MIN({col_name}), MAX({col_name}),
                   AVG(({col_name} - sub.mean) * ({col_name} - sub.mean))
            FROM quality_scores, (SELECT AVG({col_name}) as mean FROM quality_scores) sub
            WHERE {col_name} IS NOT NULL
        """).fetchone()
        if row and row[0]:
            std = row[3] ** 0.5 if row[3] else 0
            print(f"  {col_name}: mean={row[0]:.1f}, min={row[1]:.1f}, max={row[2]:.1f}, std={std:.1f}")

    conn.close()


if __name__ == "__main__":
    main()
