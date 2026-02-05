#!/usr/bin/env python3
"""
render_pipeline.py — Renders image pyramids from originals or AI variant sources.

Usage:
    python render_pipeline.py                          # Render all originals (6 tiers)
    python render_pipeline.py --test 10                # Only first 10 images
    python render_pipeline.py --source ai_variants \\
        --variant-type cartoon --tiers variant         # Render AI variant tiers (4 tiers)
    python render_pipeline.py --workers 8              # Override worker count
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter, ImageOps

import mad_database as db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
ORIGINALS_DIR = BASE_DIR / "originals"
RENDERED_DIR = BASE_DIR / "rendered"
AI_VARIANTS_DIR = BASE_DIR / "ai_variants"
MANIFEST_PATH = RENDERED_DIR / "manifest.json"

IMAGE_EXTENSIONS = {".dng", ".raw", ".jpg", ".jpeg", ".png"}
RAW_EXTENSIONS = {".dng", ".raw"}

UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


@dataclass
class TierConfig:
    name: str
    long_edge: int
    jpeg_quality: int
    webp_quality: Optional[int]
    progressive: bool
    subsampling: int
    sharpen: Optional[tuple]


# 6 tiers for originals
ORIGINAL_TIERS = [
    TierConfig("full",    3840, 92, None, True,  0, (0.5, 30, 2)),
    TierConfig("display", 2048, 88, 82,   True,  1, (0.5, 40, 2)),
    TierConfig("mobile",  1280, 85, 80,   True,  1, (0.4, 50, 2)),
    TierConfig("thumb",    480, 82, 78,   False, 2, (0.3, 60, 2)),
    TierConfig("micro",     64, 70, 68,   False, 2, None),
    TierConfig("gemini",  2048, 90, None, False, 1, (0.5, 35, 2)),
]

# 4 tiers for AI variants (no full@3840 since Imagen outputs ~1024px, no gemini)
VARIANT_TIERS = [
    TierConfig("display", 1024, 88, 82,   True,  1, (0.5, 40, 2)),
    TierConfig("mobile",   768, 85, 80,   True,  1, (0.4, 50, 2)),
    TierConfig("thumb",    480, 82, 78,   False, 2, (0.3, 60, 2)),
    TierConfig("micro",     64, 70, 68,   False, 2, None),
]

MAX_ERROR_ATTEMPTS = 3

# Module-level state set by main() for multiprocessing workers
_WORKER_OUTPUT_DIR = None
_WORKER_TIERS = None
_WORKER_SOURCE = None
_WORKER_VARIANT_TYPE = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_uuid(relative_path: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, relative_path))


def generate_variant_id(image_uuid: str, variant_type: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:{variant_type}"))


def collect_originals() -> "list[tuple[str, Path]]":
    """Walk originals/ and return (relative_path, absolute_path) for every image."""
    images = []
    for root, _dirs, files in os.walk(ORIGINALS_DIR):
        for fname in files:
            if Path(fname).suffix.lower() in IMAGE_EXTENSIONS:
                abs_path = Path(root) / fname
                rel_path = abs_path.relative_to(ORIGINALS_DIR).as_posix()
                images.append((rel_path, abs_path))
    images.sort(key=lambda x: x[0])
    return images


def collect_variant_sources(variant_type: str) -> "list[tuple[str, Path, str]]":
    """Collect AI variant source JPEGs. Returns (image_uuid, abs_path, variant_id)."""
    variant_dir = AI_VARIANTS_DIR / variant_type
    if not variant_dir.exists():
        return []
    images = []
    for root, _dirs, files in os.walk(variant_dir):
        for fname in files:
            if fname.lower().endswith((".jpg", ".jpeg", ".png")):
                abs_path = Path(root) / fname
                # The filename IS the variant_id (stem)
                variant_id = Path(fname).stem
                # Look up the image_uuid from the variant_id via filename convention
                # variant files are at: ai_variants/{type}/{cat}/{sub}/{variant_id}.jpg
                images.append((variant_id, abs_path))
    images.sort(key=lambda x: x[0])
    return images


def parse_category(relative_path: str) -> "tuple[str, str]":
    parts = Path(relative_path).parts
    category = parts[0] if len(parts) > 1 else "Uncategorized"
    subcategory = parts[1] if len(parts) > 2 else "General"
    return category, subcategory


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    return {"version": 1, "images": {}, "errors": {}}


def save_manifest(manifest: dict) -> None:
    RENDERED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=2)
    tmp.replace(MANIFEST_PATH)


def decode_image(abs_path: Path) -> Image.Image:
    ext = abs_path.suffix.lower()
    if ext in RAW_EXTENSIONS:
        import rawpy
        raw = rawpy.imread(str(abs_path))
        rgb = raw.postprocess(
            use_camera_wb=True,
            half_size=False,
            no_auto_bright=True,
            output_bps=8,
            output_color=rawpy.ColorSpace.sRGB,
            dcb_enhance=False,
            fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
        )
        raw.close()
        img = Image.fromarray(rgb)
        try:
            with Image.open(abs_path) as probe:
                exif_orientation = probe.getexif().get(0x0112, 1)
            img = _apply_orientation(img, exif_orientation)
        except Exception:
            pass
        return img
    else:
        img = Image.open(abs_path)
        img = ImageOps.exif_transpose(img)
        img.load()
        return img.convert("RGB")


def _apply_orientation(img: Image.Image, orientation: int) -> Image.Image:
    ops = {
        2: [Image.FLIP_LEFT_RIGHT],
        3: [Image.ROTATE_180],
        4: [Image.FLIP_TOP_BOTTOM],
        5: [Image.FLIP_LEFT_RIGHT, Image.ROTATE_90],
        6: [Image.ROTATE_270],
        7: [Image.FLIP_LEFT_RIGHT, Image.ROTATE_270],
        8: [Image.ROTATE_90],
    }
    for op in ops.get(orientation, []):
        img = img.transpose(op)
    return img


def render_tier(img: Image.Image, tier: TierConfig, out_dir: Path,
                category: str, subcategory: str, file_id: str) -> "list[dict]":
    """Render one tier. Returns list of dicts with path/size info for each output file."""
    w, h = img.size
    long_edge = max(w, h)

    if long_edge > tier.long_edge:
        ratio = tier.long_edge / long_edge
        new_size = (int(w * ratio), int(h * ratio))
        tier_img = img.resize(new_size, Image.LANCZOS)
    else:
        tier_img = img.copy()

    if tier.sharpen:
        tier_img = tier_img.filter(ImageFilter.UnsharpMask(*tier.sharpen))

    tw, th = tier_img.size
    outputs = []

    # JPEG
    jpeg_dir = out_dir / tier.name / "jpeg" / category / subcategory
    jpeg_dir.mkdir(parents=True, exist_ok=True)
    jpeg_path = jpeg_dir / f"{file_id}.jpg"
    tier_img.save(jpeg_path, format="JPEG", quality=tier.jpeg_quality,
                  optimize=True, progressive=tier.progressive,
                  subsampling=tier.subsampling)
    outputs.append({
        "tier": tier.name, "format": "jpeg",
        "path": str(jpeg_path), "width": tw, "height": th,
        "size": jpeg_path.stat().st_size,
    })

    # WebP
    if tier.webp_quality is not None:
        webp_dir = out_dir / tier.name / "webp" / category / subcategory
        webp_dir.mkdir(parents=True, exist_ok=True)
        webp_path = webp_dir / f"{file_id}.webp"
        tier_img.save(webp_path, format="WEBP", quality=tier.webp_quality,
                      method=4, exact=False)
        outputs.append({
            "tier": tier.name, "format": "webp",
            "path": str(webp_path), "width": tw, "height": th,
            "size": webp_path.stat().st_size,
        })

    return outputs


# ---------------------------------------------------------------------------
# Worker functions (called by multiprocessing.Pool)
# ---------------------------------------------------------------------------

def _init_worker(output_dir, tiers, source, variant_type):
    global _WORKER_OUTPUT_DIR, _WORKER_TIERS, _WORKER_SOURCE, _WORKER_VARIANT_TYPE
    _WORKER_OUTPUT_DIR = Path(output_dir)
    _WORKER_TIERS = tiers
    _WORKER_SOURCE = source
    _WORKER_VARIANT_TYPE = variant_type


def process_original(args: tuple) -> Optional[dict]:
    """Worker: decode one original image and render all tiers."""
    relative_path, abs_path_str = args
    abs_path = Path(abs_path_str)
    image_uuid = generate_uuid(relative_path)
    category, subcategory = parse_category(relative_path)

    try:
        img = decode_image(abs_path)
        w, h = img.size
        original_size = abs_path.stat().st_size

        all_outputs = []
        for tier in _WORKER_TIERS:
            outputs = render_tier(img, tier, _WORKER_OUTPUT_DIR,
                                  category, subcategory, image_uuid)
            all_outputs.extend(outputs)

        entry = {
            "uuid": image_uuid,
            "original_path": relative_path,
            "filename": Path(relative_path).name,
            "category": category,
            "subcategory": subcategory,
            "source_format": abs_path.suffix.lstrip(".").lower(),
            "width": w,
            "height": h,
            "original_size_bytes": original_size,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "tier_outputs": all_outputs,
        }
        print(f"  OK  {relative_path} -> {image_uuid[:8]}")
        return entry

    except Exception as e:
        print(f"  FAIL  {relative_path}: {e}", file=sys.stderr)
        return {"_error": True, "path": relative_path, "uuid": image_uuid, "error": str(e)}


def process_variant(args: tuple) -> Optional[dict]:
    """Worker: render tiers for one AI variant source JPEG."""
    variant_id, abs_path_str, image_uuid, category, subcategory = args
    abs_path = Path(abs_path_str)

    try:
        img = Image.open(abs_path)
        img.load()
        img = img.convert("RGB")
        w, h = img.size

        all_outputs = []
        for tier in _WORKER_TIERS:
            outputs = render_tier(img, tier, _WORKER_OUTPUT_DIR,
                                  category, subcategory, variant_id)
            all_outputs.extend(outputs)

        entry = {
            "variant_id": variant_id,
            "image_uuid": image_uuid,
            "variant_type": _WORKER_VARIANT_TYPE,
            "category": category,
            "subcategory": subcategory,
            "width": w,
            "height": h,
            "tier_outputs": all_outputs,
        }
        print(f"  OK  variant {variant_id[:8]} ({_WORKER_VARIANT_TYPE})")
        return entry

    except Exception as e:
        print(f"  FAIL  variant {variant_id[:8]}: {e}", file=sys.stderr)
        return {"_error": True, "variant_id": variant_id, "error": str(e)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Render image pyramid")
    parser.add_argument("--source", choices=["originals", "ai_variants"], default="originals",
                        help="What to render: originals or ai_variants")
    parser.add_argument("--variant-type", type=str, default=None,
                        help="Which AI variant type to render (required if --source ai_variants)")
    parser.add_argument("--tiers", choices=["original", "variant"], default=None,
                        help="Tier set: 'original' (6 tiers) or 'variant' (4 tiers). Auto-detected from --source.")
    parser.add_argument("--test", type=int, metavar="N", default=0,
                        help="Process only N images")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2),
                        help="Parallel workers (default: cpu_count - 2)")
    args = parser.parse_args()

    # Determine tier set and output directory
    if args.source == "ai_variants":
        if not args.variant_type:
            parser.error("--variant-type is required when --source is ai_variants")
        tiers = VARIANT_TIERS
        output_dir = RENDERED_DIR / "ai_variants" / args.variant_type
    else:
        tiers = ORIGINAL_TIERS
        output_dir = RENDERED_DIR / "originals"

    if args.tiers == "variant":
        tiers = VARIANT_TIERS
    elif args.tiers == "original":
        tiers = ORIGINAL_TIERS

    conn = db.get_connection()

    if args.source == "originals":
        _render_originals(args, tiers, output_dir, conn)
    else:
        _render_variants(args, tiers, output_dir, conn)

    conn.close()


def _render_originals(args, tiers, output_dir, conn):
    print(f"Scanning {ORIGINALS_DIR} ...")
    all_images = collect_originals()
    print(f"Found {len(all_images)} images")

    # Resume: skip already-processed (check DB + manifest for backward compat)
    manifest = load_manifest()
    done_in_db = db.get_all_image_uuids(conn)
    done_in_manifest = set(manifest["images"].keys())
    already_done = done_in_db | done_in_manifest

    to_process = []
    for rel_path, abs_path in all_images:
        img_uuid = generate_uuid(rel_path)
        if img_uuid not in already_done:
            err_info = manifest["errors"].get(img_uuid, {})
            if err_info.get("attempts", 0) >= MAX_ERROR_ATTEMPTS:
                continue
            to_process.append((rel_path, str(abs_path)))

    if args.test:
        to_process = to_process[:args.test]

    print(f"Already processed: {len(already_done)} | To process: {len(to_process)} | Workers: {args.workers}")

    if not to_process:
        print("Nothing to process. All images are up to date.")
        return

    # Graceful shutdown
    shutdown_requested = False
    original_sigint = signal.getsignal(signal.SIGINT)

    def handle_sigint(signum, frame):
        nonlocal shutdown_requested
        if shutdown_requested:
            print("\nForce quit.")
            sys.exit(1)
        shutdown_requested = True
        print("\nShutting down gracefully... (press Ctrl-C again to force)")

    signal.signal(signal.SIGINT, handle_sigint)

    run_id = db.start_run(conn, "render_originals", {"workers": args.workers, "test": args.test})
    start_time = datetime.now()
    completed = 0
    errors = 0

    try:
        with Pool(processes=args.workers,
                  initializer=_init_worker,
                  initargs=(str(output_dir), tiers, "originals", None)) as pool:
            for result in pool.imap_unordered(process_original, to_process):
                if shutdown_requested:
                    pool.terminate()
                    break

                if result is None:
                    errors += 1
                    continue

                if result.get("_error"):
                    img_uuid = result["uuid"]
                    err_entry = manifest["errors"].get(img_uuid, {"attempts": 0, "errors": []})
                    err_entry["attempts"] += 1
                    err_entry["errors"].append(result["error"])
                    err_entry["path"] = result["path"]
                    manifest["errors"][img_uuid] = err_entry
                    errors += 1
                else:
                    # Write to manifest (backward compat)
                    manifest["images"][result["uuid"]] = {
                        k: v for k, v in result.items() if k != "tier_outputs"
                    }
                    manifest["images"][result["uuid"]]["tiers"] = [t.name for t in tiers]

                    # Write to database
                    db.upsert_image(
                        conn, uuid=result["uuid"],
                        original_path=result["original_path"],
                        filename=result["filename"],
                        category=result["category"],
                        subcategory=result["subcategory"],
                        source_format=result["source_format"],
                        width=result["width"], height=result["height"],
                        original_size_bytes=result.get("original_size_bytes"),
                    )
                    for out in result.get("tier_outputs", []):
                        db.upsert_tier(
                            conn, image_uuid=result["uuid"],
                            tier_name=out["tier"], fmt=out["format"],
                            local_path=out["path"],
                            width=out["width"], height=out["height"],
                            file_size_bytes=out["size"],
                        )
                    conn.commit()
                    completed += 1

                if (completed + errors) % 50 == 0:
                    save_manifest(manifest)

    finally:
        save_manifest(manifest)
        db.finish_run(conn, run_id, images_processed=completed, images_failed=errors)
        signal.signal(signal.SIGINT, original_sigint)

    elapsed = datetime.now() - start_time
    print(f"\nDone in {elapsed}. Completed: {completed} | Errors: {errors}")
    print(f"  DB images: {len(db.get_all_image_uuids(conn))}")
    print(f"  Manifest: {MANIFEST_PATH}")


def _render_variants(args, tiers, output_dir, conn):
    variant_type = args.variant_type
    print(f"Rendering tiers for AI variant: {variant_type}")

    # Collect variant source files from ai_variants/{type}/{cat}/{sub}/{variant_id}.jpg
    variant_dir = AI_VARIANTS_DIR / variant_type
    if not variant_dir.exists():
        print(f"No variant sources found at {variant_dir}")
        return

    # Build work items: we need image_uuid + category/subcategory for each variant
    to_process = []
    for root, _dirs, files in os.walk(variant_dir):
        for fname in files:
            if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            abs_path = Path(root) / fname
            variant_id = Path(fname).stem
            # Get the relative path within the variant dir to extract category/subcategory
            rel = abs_path.relative_to(variant_dir).as_posix()
            parts = Path(rel).parts
            category = parts[0] if len(parts) > 2 else "Uncategorized"
            subcategory = parts[1] if len(parts) > 2 else "General"

            # Look up the image_uuid from ai_variants table
            row = conn.execute(
                "SELECT image_uuid FROM ai_variants WHERE variant_id = ?",
                (variant_id,)).fetchone()
            if not row:
                continue
            image_uuid = row["image_uuid"]

            # Skip if tiers already exist
            existing = db.get_image_tiers_count(conn, image_uuid, variant_id=variant_id)
            expected = sum(1 + (1 if t.webp_quality is not None else 0) for t in tiers)
            if existing >= expected:
                continue

            to_process.append((variant_id, str(abs_path), image_uuid, category, subcategory))

    if args.test:
        to_process = to_process[:args.test]

    print(f"Variants to render: {len(to_process)} | Workers: {args.workers}")

    if not to_process:
        print("Nothing to render.")
        return

    run_id = db.start_run(conn, f"render_variant_{variant_type}",
                          {"workers": args.workers, "variant_type": variant_type})
    start_time = datetime.now()
    completed = 0
    errors = 0

    with Pool(processes=args.workers,
              initializer=_init_worker,
              initargs=(str(output_dir), tiers, "ai_variants", variant_type)) as pool:
        for result in pool.imap_unordered(process_variant, to_process):
            if result is None or result.get("_error"):
                errors += 1
                continue

            for out in result.get("tier_outputs", []):
                db.upsert_tier(
                    conn, image_uuid=result["image_uuid"],
                    variant_id=result["variant_id"],
                    tier_name=out["tier"], fmt=out["format"],
                    local_path=out["path"],
                    width=out["width"], height=out["height"],
                    file_size_bytes=out["size"],
                )
            conn.commit()
            completed += 1

    db.finish_run(conn, run_id, images_processed=completed, images_failed=errors)
    elapsed = datetime.now() - start_time
    print(f"\nDone in {elapsed}. Rendered: {completed} | Errors: {errors}")


if __name__ == "__main__":
    main()
