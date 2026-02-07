#!/usr/bin/env python3
"""
imagen_engine.py — Generate 5 AI-enhanced/transformed variants per image using Imagen 3.

Uses Vertex AI (required for edit_image) with the imagen-3.0-capability-001 model.
Processes images in batches to manage disk space. Each variant source JPEG is saved to
ai_variants/{variant_type}/{category}/{subcategory}/{variant_id}.jpg, then rendered
into tiers by render_pipeline.py.

Usage:
    python imagen_engine.py                               # Generate all variants
    python imagen_engine.py --variant light_enhance        # Only one variant type
    python imagen_engine.py --test 5                       # Only 5 images
    python imagen_engine.py --batch-size 100               # Custom batch size
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from google import genai
from google.genai import types

import database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = db.PROJECT_ROOT
AI_VARIANTS_DIR = PROJECT_ROOT / "images" / "ai_variants"
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"

# Imagen 3 edit_image requires Vertex AI
GCP_PROJECT = os.environ.get("GCP_PROJECT", "madbox-e4a35")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

IMAGEN_MODEL = "imagen-3.0-capability-001"
UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Rate limiting: Vertex AI default ~5 req/min for image generation
MAX_CONCURRENT = 1
MAX_RETRIES = 5
BASE_BACKOFF = 5.0  # seconds, doubles each retry
DELAY_BETWEEN_CALLS = 15.0  # seconds — ~4 req/min to stay within quota

# ---------------------------------------------------------------------------
# 5 Variant Configurations
# ---------------------------------------------------------------------------

VARIANT_CONFIGS = {
    "light_enhance": {
        "prompt": (
            "Enhance the natural lighting of this photograph. Improve shadow detail "
            "and highlight recovery. Add subtle warmth to light sources. Preserve all "
            "original composition, subjects, and colors. The result should look like "
            "a professionally post-processed version of the same photograph with "
            "natural, balanced, beautiful light."
        ),
        "negative_prompt": "oversaturated, HDR look, artificial, neon, unrealistic colors, blurry",
        "edit_mode": "EDIT_MODE_DEFAULT",
        "guidance_scale": 50,
    },
    "nano_feel": {
        "prompt": (
            "Apply a subtle organic analog film aesthetic to this photograph. Add fine "
            "film grain, slightly muted highlights, and gently lifted blacks. Introduce "
            "a delicate warm amber cast to midtones and a cool blue-green shift in "
            "shadows. The effect should feel authentic to Kodak Portra 400 or Fuji "
            "Pro 400H film stock. Preserve the original composition and subject matter. "
            "The result should feel organic, warm, and nostalgic."
        ),
        "negative_prompt": "digital look, oversaturated, harsh contrast, artificial, plastic",
        "edit_mode": "EDIT_MODE_STYLE",
        "guidance_scale": 60,
    },
    "cartoon": {
        "prompt": (
            "Transform this photograph into a vibrant cartoon illustration. Use bold "
            "black outlines around shapes and subjects. Simplify details into flat color "
            "regions with cel-shading. Make colors vivid and saturated. The style should "
            "resemble a high-quality animated film frame, like Studio Ghibli or Pixar "
            "concept art. Maintain the original composition and recognizable subjects."
        ),
        "negative_prompt": "photorealistic, dull colors, sketch, pencil, watercolor, blurry",
        "edit_mode": "EDIT_MODE_STYLE",
        "guidance_scale": 75,
    },
    "cinematic": {
        "prompt": (
            "Apply dramatic cinematic color grading to this photograph. Use a teal and "
            "orange complementary color palette in shadows and highlights. Add subtle "
            "film grain and slight vignetting. Enhance contrast for a moody, atmospheric "
            "look. The result should feel like a still from a Hollywood feature film "
            "graded by a professional colorist. Preserve all subjects and composition."
        ),
        "negative_prompt": "flat, washed out, oversaturated neon, cartoon, illustration, amateur",
        "edit_mode": "EDIT_MODE_STYLE",
        "guidance_scale": 65,
    },
    "dreamscape": {
        "prompt": (
            "Transform this photograph into an ethereal dreamscape. Soften edges with a "
            "gentle painterly quality. Shift the color palette toward luminous pastels "
            "with iridescent highlights and deep sapphire shadows. Add a subtle glow "
            "to light sources and a dreamy atmospheric haze. The result should feel like "
            "a surreal oil painting inspired by the photograph, balancing between reality "
            "and imagination. Maintain the original composition."
        ),
        "negative_prompt": "sharp digital photo, harsh, gritty, dark, horror, distorted",
        "edit_mode": "EDIT_MODE_STYLE",
        "guidance_scale": 70,
    },
}

ALL_VARIANT_TYPES = list(VARIANT_CONFIGS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_variant_id(image_uuid: str, variant_type: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:{variant_type}"))


def get_display_tier_path(image_uuid: str, category: str, subcategory: str) -> Optional[Path]:
    """Find the display-tier JPEG for an image (used as source for Imagen)."""
    # Flat structure: rendered/display/jpeg/{uuid}.jpg
    path = RENDERED_DIR / "display" / "jpeg" / f"{image_uuid}.jpg"
    if path.exists():
        return path
    # Fallback: check gemini tier
    path2 = RENDERED_DIR / "gemini" / "jpeg" / f"{image_uuid}.jpg"
    if path2.exists():
        return path2
    return None


# ---------------------------------------------------------------------------
# Imagen API call
# ---------------------------------------------------------------------------

async def generate_single_variant(
    client: genai.Client,
    image_uuid: str,
    source_path: Path,
    variant_type: str,
    category: str,
    subcategory: str,
    semaphore: asyncio.Semaphore,
    conn,
    max_retries: int = MAX_RETRIES,
) -> bool:
    """Generate one AI variant for one image. Retries with exponential backoff."""
    variant_id = generate_variant_id(image_uuid, variant_type)
    config = VARIANT_CONFIGS[variant_type]
    short_id = variant_id[:8]

    # Check if already done
    status = db.get_variant_status(conn, variant_id)
    if status in ("success", "filtered"):
        return True

    for attempt in range(1, max_retries + 1):
        async with semaphore:
            start_ms = int(time.time() * 1000)
            try:
                # Build reference image — load bytes eagerly
                source_bytes = source_path.read_bytes()
                raw_ref = types.RawReferenceImage(
                    reference_id=1,
                    reference_image=types.Image(
                        image_bytes=source_bytes,
                        mime_type="image/jpeg",
                    ),
                )

                # Build edit config
                edit_config = types.EditImageConfig(
                    edit_mode=config["edit_mode"],
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                    output_compression_quality=92,
                    person_generation="ALLOW_ALL",
                    safety_filter_level="BLOCK_LOW_AND_ABOVE",
                    include_rai_reason=True,
                )
                if config.get("negative_prompt"):
                    edit_config.negative_prompt = config["negative_prompt"]
                if config.get("guidance_scale"):
                    edit_config.guidance_scale = config["guidance_scale"]

                # Call Imagen
                response = await client.aio.models.edit_image(
                    model=IMAGEN_MODEL,
                    prompt=config["prompt"],
                    reference_images=[raw_ref],
                    config=edit_config,
                )

                elapsed_ms = int(time.time() * 1000) - start_ms

                # Check for safety filter
                if not response.generated_images:
                    rai = None
                    if hasattr(response, 'generated_images') and response.generated_images:
                        rai = getattr(response.generated_images[0], 'rai_reason', None)
                    db.upsert_variant(
                        conn, variant_id=variant_id, image_uuid=image_uuid,
                        variant_type=variant_type, model=IMAGEN_MODEL,
                        prompt=config["prompt"], negative_prompt=config.get("negative_prompt"),
                        edit_mode=config["edit_mode"],
                        guidance_scale=config.get("guidance_scale"),
                        source_tier="display", generation_status="filtered",
                        rai_reason=str(rai), generation_time_ms=elapsed_ms,
                    )
                    print(f"  FILTERED  {short_id} ({variant_type}) - safety filter")
                    return False  # Don't retry filtered images

                # Save the generated image
                out_dir = AI_VARIANTS_DIR / variant_type / category / subcategory
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{variant_id}.jpg"

                gen_image = response.generated_images[0].image
                if hasattr(gen_image, 'image_bytes') and gen_image.image_bytes:
                    out_path.write_bytes(gen_image.image_bytes)
                elif hasattr(gen_image, '_pil_image') and gen_image._pil_image:
                    gen_image._pil_image.save(str(out_path), format="JPEG", quality=92)
                else:
                    gen_image.save(str(out_path))

                db.upsert_variant(
                    conn, variant_id=variant_id, image_uuid=image_uuid,
                    variant_type=variant_type, model=IMAGEN_MODEL,
                    prompt=config["prompt"], negative_prompt=config.get("negative_prompt"),
                    edit_mode=config["edit_mode"],
                    guidance_scale=config.get("guidance_scale"),
                    source_tier="display", generation_status="success",
                    generation_time_ms=elapsed_ms,
                )
                print(f"  OK  {short_id} ({variant_type}) [{elapsed_ms}ms]")
                await asyncio.sleep(DELAY_BETWEEN_CALLS)
                return True

            except Exception as e:
                elapsed_ms = int(time.time() * 1000) - start_ms
                error_msg = str(e)
                is_rate_limit = "429" in error_msg or "quota" in error_msg.lower() or "resource" in error_msg.lower()
                backoff = BASE_BACKOFF * (2 ** (attempt - 1))
                if is_rate_limit:
                    backoff = max(backoff, 30)

                print(f"  RETRY  {short_id} ({variant_type}) attempt {attempt}/{max_retries}: {error_msg[:120]}",
                      file=sys.stderr)

                if attempt == max_retries:
                    db.upsert_variant(
                        conn, variant_id=variant_id, image_uuid=image_uuid,
                        variant_type=variant_type, model=IMAGEN_MODEL,
                        prompt=config["prompt"], negative_prompt=config.get("negative_prompt"),
                        edit_mode=config["edit_mode"],
                        guidance_scale=config.get("guidance_scale"),
                        source_tier="display", generation_status="failed",
                        error_message=error_msg, generation_time_ms=elapsed_ms,
                    )
                    return False

                print(f"    Backing off {backoff:.0f}s...")
                await asyncio.sleep(backoff)


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

async def process_batch(
    client: genai.Client,
    images: list,
    variant_types: list,
    conn,
    concurrent: int,
    max_retries: int = MAX_RETRIES,
) -> "tuple[int, int]":
    """Process a batch of images for given variant types. Returns (success, fail) counts."""
    semaphore = asyncio.Semaphore(concurrent)
    tasks = []

    for img in images:
        source_path = get_display_tier_path(
            img["uuid"], img["category"], img["subcategory"])
        if not source_path:
            print(f"  SKIP  {img['uuid'][:8]}: no display tier found")
            continue

        for vtype in variant_types:
            tasks.append(generate_single_variant(
                client, img["uuid"], source_path, vtype,
                img["category"], img["subcategory"],
                semaphore, conn, max_retries,
            ))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    successes = sum(1 for r in results if r is True)
    failures = len(results) - successes
    return successes, failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    # Initialize Vertex AI client
    print(f"Initializing Vertex AI client (project={GCP_PROJECT}, location={GCP_LOCATION})")
    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)

    conn = db.get_connection()

    # Determine which variant types to generate
    if args.variant and args.variant != "all":
        if args.variant not in VARIANT_CONFIGS:
            print(f"Unknown variant type: {args.variant}")
            print(f"Available: {', '.join(ALL_VARIANT_TYPES)}")
            sys.exit(1)
        variant_types = [args.variant]
    else:
        variant_types = ALL_VARIANT_TYPES

    # Collect images that need processing
    all_images = []
    for vtype in variant_types:
        needed = db.get_ungenerated_variants(conn, vtype, kept_only=args.kept_only)
        for img in needed:
            if img not in all_images:
                all_images.append(img)

    if args.test:
        all_images = all_images[:args.test]

    total_variants = len(all_images) * len(variant_types)
    print(f"Images: {len(all_images)} | Variant types: {', '.join(variant_types)}")
    print(f"Total API calls needed: {total_variants}")
    print(f"Batch size: {args.batch_size} | Concurrency: {args.concurrent}")
    print()

    if not all_images:
        print("Nothing to generate. All variants are up to date.")
        conn.close()
        return

    run_id = db.start_run(conn, "imagen_variants", {
        "variant_types": variant_types, "batch_size": args.batch_size,
        "concurrent": args.concurrent, "test": args.test,
    })

    total_success = 0
    total_fail = 0

    # Process in batches
    batch_num = 0
    for i in range(0, len(all_images), args.batch_size):
        batch = all_images[i:i + args.batch_size]
        batch_num += 1
        print(f"--- Batch {batch_num} ({len(batch)} images) ---")

        success, fail = await process_batch(
            client, batch, variant_types, conn, args.concurrent, args.max_retries)
        total_success += success
        total_fail += fail

        print(f"Batch {batch_num} done: {success} OK, {fail} failed")

    db.finish_run(conn, run_id, images_processed=total_success, images_failed=total_fail)
    conn.close()

    print(f"\nAll done. Generated: {total_success} | Failed: {total_fail}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Imagen 3 AI variant generator")
    parser.add_argument("--variant", type=str, default="all",
                        help=f"Variant type to generate: all, {', '.join(ALL_VARIANT_TYPES)}")
    parser.add_argument("--test", type=int, metavar="N", default=0,
                        help="Process only N images")
    parser.add_argument("--batch-size", type=int, default=200,
                        help="Images per batch (default: 200)")
    parser.add_argument("--concurrent", type=int, default=MAX_CONCURRENT,
                        help=f"Max concurrent API calls (default: {MAX_CONCURRENT})")
    parser.add_argument("--max-retries", type=int, default=MAX_RETRIES,
                        help=f"Max retries per variant (default: {MAX_RETRIES})")
    parser.add_argument("--kept-only", action="store_true",
                        help="Only process images with curated_status='kept'")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
