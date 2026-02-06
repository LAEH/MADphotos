#!/usr/bin/env python3
"""
photography_engine.py — Gemini 2.5 Pro photography analysis with robust retry logic.

Sends rendered gemini-tier images to Gemini for structured analysis.
Stores parsed results in the comprehensive mad_photos.db database.
Retries failed images with exponential backoff until all are processed.

Usage:
    python photography_engine.py                # Analyze all unprocessed images
    python photography_engine.py --test 5       # Only 5 images
    python photography_engine.py --concurrent 3 # Override concurrency
    python photography_engine.py --max-retries 10  # Keep retrying
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

import mad_database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "rendered" / "gemini" / "jpeg"
MANIFEST_PATH = BASE_DIR / "rendered" / "manifest.json"

# Use Vertex AI with Application Default Credentials (same as imagen_engine)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "madbox-e4a35")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

MODEL_ID = "gemini-2.5-pro"
MAX_CONCURRENT = 5
MAX_RETRIES = 5
BASE_BACKOFF = 2.0  # seconds, doubles each retry

SYSTEM_PROMPT = """
You are a Master Photography Critic and Technical Analyst.
Analyze the image with 'Agentic Vision': zoom in on focal points and inspect technical nuances.
Return ONLY a JSON object with this exact schema:

{
  "technical": {
    "exposure": "Balanced|Under|Over",
    "sharpness": "Tack Sharp|Soft|Motion Blur",
    "lens_artifacts": ["Vignetting", "Flare", "Compression"]
  },
  "composition": {
    "technique": "Rule of Thirds|Golden Ratio|Negative Space",
    "depth": "Shallow Bokeh|Deep Focus",
    "geometry": ["Leading Lines", "Symmetry"]
  },
  "color": {
    "palette": ["#hex1", "#hex2"],
    "semantic_pops": [{"color": "Red", "object": "Airplane", "impact": "High"}],
    "grading_style": "Cinematic|Natural|Pastel|Monochrome"
  },
  "environment": {
    "time": "Golden Hour|Midday|Night",
    "setting": "Interior|Exterior|Mixed",
    "weather": "string"
  },
  "narrative": {
    "faces": int,
    "vibe": ["Moody", "Nostalgic", "Gritty"],
    "alt_text": "Poetic 1-sentence description"
  }
}

CRITICAL: Identify 'semantic_pops' (small focal points like a red plane in a blue sky).
"""

# ---------------------------------------------------------------------------
# Image collection
# ---------------------------------------------------------------------------

client = None


def find_gemini_jpeg(image_uuid: str, category: str, subcategory: str) -> Optional[Path]:
    """Find the gemini-tier JPEG for analysis."""
    # Flat layout: rendered/gemini/jpeg/{uuid}.jpg
    path = IMAGE_DIR / f"{image_uuid}.jpg"
    if path.exists():
        return path
    # Legacy nested layout: rendered/gemini/jpeg/{category}/{subcategory}/{uuid}.jpg
    path = IMAGE_DIR / category / subcategory / f"{image_uuid}.jpg"
    if path.exists():
        return path
    return None


# ---------------------------------------------------------------------------
# Analysis with retry
# ---------------------------------------------------------------------------

async def analyze_photo(
    image_uuid: str,
    category: str,
    subcategory: str,
    semaphore: asyncio.Semaphore,
    conn,
    max_retries: int,
) -> bool:
    """Analyze a single photo with Gemini. Retries with exponential backoff."""
    jpeg_path = find_gemini_jpeg(image_uuid, category, subcategory)
    if not jpeg_path:
        print(f"  SKIP  {image_uuid[:8]}: no gemini JPEG found")
        return False

    short_id = image_uuid[:8]

    for attempt in range(1, max_retries + 1):
        async with semaphore:
            try:
                image_bytes = jpeg_path.read_bytes()

                response = await client.aio.models.generate_content(
                    model=MODEL_ID,
                    contents=[
                        SYSTEM_PROMPT,
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(include_thoughts=True),
                        temperature=0.1,
                    ),
                )

                metadata_text = response.text
                parsed = json.loads(metadata_text)

                db.upsert_analysis(
                    conn, image_uuid=image_uuid, model=MODEL_ID,
                    raw_json=metadata_text, parsed=parsed,
                )
                print(f"  OK  {short_id} ({category}/{subcategory})")
                return True

            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON (attempt {attempt}/{max_retries}): {e}"
                print(f"  RETRY  {short_id}: {error_msg}", file=sys.stderr)
                if attempt == max_retries:
                    db.upsert_analysis(
                        conn, image_uuid=image_uuid, model=MODEL_ID,
                        raw_json="", error=error_msg,
                    )
                    return False

            except Exception as e:
                error_msg = str(e)
                is_rate_limit = "429" in error_msg or "quota" in error_msg.lower() or "resource" in error_msg.lower()
                backoff = BASE_BACKOFF * (2 ** (attempt - 1))
                if is_rate_limit:
                    backoff = max(backoff, 30)

                print(f"  RETRY  {short_id} (attempt {attempt}/{max_retries}): {error_msg[:100]}", file=sys.stderr)

                if attempt == max_retries:
                    db.upsert_analysis(
                        conn, image_uuid=image_uuid, model=MODEL_ID,
                        raw_json="", error=error_msg,
                    )
                    return False

                print(f"    Backing off {backoff:.0f}s...")
                await asyncio.sleep(backoff)

    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    global client
    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)

    conn = db.get_connection()

    # Get all images from DB that haven't been analyzed
    unanalyzed = db.get_unanalyzed_uuids(conn)

    # We need category/subcategory for path lookup
    to_process = []
    for uuid_str in unanalyzed:
        row = conn.execute(
            "SELECT uuid, category, subcategory FROM images WHERE uuid = ?",
            (uuid_str,)).fetchone()
        if row:
            to_process.append(dict(row))

    if args.test:
        to_process = to_process[:args.test]

    total = conn.execute("SELECT COUNT(*) as c FROM images").fetchone()["c"]
    analyzed = conn.execute(
        "SELECT COUNT(*) as c FROM gemini_analysis WHERE raw_json IS NOT NULL AND raw_json != ''").fetchone()["c"]

    print(f"Total images: {total}")
    print(f"Already analyzed: {analyzed}")
    print(f"To analyze: {len(to_process)}")
    print(f"Concurrency: {args.concurrent} | Max retries: {args.max_retries}")
    print()

    if not to_process:
        print("Nothing to analyze. All images are up to date.")
        conn.close()
        return

    run_id = db.start_run(conn, "gemini_analysis", {
        "concurrent": args.concurrent, "max_retries": args.max_retries,
    })

    semaphore = asyncio.Semaphore(args.concurrent)
    tasks = [
        analyze_photo(
            img["uuid"], img["category"], img["subcategory"],
            semaphore, conn, args.max_retries,
        )
        for img in to_process
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    successes = sum(1 for r in results if r is True)
    failures = len(results) - successes

    db.finish_run(conn, run_id, images_processed=successes, images_failed=failures)
    conn.close()

    print(f"\nDone. Analyzed: {successes} | Failed: {failures}")
    if failures > 0:
        print("Re-run to retry failed images.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini photography analysis engine")
    parser.add_argument("--test", type=int, metavar="N", default=0,
                        help="Analyze only N images")
    parser.add_argument("--concurrent", type=int, default=MAX_CONCURRENT,
                        help=f"Max concurrent API calls (default: {MAX_CONCURRENT})")
    parser.add_argument("--max-retries", type=int, default=MAX_RETRIES,
                        help=f"Max retry attempts per image (default: {MAX_RETRIES})")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
