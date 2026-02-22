#!/usr/bin/env python3
"""Generate cartoon/illustration style transfers using Imagen 3 EDIT_MODE_STYLE.

Reads style_prompts_test.json (from Gemma) and applies each style via
Google Imagen 3 edit_image API. Writes results to the ai_variants DB table.

POLLING MODE: Re-reads prompts file each cycle, so it can run alongside
Gemma and process new images as prompts become available.

Usage (run from MADphotos root with .venv-gen activated):
  .venv-gen/bin/python3 backend/generate_test_images.py
  .venv-gen/bin/python3 backend/generate_test_images.py --test 10
  .venv-gen/bin/python3 backend/generate_test_images.py --no-poll   # single pass, no waiting
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = PROJECT_ROOT / "backend" / "suggest_image_variant" / "style_prompts_test.json"
OUTPUT_ROOT = PROJECT_ROOT / "backend" / "suggest_image_variant" / "output"
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
AI_VARIANTS_DIR = PROJECT_ROOT / "images" / "ai_variants"

GCP_PROJECT = os.environ.get("GCP_PROJECT", "laeh380to760")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
IMAGEN_MODEL = "imagen-3.0-capability-001"

UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Rate limiting
DELAY_BETWEEN_CALLS = 6.0
MAX_RETRIES = 4
BASE_BACKOFF = 10.0
POLL_INTERVAL = 30  # seconds between checking for new prompts


def variant_id_for(image_uuid: str, style_idx: int, style_name: str) -> str:
    """Deterministic variant ID from image + style."""
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:style_{style_idx}_{style_name}"))


def db_upsert(conn: sqlite3.Connection, variant_id: str, image_uuid: str,
              prompt: str, status: str, elapsed_ms: int = 0,
              rai_reason: str | None = None, error: str | None = None) -> None:
    """Insert or update ai_variants row."""
    conn.execute("""
        INSERT INTO ai_variants (
            variant_id, image_uuid, variant_type, model, prompt,
            negative_prompt, edit_mode, guidance_scale, source_tier,
            generation_status, rai_reason, error_message,
            generation_time_ms, created_at
        ) VALUES (?, ?, 'style_transfer', ?, ?, ?, 'EDIT_MODE_STYLE', 75, 'mobile',
                  ?, ?, ?, ?, ?)
        ON CONFLICT(variant_id) DO UPDATE SET
            generation_status=excluded.generation_status,
            rai_reason=excluded.rai_reason,
            error_message=excluded.error_message,
            generation_time_ms=excluded.generation_time_ms
    """, (
        variant_id, image_uuid, IMAGEN_MODEL, prompt,
        "photorealistic, dull colors, blurry, low quality",
        status, rai_reason, error, elapsed_ms,
        datetime.now(timezone.utc).isoformat(),
    ))
    conn.commit()


def generate_imagen(client: genai.Client, prompt: str, source_image: str,
                    output_path: Path) -> tuple[bool, str | None]:
    """Style transfer using Imagen 3 EDIT_MODE_STYLE. Returns (ok, error)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    full_prompt = (
        f"Transform this photograph into the following artistic style, "
        f"preserving the exact composition, subjects, and layout. "
        f"No text or lettering. Style: {prompt}"
    )

    source_bytes = Path(source_image).read_bytes()
    raw_ref = types.RawReferenceImage(
        reference_id=1,
        reference_image=types.Image(
            image_bytes=source_bytes,
            mime_type="image/jpeg",
        ),
    )

    edit_config = types.EditImageConfig(
        edit_mode="EDIT_MODE_STYLE",
        number_of_images=1,
        output_mime_type="image/jpeg",
        output_compression_quality=92,
        person_generation="ALLOW_ALL",
        safety_filter_level="BLOCK_LOW_AND_ABOVE",
        guidance_scale=75,
        include_rai_reason=True,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.edit_image(
                model=IMAGEN_MODEL,
                prompt=full_prompt,
                reference_images=[raw_ref],
                config=edit_config,
            )

            if not response.generated_images:
                return False, "safety_filter"

            gen_image = response.generated_images[0].image
            if hasattr(gen_image, 'image_bytes') and gen_image.image_bytes:
                output_path.write_bytes(gen_image.image_bytes)
            elif hasattr(gen_image, '_pil_image') and gen_image._pil_image:
                gen_image._pil_image.save(str(output_path), format="JPEG", quality=92)
            else:
                gen_image.save(str(output_path))

            return output_path.exists(), None

        except Exception as e:
            err = str(e)
            is_rate_limit = "429" in err or "quota" in err.lower() or "resource" in err.lower()
            backoff = BASE_BACKOFF * (2 ** (attempt - 1))
            if is_rate_limit:
                backoff = max(backoff, 30)

            if attempt == MAX_RETRIES:
                return False, err[:200]

            print(f"    retry {attempt}/{MAX_RETRIES} — waiting {backoff:.0f}s")
            time.sleep(backoff)

    return False, "max retries"


def copy_original(src_path: str, dest_dir: Path) -> None:
    """Copy original photo into the experiment folder for comparison."""
    dest = dest_dir / "original.jpg"
    if not dest.exists() and Path(src_path).exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest)


