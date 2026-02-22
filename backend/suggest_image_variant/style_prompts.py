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

PROMPT = """You are an expert animation art director. Look at THIS photograph and choose the 5 BEST cartoon/illustration/animation styles to transform it into.

Analyze the photo — light, mood, subjects, colors, energy. Then pick 5 cartoon styles that would look STUNNING for THIS specific image. Match the style to the image's character.

RULES:
- STYLE descriptors only — composition, subjects, and layout are preserved
- Do NOT describe the scene — the image already has that
- DO describe: exact animation technique, line quality, shading method, color rendering
- Each prompt must be DETAILED (40-60 words) — specific enough to generate from
- ALWAYS specify a color palette (3-4 specific colors) derived from the image
- NO text, typography, or lettering
- All 5 must be RADICALLY different cartoon/illustration styles

CARTOON STYLE PALETTE — pick the 5 best for THIS image:
- Ghibli: Soft watercolor washes, delicate ink lines, dreamy atmospheric depth
- Makoto Shinkai: Hyper-detailed backgrounds, luminous sky gradients, photorealistic lighting in anime form
- 90s Anime Cel: Hard outlines, flat color fills, dramatic speed lines, saturated palette
- Adult Anime: Detailed realistic anatomy, moody lighting, cinematic framing, mature palette
- Anime Aquarelle: Wet-on-wet watercolor bleeds, soft anime features, translucent color layering
- Archer: Sharp flat cel-shading, muted spy-palette, crisp vector outlines, minimal gradients, dry wit aesthetic
- Pixar 3D: Subsurface scattering skin, soft ambient occlusion, hyper-clean rendering, warm bounce light
- Disney Renaissance: Rich painted backgrounds, expressive character design, lush color, visible brushwork
- Cartoon Network: Bold graphic shapes, thick outlines, pop-bright flat colors, playful exaggeration
- Corto Maltese: Hugo Pratt bold ink brush, dramatic black pools, sparse detail, raw pen strokes, high contrast
- Ligne Claire: Tintin-style uniform line weight, flat colors, no hatching, clean precise outlines
- Manga B&W: Screentone shading, dynamic inking, stark black/white contrast, expressive linework
- Vintage Cartoon: Rubber hose limbs, halftone dots, faded newsprint palette, 1930s charm
- Comic Book: Ben-Day dots, bold primary colors, dynamic inking, superhero drama
- Marvel: Dynamic heroic poses, rich detailed inking, dramatic lighting, vibrant saturated colors, muscular rendering, cinematic action-panel energy
- Moebius/Giraud: Intricate fine-line crosshatch, surreal color, otherworldly detail, sci-fi elegance
- Children's Book: Soft crayon/gouache texture, warm rounded shapes, gentle palette, storybook warmth
- Ukiyo-e: Woodblock flat color planes, bold outlines, wave patterns, traditional Japanese palette
- Pop Art: Warhol screen-print bold, flat saturated colors, halftone dots, graphic punch
- Concept Art: Loose painterly strokes, cinematic atmosphere, muted palette with focal color accent
- Graphic Novel: Heavy shadows, noir-influenced inking, limited palette, gritty realism

ALSO: Check if the image appears to be in the WRONG ORIENTATION (rotated 90° clockwise, 90° counter-clockwise, or upside down). Many photos have incorrect EXIF rotation. Look at the actual content — are subjects sideways? Is the horizon vertical? Is text sideways?

Respond with ONLY valid JSON:
{"analysis":"1 sentence on what makes this photo special","rotation":0,"styles":[{"name":"short name (2-3 words)","style_prompt":"detailed cartoon/illustration style descriptors, 40-60 words, exact technique + line quality + shading + 3-4 specific colors from the image","strength":0.75,"why":"1 sentence — why THIS cartoon style suits THIS image"}]}

rotation: 0 = correct orientation, 90 = needs 90° clockwise rotation, 180 = upside down, 270 = needs 90° counter-clockwise rotation.
Use strength 0.75 for all (Imagen 3 handles this well for cartoon transforms).

Example GOOD: "Archer-style flat cel animation, crisp black outlines with muted teal and burgundy color blocks, minimal shading with sharp shadow cutoffs, desaturated warm skin tones, clean vector-like rendering with subtle grain texture"
Example GOOD: "Studio Ghibli soft watercolor, delicate washes of muted sage green and dusty rose, fine ink linework with breathing white space, soft atmospheric haze, warm golden hour light rendered in translucent paint layers"
Example GOOD: "Hugo Pratt Corto Maltese ink brush, bold confident strokes in pure black, dramatic pools of shadow, minimal hatching, raw white paper as negative space, occasional warm sepia wash accent"
Example BAD: "A cartoon version of the person in the photo standing on a street" (describes the scene — WRONG)"""


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

        rotation = result.get("rotation", 0)
        if rotation:
            print(f"  *** ROTATION NEEDED: {rotation}° ***")
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

        # Save incrementally so Imagen can pick up new prompts in real time
        out_path = PROJECT_ROOT / "backend" / "style_prompts_test.json"
        out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
        print(f"  Saved ({len(all_results)} images in prompts file)")
        print()

    # Final save
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
