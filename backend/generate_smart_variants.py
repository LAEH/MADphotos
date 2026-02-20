#!/usr/bin/env python3
"""
generate_smart_variants.py — Generate 2 best-suited style variants per picked photo.

Uses learned acceptance patterns to match styles to photo characteristics.
Minimizes rejection by avoiding tones and styles that historically fail.

Style library:
  archer      — Archer TV series: clean vector art, bold outlines, flat color
  gonzo       — Ralph Steadman: ink splatters, kinetic energy, distorted
  ukiyoe      — Traditional Japanese woodblock: flat colors, flowing lines
  batman      — Batman TAS / dark DC: noir shadows, dramatic lighting
  pixar       — 3D render: subsurface scattering, warm Pixar look (86% accept rate)
  moebius     — Moebius/Ligne Claire: European comic, clean lines, pastels
  sumie       — Sumi-e ink wash: minimal Japanese, black ink, zen
  marvel      — Marvel comic book: dynamic poses, bold colors, halftone dots

Matching rules (from analysis of 189 reviewed variants):
  - No faces → 71% accept (vs 43% with faces). Strongly prefer faceless photos.
  - Monochrome originals: 83-88% accept. B&W transforms beautifully.
  - Pixar style: 86% accept — safe default for objects/scenes.
  - Exterior settings: 59% accept. Interior: 48%.
  - Avoid salmon/coral/khaki tones (73-100% reject).
  - Low dominant saturation preferred (21% accepted vs 31% rejected).

Usage:
    python3 generate_smart_variants.py                    # Generate for 100 images
    python3 generate_smart_variants.py --count 50         # Custom count
    python3 generate_smart_variants.py --dry              # Preview style matching only
    python3 generate_smart_variants.py --styles           # Show all styles
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
GENERATED_DIR = Path(__file__).resolve().parent / "generated_test"

IMAGEN_MODEL = "imagen-3.0-capability-001"
GCP_PROJECT = "laeh380to760"
GCP_LOCATION = "us-central1"
UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

DELAY_BETWEEN_CALLS = 16  # seconds (Imagen rate limit ~4/min)
MAX_RETRIES = 3
BASE_BACKOFF = 10

# Negative prompt: learned from rejection patterns
NEGATIVE_PROMPT = (
    "photorealistic, dull colors, blurry, low quality, text, watermark, "
    "salmon pink tones, coral orange, muddy khaki, oversaturated, "
    "washed out, flat lighting"
)


# ── Style Library ────────────────────────────────────────────────────────────

STYLES = {
    "archer": {
        "name": "Archer TV",
        "prompt": (
            "In the style of the Archer animated TV series. "
            "Clean vector illustration with bold black outlines, flat color blocks, "
            "sharp geometric shadows, limited but punchy color palette. "
            "Cel-shaded with subtle gradients. Stylish mid-century modern aesthetic. "
            "Confident linework, no texture noise."
        ),
        # Scores higher for: urban, interior, people, night, gritty
        "affinities": {"interior": 3, "night": 3, "urban": 2, "gritty": 2, "faces": 1},
        "penalties": {"nature": -2, "serene": -1},
    },
    "gonzo": {
        "name": "Gonzo / Steadman",
        "prompt": (
            "In the style of Ralph Steadman's gonzo illustrations. "
            "Explosive ink splatters, scratchy pen strokes, chaotic energy. "
            "Distorted perspective with visceral, raw emotion. "
            "Black ink dominant with sharp accents of red, yellow, or blue. "
            "Loose, aggressive linework that feels alive and unpredictable. "
            "No clean edges — everything vibrates with kinetic tension."
        ),
        "affinities": {"gritty": 4, "urban": 3, "moody": 2, "chaotic": 2, "night": 2},
        "penalties": {"serene": -3, "peaceful": -2, "ethereal": -2},
    },
    "ukiyoe": {
        "name": "Ukiyo-e Woodblock",
        "prompt": (
            "Traditional Japanese ukiyo-e woodblock print style. "
            "Flat areas of color with flowing black outlines, no gradients. "
            "Limited palette of indigo, vermillion, ochre, and soft green on cream paper. "
            "Stylized clouds, waves, or foliage patterns. "
            "Elegant composition with decorative border sensibility. "
            "Inspired by Hokusai and Hiroshige."
        ),
        "affinities": {"exterior": 3, "nature": 3, "serene": 2, "water": 2, "landscape_orient": 2},
        "penalties": {"interior": -2, "faces_many": -2},
    },
    "batman": {
        "name": "Batman TAS / Dark DC",
        "prompt": (
            "In the style of Batman: The Animated Series and dark DC Comics. "
            "Art deco architecture, deep noir shadows, dramatic backlighting. "
            "Limited palette dominated by deep navy, charcoal, and amber highlights. "
            "Bold geometric shapes, strong silhouettes, moody atmospheric perspective. "
            "Dark skies with muted warm accents. Cinematic and brooding."
        ),
        "affinities": {"night": 4, "moody": 3, "urban": 3, "cinematic": 2, "dark": 2, "architectural": 2},
        "penalties": {"bright": -3, "airy": -2, "peaceful": -1},
    },
    "pixar": {
        "name": "Pixar 3D",
        "prompt": (
            "In the style of Pixar Animation Studios 3D render. "
            "Subsurface scattering for organic materials, soft ambient occlusion. "
            "Warm, inviting lighting with gentle global illumination. "
            "Slightly rounded forms, micro-detail textures, photorealistic materials "
            "with a charming stylized quality. Rich color with depth."
        ),
        # Proven 86% acceptance rate — safe default
        "affinities": {"objects": 2, "vehicles": 2, "exterior": 1, "no_faces": 2},
        "penalties": {"faces_many": -1},
    },
    "moebius": {
        "name": "Moebius / Ligne Claire",
        "prompt": (
            "In the style of Moebius (Jean Giraud) and the European Ligne Claire tradition. "
            "Clean, uniform-weight ink lines with no hatching. "
            "Pastel and desaturated color fills — dusty pinks, sage greens, pale blues. "
            "Vast sense of space and meticulous architectural detail. "
            "Dreamlike atmosphere with crystalline clarity. "
            "Every surface precisely delineated."
        ),
        "affinities": {"exterior": 2, "landscape_orient": 2, "architectural": 2, "serene": 1, "vast": 2},
        "penalties": {"dark": -1, "gritty": -1},
    },
    "sumie": {
        "name": "Sumi-e Ink Wash",
        "prompt": (
            "Traditional Japanese sumi-e ink wash painting. "
            "Black ink on white rice paper, minimal brushstrokes. "
            "Wet-on-wet technique creating soft gradients and atmospheric washes. "
            "Zen aesthetic — capture the essence with fewest strokes possible. "
            "Negative space is as important as the marks. "
            "Monochromatic with subtle gray variations."
        ),
        "affinities": {"monochrome": 4, "serene": 2, "nature": 2, "minimal": 2, "no_faces": 2},
        "penalties": {"colorful": -2, "faces_many": -2, "urban": -1},
    },
    "marvel": {
        "name": "Marvel Comic Book",
        "prompt": (
            "In the style of classic Marvel comic book art by Jack Kirby and Jim Steranko. "
            "Dynamic composition with bold ink outlines and crosshatching. "
            "Vivid primary colors with halftone dot patterns. "
            "Dramatic foreshortening, Kirby crackle energy effects. "
            "Strong chiaroscuro shadows, heroic proportions. "
            "Action-packed visual energy even in still moments."
        ),
        "affinities": {"gritty": 2, "urban": 2, "moody": 1, "exterior": 1, "dynamic": 2},
        "penalties": {"serene": -2, "peaceful": -2, "ethereal": -1},
    },
}


# ── Photo Signal Analysis ────────────────────────────────────────────────────

def parse_vibes(vibe_json: Optional[str]) -> List[str]:
    if not vibe_json:
        return []
    try:
        v = json.loads(vibe_json)
        return [x.lower() for x in v] if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def score_style(style_key: str, photo: Dict) -> float:
    """Score how well a style matches a photo's characteristics."""
    style = STYLES[style_key]
    affinities = style["affinities"]
    penalties = style["penalties"]
    score = 0.0

    setting = (photo.get("setting") or "").lower()
    grading = (photo.get("grading_style") or "").lower()
    time_of_day = (photo.get("time_of_day") or "").lower()
    vibes = parse_vibes(photo.get("vibe"))
    faces = photo.get("faces_count") or 0
    is_mono = bool(photo.get("is_monochrome"))
    orientation = photo.get("orientation", "landscape")

    # Setting signals
    if "exterior" in setting:
        score += affinities.get("exterior", 0) + penalties.get("exterior", 0)
    if "interior" in setting:
        score += affinities.get("interior", 0) + penalties.get("interior", 0)

    # Time of day
    if "night" in time_of_day:
        score += affinities.get("night", 0)
    if "golden" in time_of_day:
        score += affinities.get("golden", 0)

    # Grading
    if "cinematic" in grading:
        score += affinities.get("cinematic", 0)
    if "monochrome" in grading or is_mono:
        score += affinities.get("monochrome", 0) + penalties.get("colorful", 0)

    # Vibes
    for vibe in vibes:
        for keyword in ["moody", "gritty", "urban", "serene", "ethereal",
                         "nostalgic", "peaceful", "vast", "airy", "chaotic"]:
            if keyword in vibe:
                score += affinities.get(keyword, 0) + penalties.get(keyword, 0)

    # Face count (strong signal)
    if faces == 0:
        score += affinities.get("no_faces", 0)
    elif faces >= 3:
        score += penalties.get("faces_many", 0)
    else:
        score += affinities.get("faces", 0)

    # Orientation
    if orientation == "landscape":
        score += affinities.get("landscape_orient", 0)

    # Bonus: Pixar gets a baseline boost (proven 86% acceptance)
    if style_key == "pixar":
        score += 1.0

    return score


