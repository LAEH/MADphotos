#!/usr/bin/env python3
"""Generate style-transferred images using mflux img2img (local) and Google Imagen (API).

Reads style_prompts_test.json and applies each style to the ORIGINAL photo.
Output has the EXACT same dimensions and aspect ratio as the source image.
Only the artistic style changes — composition, layout, subjects all preserved.

Each run creates a timestamped folder: backend/generated_test/YYYYMMDD_HHMMSS/

Usage (run from MADphotos root with .venv-gen activated):
  .venv-gen/bin/python3 backend/generate_test_images.py
  .venv-gen/bin/python3 backend/generate_test_images.py --engine mflux
  .venv-gen/bin/python3 backend/generate_test_images.py --engine imagen
  .venv-gen/bin/python3 backend/generate_test_images.py --engine both
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = PROJECT_ROOT / "backend" / "style_prompts_test.json"
OUTPUT_ROOT = PROJECT_ROOT / "backend" / "generated_test"
MFLUX_BIN = PROJECT_ROOT / ".venv-gen" / "bin" / "mflux-generate"

MFLUX_MODEL = "dev"


def get_image_dimensions(image_path: str) -> tuple[int, int]:
    """Read exact width and height from source image."""
    with Image.open(image_path) as img:
        return img.width, img.height


def round_to_multiple(n: int, multiple: int = 64) -> int:
    """Round to nearest multiple (mflux requires dimensions divisible by certain values)."""
    return max(multiple, round(n / multiple) * multiple)


def generate_mflux(prompt: str, source_image: str, output_path: Path,
                   strength: float = 0.5, width: int = 768, height: int = 768) -> bool:
    """Style transfer using mflux img2img — same dimensions as source."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # mflux needs dimensions as multiples of 64
    w = round_to_multiple(width, 64)
    h = round_to_multiple(height, 64)

    cmd = [
        str(MFLUX_BIN),
        "--model", MFLUX_MODEL,
        "--quantize", "4",
        "--prompt", prompt,
        "--image-path", source_image,
        "--image-strength", str(strength),
        "--width", str(w),
        "--height", str(h),
        "--steps", "20",
        "--output", str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"    mflux error: {result.stderr[:300]}")
            return False
        # If mflux rounded dimensions, resize output to exact source size
        if output_path.exists() and (w != width or h != height):
            with Image.open(output_path) as img:
                img.resize((width, height), Image.LANCZOS).save(output_path)
        return output_path.exists()
    except subprocess.TimeoutExpired:
        print("    mflux timeout (300s)")
        return False


# Imagen state
_imagen_model = None
_imagen_last_call = 0.0
IMAGEN_MIN_INTERVAL = 6.0


def generate_imagen(prompt: str, source_image: str, output_path: Path,
                    strength: float = 0.5) -> bool:
    """Style transfer using Google Imagen edit mode — preserves source dimensions."""
    global _imagen_model, _imagen_last_call

    try:
        if _imagen_model is None:
            import vertexai
            from vertexai.preview.vision_models import ImageGenerationModel
            vertexai.init(project="laeh380to760", location="us-central1")
            _imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")

        elapsed_since_last = time.time() - _imagen_last_call
        if elapsed_since_last < IMAGEN_MIN_INTERVAL:
            time.sleep(IMAGEN_MIN_INTERVAL - elapsed_since_last)

        full_prompt = (
            f"Transform this photograph into the following artistic style, "
            f"preserving the exact composition, subjects, and layout. "
            f"No text or lettering. Style: {prompt}"
        )

        _imagen_last_call = time.time()
        from vertexai.preview.vision_models import Image as VertexImage
        source = VertexImage.load_from_file(source_image)

        response = _imagen_model.edit_images(
            base_image=source,
            prompt=full_prompt,
            number_of_images=1,
            safety_filter_level="block_few",
            person_generation="allow_adult",
        )

        if response.images:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            response.images[0].save(str(output_path))
            # Resize to exact source dimensions if needed
            src_w, src_h = get_image_dimensions(source_image)
            with Image.open(output_path) as img:
                if img.width != src_w or img.height != src_h:
                    img.resize((src_w, src_h), Image.LANCZOS).save(output_path)
            return output_path.exists()
        else:
            print("    imagen: no images returned")
            return False
    except Exception as e:
        err = str(e)
        if "429" in err:
            print("    imagen: rate limited, waiting 30s...")
            time.sleep(30)
            try:
                _imagen_last_call = time.time()
                response = _imagen_model.edit_images(
                    base_image=source,
                    prompt=full_prompt,
                    number_of_images=1,
                    safety_filter_level="block_few",
                    person_generation="allow_adult",
                )
                if response.images:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    response.images[0].save(str(output_path))
                    src_w, src_h = get_image_dimensions(source_image)
                    with Image.open(output_path) as img:
                        if img.width != src_w or img.height != src_h:
                            img.resize((src_w, src_h), Image.LANCZOS).save(output_path)
                    return output_path.exists()
            except Exception as e2:
                print(f"    imagen retry failed: {e2}")
                return False
        print(f"    imagen error: {err[:200]}")
        return False


