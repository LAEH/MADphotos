#!/usr/bin/env python3
"""
generate_variants_v2.py — Learned-preference variant generation.

Uses acceptance patterns from 904 reviewed variants to maximize acceptance rate.
Targets untried picks with highest aesthetic scores.

Acceptance data (from review history):
  watercolor (gemma)  65%   |  impressionist (gemma) 80%
  illustration (gemma) 65%  |  ghibli (gemma) 58%
  ink (style_transfer)  51% |  sumi-e (smart) 100% (n=3)
  batman (smart) 40%        |  gonzo (smart) 40%

Avoided (low acceptance): moebius 0%, pixar/smart 10%, vintage 13%,
  comic 18%, ukiyoe 19%, archer 22%

Usage:
    python3 generate_variants_v2.py                   # 125 images × 2 styles = 250 calls (~$10)
    python3 generate_variants_v2.py --count 50        # Custom image count
    python3 generate_variants_v2.py --dry             # Preview only
    python3 generate_variants_v2.py --budget 5        # $5 worth (~125 calls)
"""
from __future__ import annotations

import argparse
import json
import random
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
GENERATED_DIR = Path(__file__).resolve().parent / "suggest_image_variant" / "output"
PICKS_PATH = PROJECT_ROOT / "frontend" / "show" / "public" / "data" / "picks.json"

IMAGEN_MODEL = "imagen-3.0-capability-001"
GCP_PROJECT = "laeh380to760"
GCP_LOCATION = "us-central1"
UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

COST_PER_CALL = 0.04
DELAY_BETWEEN_CALLS = 16
MAX_RETRIES = 3
BASE_BACKOFF = 10

NEGATIVE_PROMPT = (
    "photorealistic, dull colors, blurry, low quality, text, watermark, "
    "salmon pink tones, coral orange, muddy khaki, oversaturated, "
    "washed out, flat lighting"
)


# ── Style Library (curated from acceptance data) ─────────────────────────────

