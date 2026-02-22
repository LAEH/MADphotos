"""Imagen 3 generation with budget tracking and post-processing."""
from __future__ import annotations

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

from .config import (
    BASE_BACKOFF,
    COST_PER_IMAGE,
    DELAY_BETWEEN_CALLS,
    GCP_LOCATION,
    GCP_PROJECT,
    IMAGEN_MODEL,
    MAX_RETRIES,
    NEGATIVE_PROMPT,
    UUID_NAMESPACE,
)


def variant_id_for(image_uuid: str, style_key: str) -> str:
    """Deterministic variant ID for smart_style variants."""
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:smart_{style_key}"))


def create_client() -> genai.Client:
    return genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)


def _detect_border(arr: np.ndarray) -> tuple:
    """Detect borders by comparing edge strips vs center content.

    Uses two methods:
    1. Low-variance strips — rows/cols with very little variation (solid or near-solid)
    2. Edge-vs-center difference — edge strips whose mean color differs sharply from center

    Returns (top, right, bottom, left) in px.
    """
    h, w = arr.shape[:2]
    max_border = int(h * 0.15)
    max_border_w = int(w * 0.15)

    # Reference: mean color of the center 50% of the image
    ch, cw = h // 4, w // 4
    center = arr[ch:h - ch, cw:w - cw, :].astype(float)
    center_mean = np.mean(center, axis=(0, 1))

    def is_border_row(y: int) -> bool:
        row = arr[y, :, :].astype(float)
        row_mean = np.mean(row, axis=0)
        # Low variance (uniform strip) OR very different from center content
        if np.std(row) < 30:
            return True
        if np.linalg.norm(row_mean - center_mean) > 40:
            return True
        return False

    def is_border_col(x: int) -> bool:
        col = arr[:, x, :].astype(float)
        col_mean = np.mean(col, axis=0)
        if np.std(col) < 30:
            return True
        if np.linalg.norm(col_mean - center_mean) > 40:
            return True
        return False

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
    """Remove borders and resize to match source dimensions exactly."""
    source = Image.open(source_path)
    src_w, src_h = source.size
    source.close()

    img = Image.open(output_path).convert("RGB")
    gen_w, gen_h = img.size

    # Method 1: If generated image is larger than source, center-crop first
    if gen_w > src_w or gen_h > src_h:
        cx, cy = gen_w // 2, gen_h // 2
        crop_w = min(gen_w, src_w)
        crop_h = min(gen_h, src_h)
        img = img.crop((
            cx - crop_w // 2, cy - crop_h // 2,
            cx + crop_w // 2, cy + crop_h // 2,
        ))

    # Method 2: Detect and trim any remaining border artifacts
    arr = np.array(img)
    top, right, bottom, left = _detect_border(arr)
    if top + right + bottom + left > 0:
        oh, ow = arr.shape[:2]
        img = img.crop((left, top, ow - right, oh - bottom))

    # Resize to match source dimensions exactly
    if img.size != (src_w, src_h):
        img = img.resize((src_w, src_h), Image.LANCZOS)

    img.save(str(output_path), "JPEG", quality=92)
    img.close()


def generate_imagen(client: genai.Client, prompt: str, source_path: str,
                    output_path: Path) -> Tuple[bool, Optional[str]]:
    """Style transfer via Imagen 3. Returns (success, error_or_none)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_bytes = Path(source_path).read_bytes()
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
                prompt=prompt,
                reference_images=[raw_ref],
                config=edit_config,
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


def db_upsert(conn: sqlite3.Connection, variant_id: str, image_uuid: str,
              style_key: str, prompt: str, status: str, elapsed_ms: int = 0,
              rai_reason: Optional[str] = None, error: Optional[str] = None) -> None:
    conn.execute("""
        INSERT INTO ai_variants (
            variant_id, image_uuid, variant_type, model, prompt,
            negative_prompt, edit_mode, guidance_scale, source_tier,
            generation_status, rai_reason, error_message,
            generation_time_ms, created_at, style_key
        ) VALUES (?, ?, 'smart_style', ?, ?, ?, 'EDIT_MODE_STYLE', 75, 'mobile',
                  ?, ?, ?, ?, ?, ?)
        ON CONFLICT(variant_id) DO UPDATE SET
            generation_status=excluded.generation_status,
            rai_reason=excluded.rai_reason,
            error_message=excluded.error_message,
            generation_time_ms=excluded.generation_time_ms,
            style_key=excluded.style_key
    """, (
        variant_id, image_uuid, IMAGEN_MODEL, prompt,
        NEGATIVE_PROMPT,
        status, rai_reason, error, elapsed_ms,
        datetime.now(timezone.utc).isoformat(),
        style_key,
    ))
    conn.commit()


class BudgetTracker:
    """Track spending against a budget limit."""

    def __init__(self, budget: float) -> None:
        self.budget = budget
        self.spent = 0.0
        self.success_count = 0
        self.filtered_count = 0
        self.failed_count = 0

    def record_success(self) -> None:
        self.spent += COST_PER_IMAGE
        self.success_count += 1

    def record_filtered(self) -> None:
        self.spent += COST_PER_IMAGE
        self.filtered_count += 1

    def record_failed(self) -> None:
        self.failed_count += 1

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget - self.spent)

    @property
    def can_continue(self) -> bool:
        return self.spent + COST_PER_IMAGE <= self.budget

    @property
    def total_calls(self) -> int:
        return self.success_count + self.filtered_count + self.failed_count

    def summary(self) -> str:
        return (
            f"Budget: ${self.spent:.2f} / ${self.budget:.2f} "
            f"({self.success_count} OK, {self.filtered_count} filtered, "
            f"{self.failed_count} failed)"
        )


def copy_original(source_path: str, dest_dir: Path) -> None:
    """Copy the original photo into the variant directory for the review UI."""
    orig_dest = dest_dir / "original.jpg"
    if not orig_dest.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, orig_dest)