def process_image(client: genai.Client, conn: sqlite3.Connection,
                  img_data: dict, run_dir: Path) -> tuple[int, int]:
    """Process one image's styles. Returns (ok_count, fail_count)."""
    uid = img_data["uuid"]
    src_path = img_data["path"]
    styles = img_data["result"].get("styles", [])
    analysis = img_data["result"].get("analysis", "")

    img_dir = run_dir / uid
    copy_original(src_path, img_dir)

    print(f"\n{'='*60}")
    print(f"Image: {uid}")
    print(f"  {analysis}")
    print(f"  {len(styles)} styles\n")

    ok = 0
    fail = 0

    for j, style in enumerate(styles):
        style_name = style.get("name", f"style_{j}")
        prompt = style.get("style_prompt", style.get("prompt", ""))
        safe_name = style_name.lower().replace(" ", "_").replace("/", "-")[:40]
        vid = variant_id_for(uid, j, safe_name)

        # Check DB — already done?
        row = conn.execute(
            "SELECT generation_status FROM ai_variants WHERE variant_id=?", (vid,)
        ).fetchone()
        if row and row[0] in ("success", "filtered"):
            print(f"  [{j+1}/{len(styles)}] {style_name} — already in DB, skip")
            ok += 1
            continue

        out_path = img_dir / f"imagen_{j}_{safe_name}.jpg"
        if out_path.exists():
            print(f"  [{j+1}/{len(styles)}] {style_name} — file exists, skip")
            ok += 1
            continue

        print(f"  [{j+1}/{len(styles)}] {style_name}")
        print(f"    {prompt[:90]}...")

        t1 = time.time()
        success, error = generate_imagen(client, prompt, src_path, out_path)
        elapsed_ms = int((time.time() - t1) * 1000)

        if success:
            ok += 1
            db_upsert(conn, vid, uid, prompt, "success", elapsed_ms)
            print(f"    OK ({elapsed_ms/1000:.1f}s)")
        elif error == "safety_filter":
            fail += 1
            db_upsert(conn, vid, uid, prompt, "filtered", elapsed_ms, rai_reason="safety")
            print(f"    FILTERED (safety)")
        else:
            fail += 1
            db_upsert(conn, vid, uid, prompt, "failed", elapsed_ms, error=error)
            print(f"    FAILED: {error}")

        # Rate limit
        wait = max(0, DELAY_BETWEEN_CALLS - (time.time() - t1))
        if wait > 0:
            time.sleep(wait)

    return ok, fail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=int, default=0, help="Only process N images")
    parser.add_argument("--no-poll", action="store_true", help="Single pass, don't wait for new prompts")
    parser.add_argument("--run-dir", type=str, default=None, help="Reuse existing run directory")
    args = parser.parse_args()

    # Timestamped output folder
    if args.run_dir:
        run_dir = Path(args.run_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = OUTPUT_ROOT / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Imagen 3 Style Transfer — EDIT_MODE_STYLE, guidance=75")
    print(f"Model: {IMAGEN_MODEL}")
    print(f"Experiment: {run_dir}")
    print(f"Polling: {'OFF' if args.no_poll else f'every {POLL_INTERVAL}s'}")
    print()

    # Init
    print(f"Initializing Vertex AI client (project={GCP_PROJECT})")
    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    conn = sqlite3.connect(str(DB_PATH))

    processed_uuids: set[str] = set()
    total_ok = 0
    total_fail = 0
    t0 = time.time()

    while True:
        # Re-read prompts file each cycle
        if not PROMPTS_FILE.exists():
            if args.no_poll:
                print("No prompts file found.")
                break
            print(f"Waiting for prompts file...")
            time.sleep(POLL_INTERVAL)
            continue

        prompts_data = json.loads(PROMPTS_FILE.read_text())
        if args.test:
            prompts_data = prompts_data[:args.test]

        # Find new (unprocessed) images
        new_items = [d for d in prompts_data if d["uuid"] not in processed_uuids
                     and "styles" in d.get("result", {})]

        if new_items:
            print(f"\n>>> {len(new_items)} new images to process "
                  f"({len(processed_uuids)} already done, "
                  f"{len(prompts_data)} total in file)")

            # Update experiment prompts.json
            prompts_copy = run_dir / "prompts.json"
            prompts_copy.write_text(json.dumps(prompts_data, indent=2))

            for img_data in new_items:
                ok, fail = process_image(client, conn, img_data, run_dir)
                total_ok += ok
                total_fail += fail
                processed_uuids.add(img_data["uuid"])

        if args.no_poll:
            break

        # Check if Gemma is still running
        if len(processed_uuids) >= (args.test or 100):
            print(f"\nAll {len(processed_uuids)} images processed.")
            break

        if not new_items:
            print(f"  [{len(processed_uuids)}/{args.test or 100}] Waiting for Gemma... ({POLL_INTERVAL}s)")
        time.sleep(POLL_INTERVAL)

    conn.close()
    elapsed = time.time() - t0
    total_images = len(list(run_dir.glob("*/imagen_*.jpg")))
    print(f"\nDone! {elapsed/60:.1f} min — {total_ok} OK, {total_fail} failed, {total_images} images on disk")
    print(f"Experiment: {run_dir}")


if __name__ == "__main__":
    main()
