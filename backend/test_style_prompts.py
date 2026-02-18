#!/usr/bin/env python3
"""Test: Generate 5 diverse style-transfer descriptors per photo using Gemma 27b.

Picks random images from picks.json, sends each to the local model,
and asks for 5 maximally different style transfer descriptions.
These are NOT full scene prompts — they describe only the artistic style
to apply to the existing image (composition/subject preserved via img2img).

Usage:
  python3 backend/test_style_prompts.py
  python3 backend/test_style_prompts.py --count 10
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import sqlite3
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:27b"

PROMPT = """You are an expert art director specializing in style transfer. Look at THIS photograph and pick the 5 styles that would produce the most stunning transformations for THIS specific image.

Analyze deeply — the light, shadows, geometry, mood, textures, subject, color palette. Then choose 5 styles where each one is a PERFECT match for what's in the image. Not your defaults — styles THIS image is begging to become.

RULES:
- STYLE descriptors only — composition, subjects, and layout are preserved
- Do NOT describe the scene — the image already has that
- DO describe: exact medium, texture, technique, materials, tonal quality
- Each prompt must be DETAILED (40-60 words) — specific enough to generate from
- ALWAYS specify 3-4 exact colors derived from the image's own palette
- NO text, typography, or lettering
- The 5 styles must be radically different from each other

YOUR FULL PALETTE (pick whatever fits THIS image best):
- Anime/Manga: Ghibli soft watercolor, Makoto Shinkai luminous, 90s cel shading, Junji Ito horror ink
- 3D/Cartoon: Pixar subsurface skin, Claymation handmade, Cartoon Network flat, Disney renaissance, Archer sharp flat cel-shading with muted spy-palette
- B&W/Graphic: Charcoal on rough paper, pen crosshatch, Sumi-e ink wash, noir silhouette, edge-detection contour, stipple dots, scratchboard engraving
- Print/Process: Cyanotype blueprint, risograph 2-color, linocut woodblock, screen print halftone, mezzotint, photogravure
- Painting: Van Gogh impasto, Monet impressionist, Klimt gold leaf, Caravaggio chiaroscuro, Basquiat raw, Hopper light, Rothko color field, Hockney pool-bright
- Photo Effect: Infrared false color, solarization, double exposure, high-key bleach, shadow crush duotone, chromatic aberration
- Material/Craft: Mosaic tile, stained glass, embroidery, torn paper collage, gold leaf lacquer, ceramic glaze
- Illustration: Ligne claire, vintage travel poster, botanical watercolor, editorial ink wash, children's crayon, Corto Maltese Hugo Pratt bold ink brush with dramatic black pools

Respond with ONLY valid JSON:
{"analysis":"1 sentence on what makes this photo special","styles":[{"name":"short name (2-3 words)","style_prompt":"detailed style descriptors, 40-60 words, exact technique + materials + 3-4 specific colors from the image, no scene description, no text","strength":0.5 to 0.85,"why":"1 sentence — why THIS style suits THIS image"}]}

strength guide: 0.5 = subtle, 0.65 = moderate, 0.75 = strong (default), 0.85 = dramatic.

Example GOOD: "High-contrast charcoal on rough cold-press paper, deep velvety blacks with aggressive crosshatch shading in burnt umber and raw sienna, bright highlights left as raw white paper, warm grey midtones, edges dissolving into dust and grain with deliberate smudging"
Example GOOD: "Archer-style flat cel animation, crisp black outlines with muted teal and burgundy color blocks, minimal shading with sharp shadow cutoffs, desaturated warm skin tones, clean vector-like rendering"
Example BAD: "A Japanese woodblock print showing a person standing in a city" (describes the scene — WRONG)"""


def get_sample_images(count: int = 5) -> list[tuple[str, str]]:
    """Return (uuid, path) pairs for random picked images."""
    picks = json.loads(PICKS_JSON.read_text())
    all_uuids = list(dict.fromkeys(picks["portrait"] + picks["landscape"]))
    random.shuffle(all_uuids)

    conn = sqlite3.connect(str(DB_PATH))
    results = []
    for uuid in all_uuids:
        if len(results) >= count:
            break
        row = conn.execute(
            "SELECT local_path FROM tiers "
            "WHERE image_uuid=? AND tier_name='mobile' AND format='jpeg' LIMIT 1",
            (uuid,),
        ).fetchone()
        if row and Path(row[0]).exists():
            results.append((uuid, row[0]))
    conn.close()
    return results


def query_gemma(img_path: str) -> dict:
    """Send image to Gemma and get style transfer descriptors."""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": MODEL,
        "prompt": PROMPT,
        "images": [img_b64],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1500},
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=300)
    result = json.loads(resp.read())
    text = result.get("response", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5, help="Number of images to test")
    args = parser.parse_args()

    print(f"Picking {args.count} random images from picks...")
    samples = get_sample_images(args.count)
    print(f"Got {len(samples)} images with local paths\n")

    all_results = []

    for i, (uuid, path) in enumerate(samples):
        print(f"{'='*60}")
        print(f"[{i+1}/{len(samples)}] {uuid}")
        print(f"  Path: {path}")

        t0 = time.time()
        result = query_gemma(path)
        elapsed = time.time() - t0

        print(f"  Time: {elapsed:.1f}s")

        if "raw" in result:
            print(f"  ERROR: Failed to parse JSON")
            print(f"  Raw: {result['raw'][:200]}")
            continue

        print(f"  Analysis: {result.get('analysis', 'N/A')}")
        styles = result.get("styles", [])
        print(f"  Styles ({len(styles)}):")
        for j, s in enumerate(styles):
            strength = s.get("strength", 0.5)
            print(f"\n    {j+1}. {s.get('name', '?')} (strength: {strength})")
            print(f"       Style: {s.get('style_prompt', '?')}")
            print(f"       Why: {s.get('why', '?')}")

        all_results.append({
            "uuid": uuid,
            "path": path,
            "elapsed": round(elapsed, 1),
            "result": result,
        })
        print()

    # Save full results
    out_path = PROJECT_ROOT / "backend" / "style_prompts_test.json"
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"\nFull results saved to {out_path}")
    print(f"Total images: {len(all_results)}")

    # Print style diversity summary
    all_styles = []
    for r in all_results:
        for s in r.get("result", {}).get("styles", []):
            all_styles.append(s.get("name", "?"))
    print(f"Total style descriptors: {len(all_styles)}")
    print(f"Unique style names: {len(set(all_styles))}")
    if all_styles:
        print(f"Styles: {', '.join(sorted(set(all_styles)))}")


if __name__ == "__main__":
    main()