def copy_original(src_path: str, dest_dir: Path) -> None:
    """Copy original photo into the experiment folder for comparison."""
    dest = dest_dir / "original.jpg"
    if not dest.exists() and Path(src_path).exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["mflux", "imagen", "both"], default="both")
    args = parser.parse_args()

    # Timestamped output folder per experiment
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    prompts_data = json.loads(PROMPTS_FILE.read_text())

    # Save prompts into the experiment folder for reference
    (run_dir / "prompts.json").write_text(PROMPTS_FILE.read_text())

    print(f"Loaded {len(prompts_data)} images with style prompts")
    print(f"Experiment: {run_dir}")
    print(f"Engine: {args.engine}")
    print(f"Mode: IMG2IMG style transfer (exact source dimensions preserved)")
    if args.engine in ("mflux", "both"):
        print(f"Local model: {MFLUX_MODEL}")
    print()

    total = sum(len(d["result"].get("styles", [])) for d in prompts_data)
    done = 0
    t0 = time.time()

    for img_data in prompts_data:
        uuid = img_data["uuid"]
        src_path = img_data["path"]
        styles = img_data["result"].get("styles", [])
        analysis = img_data["result"].get("analysis", "")

        # Read source image dimensions
        src_w, src_h = get_image_dimensions(src_path)

        img_dir = run_dir / uuid
        copy_original(src_path, img_dir)

        print(f"{'='*60}")
        print(f"Image: {uuid}")
        print(f"  Size: {src_w}x{src_h} ({'portrait' if src_h > src_w else 'landscape'})")
        print(f"  {analysis}")
        print(f"  {len(styles)} styles to generate\n")

        for j, style in enumerate(styles):
            style_name = style.get("name", f"style_{j}")
            prompt = style.get("style_prompt", style.get("prompt", ""))
            strength = max(0.55, min(0.7, style.get("strength", 0.65)))
            safe_name = style_name.lower().replace(" ", "_").replace("/", "-")[:40]

            print(f"  [{j+1}/{len(styles)}] {style_name} (strength: {strength})")
            print(f"    Style: {prompt[:80]}...")

            if args.engine in ("mflux", "both"):
                out_mflux = img_dir / f"mflux_{j}_{safe_name}.png"
                if out_mflux.exists():
                    print(f"    mflux: exists, skipping")
                else:
                    t1 = time.time()
                    ok = generate_mflux(prompt, src_path, out_mflux, strength, src_w, src_h)
                    print(f"    mflux: {'ok' if ok else 'FAILED'} ({time.time()-t1:.1f}s)")

            if args.engine in ("imagen", "both"):
                out_imagen = img_dir / f"imagen_{j}_{safe_name}.png"
                if out_imagen.exists():
                    print(f"    imagen: exists, skipping")
                else:
                    t1 = time.time()
                    ok = generate_imagen(prompt, src_path, out_imagen, strength)
                    print(f"    imagen: {'ok' if ok else 'FAILED'} ({time.time()-t1:.1f}s)")

            done += 1

        print()

    elapsed = time.time() - t0
    print(f"\nDone! {done} style prompts processed in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Experiment: {run_dir}")

    mflux_count = len(list(run_dir.glob("*/mflux_*.png")))
    imagen_count = len(list(run_dir.glob("*/imagen_*.png")))
    print(f"  mflux images:  {mflux_count}")
    print(f"  imagen images: {imagen_count}")


if __name__ == "__main__":
    main()