def pick_styles(photo: Dict) -> List[str]:
    """Pick the 2 best-suited styles for a photo. Ensures variety (no duplicate families)."""
    scores = [(key, score_style(key, photo)) for key in STYLES]
    scores.sort(key=lambda x: -x[1])

    # Pick top 1, then next best that's from a different "family"
    # Group families: ink-based (gonzo, sumie), comic (marvel, batman, archer), artistic (ukiyoe, moebius, pixar)
    families = {
        "archer": "comic", "batman": "comic", "marvel": "comic",
        "gonzo": "ink", "sumie": "ink",
        "ukiyoe": "trad", "moebius": "euro", "pixar": "3d",
    }

    picked = [scores[0][0]]
    first_family = families[picked[0]]

    for key, sc in scores[1:]:
        if families[key] != first_family:
            picked.append(key)
            break

    # Fallback: if somehow no variety, just take #2
    if len(picked) < 2:
        picked.append(scores[1][0])

    return picked[:2]


# ── Image Generation ─────────────────────────────────────────────────────────

def variant_id_for(image_uuid: str, style_key: str) -> str:
    """Deterministic variant ID."""
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:smart_{style_key}"))


def generate_imagen(client: genai.Client, prompt: str, source_path: str,
                    output_path: Path) -> Tuple[bool, Optional[str]]:
    """Style transfer via Imagen 3. Returns (success, error)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    full_prompt = (
        f"Transform this photograph into the following artistic style, "
        f"preserving the exact composition, subjects, and layout. "
        f"No text or lettering. Style: {prompt}"
    )

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
            generation_time_ms, created_at
        ) VALUES (?, ?, 'smart_style', ?, ?, ?, 'EDIT_MODE_STYLE', 75, 'mobile',
                  ?, ?, ?, ?, ?)
        ON CONFLICT(variant_id) DO UPDATE SET
            generation_status=excluded.generation_status,
            rai_reason=excluded.rai_reason,
            error_message=excluded.error_message,
            generation_time_ms=excluded.generation_time_ms
    """, (
        variant_id, image_uuid, IMAGEN_MODEL, prompt,
        NEGATIVE_PROMPT,
        status, rai_reason, error, elapsed_ms,
        datetime.now(timezone.utc).isoformat(),
    ))
    conn.commit()


