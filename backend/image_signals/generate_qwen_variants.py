"""Generate image variants using Qwen's variant_prompts via Imagen 3.

Reads variant_prompts from qwen_analysis table, generates style-transferred
images via Imagen 3 EDIT_MODE_STYLE, records in ai_variants table.

Usage:
    python3 backend/image_signals/generate_qwen_variants.py --count 10
    python3 backend/image_signals/generate_qwen_variants.py --count 10 --styles 2
    python3 backend/image_signals/generate_qwen_variants.py --count 50 --budget 5.0
    python3 backend/image_signals/generate_qwen_variants.py --all --budget 25.0
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image
from google import genai
from google.genai import types

# ── constants ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
OUTPUT_DIR = PROJECT_ROOT / "backend" / "suggest_image_variant" / "output"

IMAGEN_MODEL = "imagen-3.0-capability-001"
GCP_PROJECT = "laeh380to760"
GCP_LOCATION = "us-central1"
UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

COST_PER_IMAGE = 0.04
DELAY_BETWEEN_CALLS = 16  # seconds (~4 req/min Imagen limit)
MAX_RETRIES = 3
BASE_BACKOFF = 10


# ── Imagen generation (self-contained, adapted from suggest_image_variant) ───

def _detect_border(arr: np.ndarray) -> tuple:
    h, w = arr.shape[:2]
    max_border = int(h * 0.15)
    max_border_w = int(w * 0.15)
    ch, cw = h // 4, w // 4
    center = arr[ch:h - ch, cw:w - cw, :].astype(float)
    center_mean = np.mean(center, axis=(0, 1))

    def is_border_row(y):
        row = arr[y, :, :].astype(float)
        if np.std(row) < 30:
            return True
        return np.linalg.norm(np.mean(row, axis=0) - center_mean) > 40

    def is_border_col(x):
        col = arr[:, x, :].astype(float)
        if np.std(col) < 30:
            return True
        return np.linalg.norm(np.mean(col, axis=0) - center_mean) > 40

    top = 0
    for y in range(min(max_border, h)):
        if is_border_row(y):
            top = y + 1
        else:
            break
    bottom = 0
    for y in range(h - 1, max(h - max_border, 0) - 1, -1):
        if is_border_row(y):
            bottom = h - y
        else:
            break
    left = 0
    for x in range(min(max_border_w, w)):
        if is_border_col(x):
            left = x + 1
        else:
            break
    right = 0
    for x in range(w - 1, max(w - max_border_w, 0) - 1, -1):
        if is_border_col(x):
            right = w - x
        else:
            break
    return top, right, bottom, left


def _post_process(output_path: Path, source_path: str) -> None:
    source = Image.open(source_path)
    src_w, src_h = source.size
    source.close()
    img = Image.open(output_path).convert("RGB")
    gen_w, gen_h = img.size
    if gen_w > src_w or gen_h > src_h:
        cx, cy = gen_w // 2, gen_h // 2
        crop_w, crop_h = min(gen_w, src_w), min(gen_h, src_h)
        img = img.crop((cx - crop_w // 2, cy - crop_h // 2,
                        cx + crop_w // 2, cy + crop_h // 2))
    arr = np.array(img)
    top, right, bottom, left = _detect_border(arr)
    if top + right + bottom + left > 0:
        oh, ow = arr.shape[:2]
        img = img.crop((left, top, ow - right, oh - bottom))
    if img.size != (src_w, src_h):
        img = img.resize((src_w, src_h), Image.LANCZOS)
    img.save(str(output_path), "JPEG", quality=92)
    img.close()


def generate_imagen(client: genai.Client, prompt: str, source_path: str,
                    output_path: Path) -> Tuple[bool, Optional[str]]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = Path(source_path).read_bytes()
    raw_ref = types.RawReferenceImage(
        reference_id=1,
        reference_image=types.Image(image_bytes=source_bytes, mime_type="image/jpeg"),
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
                model=IMAGEN_MODEL, prompt=prompt,
                reference_images=[raw_ref], config=edit_config,
            )
            if not response.generated_images:
                return False, "safety_filter"
            gen_image = response.generated_images[0].image
            if hasattr(gen_image, "image_bytes") and gen_image.image_bytes:
                output_path.write_bytes(gen_image.image_bytes)
            elif hasattr(gen_image, "_pil_image") and gen_image._pil_image:
                gen_image._pil_image.save(str(output_path), format="JPEG", quality=92)
            else:
                gen_image.save(str(output_path))
            if output_path.exists():
                _post_process(output_path, source_path)
            return output_path.exists(), None
        except Exception as e:
            err = str(e)
            is_rate = "429" in err or "quota" in err.lower() or "resource" in err.lower()
            backoff = BASE_BACKOFF * (2 ** (attempt - 1))
            if is_rate:
                backoff = max(backoff, 30)
            if attempt < MAX_RETRIES:
                print(f"      retry {attempt}/{MAX_RETRIES} in {backoff}s: {err[:60]}")
                time.sleep(backoff)
            else:
                return False, err[:200]
    return False, "max_retries"


# ── candidate selection ──────────────────────────────────────────────

def get_candidates(conn: sqlite3.Connection, count: int | None,
                   styles_per_image: int) -> list[dict]:
    rows = conn.execute("""
        SELECT q.uuid, q.variant_prompts
        FROM qwen_analysis q
        WHERE q.variant_prompts IS NOT NULL
          AND length(q.variant_prompts) > 200
          AND json_array_length(q.variant_prompts) >= ?
        ORDER BY length(q.variant_prompts) DESC
    """, (styles_per_image,)).fetchall()

    existing = set()
    for row in conn.execute("""
        SELECT image_uuid, style_key FROM ai_variants
        WHERE variant_type = 'qwen_variant'
          AND generation_status IN ('success', 'filtered')
    """).fetchall():
        existing.add((row[0], row[1]))

    candidates = []
    for uuid_val, vp_json in rows:
        try:
            prompts = json.loads(vp_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(prompts, list):
            continue
        pending_prompts = []
        for i, vp in enumerate(prompts[:styles_per_image]):
            if not isinstance(vp, dict) or not vp.get("prompt"):
                continue
            style_key = f"qwen_{vp.get('style', f'style_{i}').lower().replace(' ', '_')}"
            if (uuid_val, style_key) not in existing:
                pending_prompts.append((i, style_key, vp))
        if pending_prompts:
            candidates.append({"uuid": uuid_val, "prompts": pending_prompts})
        if count and len(candidates) >= count:
            break
    return candidates


def get_source_path(conn: sqlite3.Connection, image_uuid: str) -> str | None:
    row = conn.execute("""
        SELECT local_path FROM tiers
        WHERE image_uuid = ? AND tier_name = 'mobile' AND format = 'jpeg'
          AND variant_id IS NULL
        LIMIT 1
    """, (image_uuid,)).fetchone()
    if row and Path(row[0]).exists():
        return row[0]
    return None


def qwen_variant_id(image_uuid: str, style_key: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:{style_key}"))


def db_upsert(conn: sqlite3.Connection, variant_id: str, image_uuid: str,
              style_key: str, prompt: str, status: str, elapsed_ms: int = 0,
              rai_reason: str | None = None, error: str | None = None) -> None:
    conn.execute("""
        INSERT INTO ai_variants (
            variant_id, image_uuid, variant_type, model, prompt,
            edit_mode, guidance_scale, source_tier,
            generation_status, rai_reason, error_message,
            generation_time_ms, created_at, style_key
        ) VALUES (?, ?, 'qwen_variant', ?, ?, 'EDIT_MODE_STYLE', 75, 'mobile',
                  ?, ?, ?, ?, ?, ?)
        ON CONFLICT(variant_id) DO UPDATE SET
            generation_status=excluded.generation_status,
            rai_reason=excluded.rai_reason,
            error_message=excluded.error_message,
            generation_time_ms=excluded.generation_time_ms
    """, (
        variant_id, image_uuid, IMAGEN_MODEL, prompt,
        status, rai_reason, error, elapsed_ms,
        datetime.now(timezone.utc).isoformat(), style_key,
    ))
    conn.commit()


def build_prompt(vp: dict) -> str:
    base = vp.get("prompt", "")
    color_palette = vp.get("color_palette")
    inner = base
    if color_palette:
        if isinstance(color_palette, list):
            color_palette = ", ".join(color_palette)
        inner += f" Dominant colors: {color_palette}."
    return (
        "Transform this photograph into the following artistic style, "
        "preserving the exact composition, subjects, and layout. "
        "No text or lettering. No border, frame, or vignette. "
        f"Style: {inner}"
    )


# ── budget tracker ───────────────────────────────────────────────────

class BudgetTracker:
    def __init__(self, budget: float) -> None:
        self.budget = budget
        self.spent = 0.0
        self.success_count = 0
        self.filtered_count = 0
        self.failed_count = 0

    def record_success(self):
        self.spent += COST_PER_IMAGE
        self.success_count += 1

    def record_filtered(self):
        self.spent += COST_PER_IMAGE
        self.filtered_count += 1

    def record_failed(self):
        self.failed_count += 1

    @property
    def can_continue(self) -> bool:
        return self.spent + COST_PER_IMAGE <= self.budget

    def summary(self) -> str:
        return (f"${self.spent:.2f}/${self.budget:.2f} "
                f"({self.success_count} OK, {self.filtered_count} filtered, "
                f"{self.failed_count} failed)")


# ── main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate variants from Qwen prompts")
    parser.add_argument("--count", type=int, default=10,
                        help="Number of images to process (default: 10)")
    parser.add_argument("--all", action="store_true",
                        help="Process all available images")
    parser.add_argument("--styles", type=int, default=2,
                        help="Max styles per image (default: 2)")
    parser.add_argument("--budget", type=float, default=5.0,
                        help="Max spend in $ (default: 5.0)")
    parser.add_argument("--dry", action="store_true",
                        help="Show what would be generated without calling API")
    args = parser.parse_args()

    count = None if args.all else args.count
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    candidates = get_candidates(conn, count, args.styles)
    total_variants = sum(len(c["prompts"]) for c in candidates)

    print(f"Qwen variant generation via Imagen 3")
    print(f"  Images: {len(candidates)}")
    print(f"  Variants: {total_variants} ({args.styles} styles/image max)")
    print(f"  Budget: ${args.budget:.2f} (${COST_PER_IMAGE:.2f}/variant)")
    print(f"  Est. cost: ${total_variants * COST_PER_IMAGE:.2f}")
    print(f"  Est. time: ~{total_variants * DELAY_BETWEEN_CALLS // 60}m")
    print()

    if args.dry:
        for c in candidates:
            src = get_source_path(conn, c["uuid"])
            print(f"  {c['uuid'][:12]}...  source: {'OK' if src else 'MISSING'}")
            for _, style_key, vp in c["prompts"]:
                print(f"    -> {style_key}: {vp.get('prompt', '')[:80]}...")
        print(f"\nDry run complete. Use without --dry to generate.")
        conn.close()
        return

    # Create run directory
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / f"qwen_{run_ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Output: {run_dir}")
    print()

    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    tracker = BudgetTracker(args.budget)

    for img_idx, candidate in enumerate(candidates, 1):
        image_uuid = candidate["uuid"]
        source_path = get_source_path(conn, image_uuid)
        if not source_path:
            print(f"[{img_idx}/{len(candidates)}] {image_uuid[:12]}... SKIP (no mobile tier)")
            continue

        img_dir = run_dir / image_uuid
        img_dir.mkdir(parents=True, exist_ok=True)
        orig_dest = img_dir / "original.jpg"
        if not orig_dest.exists():
            shutil.copy2(source_path, orig_dest)

        print(f"[{img_idx}/{len(candidates)}] {image_uuid[:12]}...")

        for prompt_idx, style_key, vp in candidate["prompts"]:
            if not tracker.can_continue:
                print(f"  Budget exhausted: {tracker.summary()}")
                break

            vid = qwen_variant_id(image_uuid, style_key)
            prompt = build_prompt(vp)
            style_name = vp.get("style", style_key)
            out_path = img_dir / f"qwen_{style_key}.jpg"

            print(f"  [{prompt_idx+1}] {style_name}...", end=" ", flush=True)

            t0 = time.time()
            success, error = generate_imagen(client, prompt, source_path, out_path)
            elapsed_ms = int((time.time() - t0) * 1000)

            if success:
                tracker.record_success()
                db_upsert(conn, vid, image_uuid, style_key, prompt,
                          "success", elapsed_ms)
                print(f"OK ({elapsed_ms/1000:.1f}s)")
            elif error == "safety_filter":
                tracker.record_filtered()
                db_upsert(conn, vid, image_uuid, style_key, prompt,
                          "filtered", elapsed_ms, rai_reason="safety")
                print(f"FILTERED ({elapsed_ms/1000:.1f}s)")
            else:
                tracker.record_failed()
                db_upsert(conn, vid, image_uuid, style_key, prompt,
                          "failed", elapsed_ms, error=str(error)[:200])
                print(f"FAILED: {str(error)[:60]}")

            wait = max(0, DELAY_BETWEEN_CALLS - (time.time() - t0))
            if wait > 0 and tracker.can_continue:
                time.sleep(wait)

        if not tracker.can_continue:
            print(f"\nBudget exhausted.")
            break

    print(f"\n{'='*50}")
    print(f"DONE: {tracker.summary()}")
    print(f"Output: {run_dir}")

    successes = conn.execute("""
        SELECT image_uuid, style_key FROM ai_variants
        WHERE variant_type = 'qwen_variant' AND generation_status = 'success'
        ORDER BY created_at DESC LIMIT 20
    """).fetchall()
    if successes:
        print(f"\nGenerated variants:")
        for iu, sk in successes:
            print(f"  {iu[:12]}... -> {sk}")

    conn.close()


if __name__ == "__main__":
    main()