STYLES: Dict[str, Dict[str, Any]] = {
    "watercolor": {
        "name": "Watercolor",
        "weight": 25,  # % of total assignments
        "prompt": (
            "Delicate watercolor painting with soft washes and gentle blending. "
            "Transparent layers of color bleeding into each other on textured paper. "
            "Loose, expressive brushwork with areas of white paper showing through. "
            "Dreamy, nostalgic quality with muted, harmonious tones. "
            "Subtle color gradients and soft edges."
        ),
        "affinities": {"serene": 3, "nature": 3, "peaceful": 2, "golden": 2,
                        "exterior": 2, "monochrome": 1, "no_faces": 2},
        "penalties": {"gritty": -1, "dark": -1},
    },
    "illustration": {
        "name": "Illustration",
        "weight": 20,
        "prompt": (
            "Elegant editorial illustration with confident linework and "
            "sophisticated color palette. Clean shapes with subtle textures, "
            "balanced composition between detail and simplicity. "
            "Professional quality like a New Yorker magazine cover — "
            "thoughtful, refined, quietly beautiful."
        ),
        "affinities": {"urban": 2, "architectural": 2, "interior": 2,
                        "cinematic": 1, "exterior": 1},
        "penalties": {"chaotic": -1},
    },
    "ghibli": {
        "name": "Studio Ghibli",
        "weight": 15,
        "prompt": (
            "In the style of Studio Ghibli animation by Hayao Miyazaki. "
            "Beautifully detailed backgrounds with soft, luminous colors. "
            "Warm golden lighting, lush greens, and gentle atmospheric perspective. "
            "Painterly skies with volumetric clouds. Serene, magical feeling "
            "that makes ordinary scenes feel extraordinary. Hand-painted quality."
        ),
        "affinities": {"nature": 3, "serene": 2, "exterior": 2, "peaceful": 2,
                        "golden": 2, "vast": 1},
        "penalties": {"dark": -2, "gritty": -2, "night": -1},
    },
    "impressionist": {
        "name": "Impressionist",
        "weight": 10,
        "prompt": (
            "French Impressionist oil painting in the style of Monet and Renoir. "
            "Visible brushstrokes capturing the play of light on surfaces. "
            "Dappled sunlight, vibrant yet harmonious color mixing. "
            "Emphasis on atmosphere and mood over precise detail. "
            "Warm, luminous palette with touches of complementary colors."
        ),
        "affinities": {"exterior": 3, "golden": 3, "nature": 2, "serene": 2,
                        "bright": 1},
        "penalties": {"dark": -2, "night": -2, "gritty": -1},
    },
    "ink": {
        "name": "Ink Drawing",
        "weight": 10,
        "prompt": (
            "Bold black ink drawing with confident, expressive linework. "
            "Mix of precise contours and loose gestural strokes. "
            "Strong contrast between black ink and white paper. "
            "Crosshatching and stippling for tonal depth. "
            "Raw, immediate quality with artistic energy. Minimal color — "
            "primarily monochrome with occasional ink wash accents."
        ),
        "affinities": {"monochrome": 4, "urban": 2, "architectural": 2,
                        "moody": 1, "gritty": 1},
        "penalties": {"colorful": -1, "bright": -1},
    },
    "batman_noir": {
        "name": "Batman TAS / Noir",
        "weight": 10,
        "prompt": (
            "In the style of Batman: The Animated Series and dark DC Comics. "
            "Art deco architecture, deep noir shadows, dramatic backlighting. "
            "Limited palette dominated by deep navy, charcoal, and amber highlights. "
            "Bold geometric shapes, strong silhouettes, moody atmospheric perspective. "
            "Dark skies with muted warm accents. Cinematic and brooding."
        ),
        "affinities": {"night": 3, "moody": 2, "urban": 2, "cinematic": 1,
                        "dark": 2, "architectural": 1},
        "penalties": {"bright": -3, "airy": -2, "peaceful": -1, "serene": -1},
    },
    "sumie": {
        "name": "Sumi-e Ink Wash",
        "weight": 5,
        "prompt": (
            "Traditional Japanese sumi-e ink wash painting. "
            "Black ink on white rice paper, minimal brushstrokes. "
            "Wet-on-wet technique creating soft gradients and atmospheric washes. "
            "Zen aesthetic — capture the essence with fewest strokes possible. "
            "Negative space is as important as the marks. "
            "Monochromatic with subtle gray variations."
        ),
        "affinities": {"monochrome": 4, "serene": 3, "nature": 2,
                        "minimal": 2, "no_faces": 2},
        "penalties": {"colorful": -2, "faces_many": -2, "urban": -1},
    },
    "gonzo": {
        "name": "Gonzo / Steadman",
        "weight": 5,
        "prompt": (
            "In the style of Ralph Steadman's gonzo illustrations. "
            "Explosive ink splatters, scratchy pen strokes, chaotic energy. "
            "Distorted perspective with visceral, raw emotion. "
            "Black ink dominant with sharp accents of red, yellow, or blue. "
            "Loose, aggressive linework that feels alive and unpredictable."
        ),
        "affinities": {"gritty": 3, "urban": 2, "moody": 2, "chaotic": 2,
                        "night": 1},
        "penalties": {"serene": -3, "peaceful": -2, "ethereal": -2},
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


ACCEPTANCE_BASELINE = {
    "watercolor": 3.0,      # 65% gemma_cartoon
    "illustration": 3.0,    # 65% gemma_cartoon
    "ghibli": 2.5,          # 58% gemma_cartoon
    "impressionist": 3.5,   # 80% gemma_cartoon
    "ink": 2.0,             # 51% style_transfer
    "batman_noir": 1.0,     # 40% smart_style
    "sumie": 2.5,           # 100% smart_style (small n)
    "gonzo": 1.0,           # 40% smart_style
}


def score_style(style_key: str, photo: Dict) -> float:
    """Score how well a style matches a photo's characteristics.
    Starts from acceptance-rate baseline, then adjusts by photo signals."""
    style = STYLES[style_key]
    affinities = style["affinities"]
    penalties = style["penalties"]
    score = ACCEPTANCE_BASELINE.get(style_key, 0.0)

    setting = (photo.get("setting") or "").lower()
    grading = (photo.get("grading_style") or "").lower()
    time_of_day = (photo.get("time_of_day") or "").lower()
    vibes = parse_vibes(photo.get("vibe"))
    faces = photo.get("faces_count") or 0
    is_mono = bool(photo.get("is_monochrome"))

    # Setting
    if "exterior" in setting:
        score += affinities.get("exterior", 0) + penalties.get("exterior", 0)
    if "interior" in setting:
        score += affinities.get("interior", 0) + penalties.get("interior", 0)

    # Time of day
    if "night" in time_of_day:
        score += affinities.get("night", 0) + penalties.get("night", 0)
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
                         "nostalgic", "peaceful", "vast", "airy", "chaotic",
                         "bright", "dark", "minimal"]:
            if keyword in vibe:
                score += affinities.get(keyword, 0) + penalties.get(keyword, 0)

    # Face count
    if faces == 0:
        score += affinities.get("no_faces", 0)
    elif faces >= 3:
        score += penalties.get("faces_many", 0)

    return score


def pick_styles(photo: Dict) -> List[str]:
    """Pick 2 best-suited styles for a photo, weighted by acceptance rate."""
    scores = [(key, score_style(key, photo)) for key in STYLES]
    scores.sort(key=lambda x: -x[1])

    # Group by family to ensure variety
    families = {
        "watercolor": "paint", "impressionist": "paint", "ghibli": "anime",
        "illustration": "modern", "ink": "mono", "sumie": "mono",
        "batman_noir": "dark", "gonzo": "dark",
    }

    picked = [scores[0][0]]
    first_family = families[picked[0]]

    for key, sc in scores[1:]:
        if families[key] != first_family:
            picked.append(key)
            break

    if len(picked) < 2:
        picked.append(scores[1][0])

    return picked[:2]


# ── Image Generation ─────────────────────────────────────────────────────────

def variant_id_for(image_uuid: str, style_key: str) -> str:
    """Deterministic variant ID."""
    return str(uuid.uuid5(UUID_NAMESPACE, f"{image_uuid}:v2_{style_key}"))


def generate_imagen(client: genai.Client, prompt: str, source_path: str,
                    output_path: Path) -> Tuple[bool, Optional[str]]:
    """Style transfer via Imagen 3."""
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


# ── Candidate Selection ──────────────────────────────────────────────────────

def get_candidates(conn: sqlite3.Connection, count: int) -> List[Dict]:
    """Get untried picked photos with highest aesthetic scores."""

    # Load pick IDs from picks.json
    with open(PICKS_PATH) as f:
        picks = json.load(f)
    all_pick_ids = set(picks.get("portrait", []) + picks.get("landscape", []))
    gen_ids = set(picks.get("generated", []))
    orig_pick_ids = all_pick_ids - gen_ids

    if not orig_pick_ids:
        return []

    placeholders = ",".join("?" for _ in orig_pick_ids)
    rows = conn.execute(f"""
        SELECT i.uuid, i.category, i.subcategory, i.orientation, i.is_monochrome,
               ga.setting, ga.time_of_day, ga.grading_style, ga.vibe, ga.faces_count,
               a.score as aesthetic,
               MIN(t.local_path) as source_path
        FROM images i
        JOIN gemini_analysis ga ON i.uuid = ga.image_uuid
        LEFT JOIN aesthetic_scores a ON i.uuid = a.image_uuid
        JOIN tiers t ON i.uuid = t.image_uuid
            AND t.tier_name = 'mobile' AND t.format = 'jpeg' AND t.variant_id IS NULL
        WHERE i.uuid IN ({placeholders})
        AND i.uuid NOT IN (
            SELECT DISTINCT image_uuid FROM ai_variants
            WHERE variant_type = 'smart_style'
            AND generation_status IN ('success', 'filtered')
        )
        GROUP BY i.uuid
        ORDER BY a.score DESC, i.uuid
        LIMIT ?
    """, list(orig_pick_ids) + [count]).fetchall()

    return [dict(r) for r in rows]


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate v2 smart variants (learned preferences)")
    parser.add_argument("--count", type=int, default=125, help="Number of images to process")
    parser.add_argument("--budget", type=float, help="Budget in USD (overrides --count)")
    parser.add_argument("--dry", action="store_true", help="Preview style matching only")
    parser.add_argument("--styles", action="store_true", help="Show styles with weights")
    args = parser.parse_args()

    if args.styles:
        print(f"{'Key':<15} {'Name':<20} {'Weight':>6} {'Prompt (first 70 chars)'}")
        print("-" * 115)
        for key, style in STYLES.items():
            print(f"{key:<15} {style['name']:<20} {style['weight']:>5}% {style['prompt'][:70]}...")
        total_w = sum(s["weight"] for s in STYLES.values())
        print(f"\nTotal weight: {total_w}%")
        return

    if args.budget:
        calls = int(args.budget / COST_PER_CALL)
        args.count = calls // 2  # 2 styles per image
        print(f"Budget ${args.budget:.2f} → {calls} Imagen calls → {args.count} images × 2 styles")

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row

    candidates = get_candidates(conn, args.count)
    print(f"Found {len(candidates)} candidate images (top aesthetic, untried)")

    if not candidates:
        print("Nothing to do — all picked photos already have smart variants.")
        conn.close()
        return

    # Style matching
    style_counts: Dict[str, int] = {}
    assignments: List[Tuple[Dict, List[str]]] = []

    for photo in candidates:
        styles = pick_styles(photo)
        assignments.append((photo, styles))
        for s in styles:
            style_counts[s] = style_counts.get(s, 0) + 1

    total_calls = sum(style_counts.values())
    est_cost = total_calls * COST_PER_CALL
    est_time = total_calls * DELAY_BETWEEN_CALLS / 60

    print(f"\n{'─' * 60}")
    print(f"  Images: {len(candidates)}")
    print(f"  Total Imagen calls: {total_calls}")
    print(f"  Estimated cost: ${est_cost:.2f}")
    print(f"  Estimated time: {est_time:.0f} min ({est_time/60:.1f} hr)")
    print(f"{'─' * 60}")

    print(f"\nStyle distribution:")
    for key in sorted(style_counts, key=lambda k: -style_counts[k]):
        pct = style_counts[key] * 100 // total_calls
        bar = "█" * (pct // 2)
        print(f"  {STYLES[key]['name']:<20} {style_counts[key]:>4} ({pct:>2}%) {bar}")

    if args.dry:
        print(f"\n{'UUID':<38} {'Aes':>4} {'Orient':<10} {'Setting':<12} {'Faces'} → {'Style 1':<20} {'Style 2'}")
        print("-" * 120)
        for photo, styles in assignments[:40]:
            print(f"{photo['uuid']:<38} {(photo['aesthetic'] or 0):>4.1f} "
                  f"{photo['orientation']:<10} {(photo['setting'] or '')[:11]:<12} "
                  f"{photo['faces_count'] or 0:>5} → "
                  f"{STYLES[styles[0]]['name']:<20} {STYLES[styles[1]]['name']}")
        if len(assignments) > 40:
            print(f"  ... and {len(assignments) - 40} more")
        conn.close()
        return

    # Generate
    run_dir = GENERATED_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput: {run_dir}")

    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    total_ok = 0
    total_fail = 0
    total_filtered = 0
    cost_so_far = 0.0
    start_time = time.time()

    for img_i, (photo, styles) in enumerate(assignments):
        uid = photo["uuid"]
        source = photo["source_path"]
        img_dir = run_dir / uid
        vibes = parse_vibes(photo.get("vibe"))

        elapsed_total = time.time() - start_time
        rate = (total_ok + total_fail + total_filtered) / max(elapsed_total / 60, 0.1)

        print(f"\n[{img_i+1}/{len(assignments)}] {uid}")
        print(f"  {photo['orientation']} | {photo.get('setting', '?')} | "
              f"faces={photo.get('faces_count', 0)} | aes={photo.get('aesthetic', 0):.1f}")
        print(f"  Progress: {total_ok}ok {total_filtered}filt {total_fail}fail | "
              f"${cost_so_far:.2f} spent | {rate:.1f}/min")

        for style_key in styles:
            style = STYLES[style_key]
            vid = variant_id_for(uid, style_key)

            # Skip if already done
            row = conn.execute(
                "SELECT generation_status FROM ai_variants WHERE variant_id=?", (vid,)
            ).fetchone()
            if row and row[0] in ("success", "filtered"):
                print(f"  {style['name']:<20} — already done, skip")
                total_ok += 1
                continue

            out_path = img_dir / f"imagen_v2_{style_key}.jpg"
            print(f"  {style['name']:<20} — generating...", end=" ", flush=True)

            t1 = time.time()
            success, error = generate_imagen(client, style["prompt"], source, out_path)
            elapsed_ms = int((time.time() - t1) * 1000)
            cost_so_far += COST_PER_CALL

            if success:
                total_ok += 1
                db_upsert(conn, vid, uid, style_key, style["prompt"], "success", elapsed_ms)
                print(f"OK ({elapsed_ms/1000:.1f}s)")
            elif error == "safety_filter":
                total_filtered += 1
                db_upsert(conn, vid, uid, style_key, style["prompt"], "filtered", elapsed_ms,
                          rai_reason="safety")
                print(f"FILTERED")
            else:
                total_fail += 1
                db_upsert(conn, vid, uid, style_key, style["prompt"], "failed", elapsed_ms,
                          error=error)
                print(f"FAILED: {error[:60]}")

            # Rate limit
            wait = max(0, DELAY_BETWEEN_CALLS - (time.time() - t1))
            if wait > 0:
                time.sleep(wait)

    conn.close()
    elapsed_min = (time.time() - start_time) / 60
    total = total_ok + total_fail + total_filtered
    print(f"\n{'═' * 60}")
    print(f"  Done in {elapsed_min:.1f} min")
    print(f"  {total_ok}/{total} OK, {total_filtered} filtered, {total_fail} failed")
    print(f"  Cost: ${cost_so_far:.2f}")
    print(f"  Output: {run_dir}")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