# ── Main ─────────────────────────────────────────────────────────────────────

def get_candidates(conn: sqlite3.Connection, count: int) -> List[Dict]:
    """Get picked photos without accepted variants, ordered by aesthetic score."""
    rows = conn.execute("""
        SELECT i.uuid, i.category, i.subcategory, i.orientation, i.is_monochrome,
               ga.setting, ga.time_of_day, ga.grading_style, ga.vibe, ga.faces_count,
               a.score as aesthetic,
               MIN(t.local_path) as source_path
        FROM images i
        JOIN gemini_analysis ga ON i.uuid = ga.image_uuid
        LEFT JOIN aesthetic_scores a ON i.uuid = a.image_uuid
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = 'mobile' AND t.format = 'jpeg' AND t.variant_id IS NULL
        WHERE i.uuid NOT IN (
            SELECT image_uuid FROM ai_variants
            WHERE review_status = 'accepted'
        )
        AND i.uuid NOT IN (
            SELECT image_uuid FROM ai_variants
            WHERE variant_type = 'smart_style' AND generation_status IN ('success', 'filtered')
        )
        GROUP BY i.uuid
        ORDER BY a.score DESC, i.uuid
        LIMIT ?
    """, (count,)).fetchall()
    return [dict(r) for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 2 smart style variants per image")
    parser.add_argument("--count", type=int, default=100, help="Number of images to process")
    parser.add_argument("--dry", action="store_true", help="Preview style matching only, no generation")
    parser.add_argument("--styles", action="store_true", help="Show all available styles")
    args = parser.parse_args()

    if args.styles:
        print(f"{'Key':<10} {'Name':<25} {'Prompt (first 80 chars)'}")
        print("-" * 115)
        for key, style in STYLES.items():
            print(f"{key:<10} {style['name']:<25} {style['prompt'][:80]}...")
        return

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    candidates = get_candidates(conn, args.count)
    print(f"Found {len(candidates)} candidate images")

    if not candidates:
        print("Nothing to do — all picked photos already have accepted or pending smart variants.")
        conn.close()
        return

    # Preview style matching
    style_counts: Dict[str, int] = {}
    assignments: List[Tuple[Dict, List[str]]] = []

    for photo in candidates:
        styles = pick_styles(photo)
        assignments.append((photo, styles))
        for s in styles:
            style_counts[s] = style_counts.get(s, 0) + 1

    print(f"\nStyle distribution across {len(candidates)} images ({len(candidates) * 2} variants):")
    for key in sorted(style_counts, key=lambda k: -style_counts[k]):
        print(f"  {STYLES[key]['name']:<25} {style_counts[key]:>4} ({style_counts[key]*100//(len(candidates)*2)}%)")

    if args.dry:
        print(f"\n{'UUID':<38} {'Cat':<8} {'Orient':<10} {'Setting':<10} {'Faces'} → {'Style 1':<15} {'Style 2'}")
        print("-" * 120)
        for photo, styles in assignments[:30]:
            print(f"{photo['uuid']:<38} {photo['category']:<8} {photo['orientation']:<10} "
                  f"{(photo['setting'] or ''):<10} {photo['faces_count'] or 0:>5} → "
                  f"{STYLES[styles[0]]['name']:<15} {STYLES[styles[1]]['name']}")
        if len(assignments) > 30:
            print(f"  ... and {len(assignments) - 30} more")
        conn.close()
        return

    # Generate
    run_dir = GENERATED_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput: {run_dir}")

    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    total_ok = 0
    total_fail = 0

    for img_i, (photo, styles) in enumerate(assignments):
        uid = photo["uuid"]
        source = photo["source_path"]
        img_dir = run_dir / uid
        vibes = parse_vibes(photo.get("vibe"))

        print(f"\n[{img_i+1}/{len(assignments)}] {uid}")
        print(f"  {photo['category']} {photo['orientation']} | "
              f"{photo.get('setting', '?')} | faces={photo.get('faces_count', 0)} | "
              f"vibes={','.join(vibes[:3])}")

        for style_key in styles:
            style = STYLES[style_key]
            vid = variant_id_for(uid, style_key)
            safe_name = style_key

            # Skip if already done
            row = conn.execute(
                "SELECT generation_status FROM ai_variants WHERE variant_id=?", (vid,)
            ).fetchone()
            if row and row[0] in ("success", "filtered"):
                print(f"  {style['name']:<25} — already done, skip")
                total_ok += 1
                continue

            out_path = img_dir / f"imagen_smart_{safe_name}.jpg"

            print(f"  {style['name']:<25} — generating...")

            t1 = time.time()
            success, error = generate_imagen(client, style["prompt"], source, out_path)
            elapsed_ms = int((time.time() - t1) * 1000)

            if success:
                total_ok += 1
                db_upsert(conn, vid, uid, style_key, style["prompt"], "success", elapsed_ms)
                print(f"  {style['name']:<25} — OK ({elapsed_ms/1000:.1f}s)")
            elif error == "safety_filter":
                total_fail += 1
                db_upsert(conn, vid, uid, style_key, style["prompt"], "filtered", elapsed_ms,
                          rai_reason="safety")
                print(f"  {style['name']:<25} — FILTERED")
            else:
                total_fail += 1
                db_upsert(conn, vid, uid, style_key, style["prompt"], "failed", elapsed_ms,
                          error=error)
                print(f"  {style['name']:<25} — FAILED: {error[:60]}")

            # Rate limit
            wait = max(0, DELAY_BETWEEN_CALLS - (time.time() - t1))
            if wait > 0:
                time.sleep(wait)

    conn.close()
    total = total_ok + total_fail
    print(f"\nDone: {total_ok}/{total} OK, {total_fail} failed")
    print(f"Output: {run_dir}")


if __name__ == "__main__":
    main()
