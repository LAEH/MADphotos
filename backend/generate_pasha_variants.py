"""Generate 20 diverse style variants of pasha.png via Imagen 3."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PIL import Image
from google import genai
from google.genai import types

SOURCE = Path("/Users/laeh/Desktop/TypeButton/original.png")
OUT_DIR = Path("/Users/laeh/Desktop/pasha_variants")
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "imagen-3.0-capability-001"
GCP_PROJECT = "laeh380to760"
GCP_LOCATION = "us-central1"
DELAY = 16  # seconds between calls
MAX_RETRIES = 3

# 20 styles — wildly diverse, all demanding subject preservation
STYLES = [
    ("01_batman", (
        "In the style of Batman: The Animated Series and dark DC Comics. "
        "Art deco architecture, deep noir shadows, dramatic backlighting. "
        "Bold geometric shapes, strong silhouettes, moody atmospheric perspective. "
        "Deep blacks with electric blue neon accents and red highlights. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("02_ukiyoe", (
        "Traditional Japanese ukiyo-e woodblock print style. "
        "Flat areas of color with flowing black outlines, no gradients. "
        "Stylized patterns and elegant composition inspired by Hokusai. "
        "Indigo and cyan ink tones on cream paper. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("03_stainedglass", (
        "Gothic cathedral stained glass window — the scene rendered in jewel-toned "
        "translucent glass panels separated by thick black lead came lines. "
        "Light floods through saturated glass: deep ruby, sapphire, emerald, amethyst. "
        "Each color panel glows with backlit luminosity. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("04_ghibli", (
        "Studio Ghibli anime illustration — warm, inviting, hand-painted watercolor cel style. "
        "Soft diffused lighting, rich natural colors, gentle atmosphere. "
        "Clean linework, slightly rounded forms, expressive eyes. "
        "The cozy warmth of Miyazaki's domestic scenes. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("05_pixar", (
        "Pixar 3D animation render — hyperreal CG with soft subsurface scattering on fur. "
        "Warm Pixar lighting, slightly exaggerated proportions, expressive character. "
        "Cinematic depth of field, global illumination, photorealistic textures. "
        "The charm and heart of a Pixar feature film. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("06_sincity", (
        "In the style of Frank Miller's Sin City. "
        "Extreme high-contrast black and white — no midtones. "
        "Everything is pure black or blinding white. "
        "Rain-slicked surfaces, dramatic backlighting, noir atmosphere. "
        "One searing red accent only. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("07_technicolor", (
        "Explosive full-spectrum color illustration. "
        "Every surface saturated to maximum — electric red, vivid blue, blazing orange, "
        "acid green, hot pink, deep purple. "
        "Thick black outlines contain fields of pure flat saturated color. "
        "Pop art meets Fauvist explosion — Matisse cutouts on steroids. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("08_thermal", (
        "Thermal infrared camera image — FLIR false-color heat signature visualization. "
        "Cold regions in deep black and purple, warm zones in vivid red and orange, "
        "hot spots blazing yellow and white. Scientific overlay aesthetic. "
        "Every surface remapped by its heat emission. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("09_azulejo", (
        "Hand-painted Portuguese azulejo tile panel — cobalt blue on white tin-glazed ceramic. "
        "Bold blue brushstrokes on pure white glaze, visible tile grid. "
        "Baroque ornamental details, some tiles cracked, grout lines visible. "
        "Deep ultramarine blue — between navy and cobalt. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("10_kintsugi", (
        "Kintsugi — the Japanese art of golden repair. "
        "The image rendered on dark ceramic, then shattered and reassembled "
        "with bright gold lacquer filling every crack. "
        "Dark stoneware fragments with veins of pure gold running through the breaks. "
        "Wabi-sabi: the beauty of imperfection. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("11_embroidery", (
        "Traditional silk embroidery on black velvet ground — the image stitched "
        "thread by thread in luminous colored silk. "
        "Visible stitch direction: satin stitch, split stitch, French knots. "
        "Rich palette: ruby, sapphire, emerald, and gold thread on deep black velvet. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("12_charcoal", (
        "Raw charcoal drawing on heavyweight white paper. "
        "Smudged, grainy, tactile — deep velvety blacks rubbed into the paper grain. "
        "Aggressive mark-making: broad strokes, finger smudges, eraser lifts. "
        "High contrast with luminous white paper showing through. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("13_papercut", (
        "Multi-layered paper cut diorama — stacked layers of laser-cut paper "
        "creating dramatic depth with real shadows between layers. "
        "Pure white paper layers in front, graduating to deep black at back. "
        "Sharp geometric edges, architectural precision, dramatic parallax. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("14_sorayama", (
        "Hajime Sorayama chrome airbrush hyperrealism — everything rendered in liquid chrome. "
        "Mirror-perfect metal reflections, mercury pooling, chrome distortion. "
        "Razor-sharp highlights, deep metallic shadows, perfect gradients. "
        "1980s Japanese airbrush mastery. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("15_vectorcrt", (
        "Early 1980s vector CRT display — glowing phosphor lines on pure black screen. "
        "No fill, no solid areas — entire image is wireframe outlines made of light. "
        "Green phosphor glow with characteristic bloom and afterimage. "
        "Scanline artifacts, the romance of early computer graphics. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("16_mucha", (
        "In the style of Alphonse Mucha's Art Nouveau posters. "
        "Elegant flowing lines with ornamental botanical patterns. "
        "Purple, mint, and indigo jewel tones on pure white with strong black outlines. "
        "Intricate pattern work, luxurious poster-like composition. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("17_sovietmosaic", (
        "Monumental Soviet-era metro station tile mosaic. "
        "Thousands of small glass smalti tesserae — each tile a distinct square of vivid color. "
        "Bold, heroic composition — simplified geometric forms. "
        "Deep red, gold, midnight blue, white, and black palette. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("18_risograph", (
        "Risograph print — 2-3 color layers with deliberate misregistration. "
        "Soy-based ink on uncoated paper — visible ink grain, dot pattern, paper fiber. "
        "Each color layer slightly offset, creating halftone moiré. "
        "Limited palette: deep black, fluorescent pink, and electric blue. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("19_disney", (
        "Classic Disney hand-drawn animation style — 1990s renaissance era. "
        "Clean ink outlines with warm gouache colors, expressive character animation. "
        "Painterly backgrounds with rich atmospheric depth. "
        "The charm, warmth, and appeal of a Disney animated feature. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
    ("20_linocut", (
        "Bold linocut reduction print with vivid color layers. "
        "Thick black outlines carved from linoleum block. "
        "Flat saturated color layers — orange, green, pink — "
        "printed with slight misregistration for handmade quality. "
        "Visible carving marks and ink texture from roller. "
        "Maintain exact subject position and composition. "
        "NEVER add any border, frame, or vignette. Fill the entire canvas edge to edge."
    )),
]


def detect_border(arr: np.ndarray) -> tuple:
    h, w = arr.shape[:2]
    max_b, max_bw = int(h * 0.15), int(w * 0.15)
    ch, cw = h // 4, w // 4
    center_mean = np.mean(arr[ch:h-ch, cw:w-cw, :].astype(float), axis=(0, 1))

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
    for y in range(min(max_b, h)):
        if is_border_row(y): top = y + 1
        else: break
    bottom = 0
    for y in range(h - 1, max(h - max_b, 0) - 1, -1):
        if is_border_row(y): bottom = h - y
        else: break
    left = 0
    for x in range(min(max_bw, w)):
        if is_border_col(x): left = x + 1
        else: break
    right = 0
    for x in range(w - 1, max(w - max_bw, 0) - 1, -1):
        if is_border_col(x): right = w - x
        else: break
    return top, right, bottom, left


def post_process(output_path: Path, src_w: int, src_h: int):
    img = Image.open(output_path).convert("RGB")
    gw, gh = img.size
    if gw > src_w or gh > src_h:
        cx, cy = gw // 2, gh // 2
        cw, ch = min(gw, src_w), min(gh, src_h)
        img = img.crop((cx - cw//2, cy - ch//2, cx + cw//2, cy + ch//2))
    arr = np.array(img)
    t, r, b, l = detect_border(arr)
    if t + r + b + l > 0:
        oh, ow = arr.shape[:2]
        img = img.crop((l, t, ow - r, oh - b))
    if img.size != (src_w, src_h):
        img = img.resize((src_w, src_h), Image.LANCZOS)
    img.save(str(output_path), "JPEG", quality=92)
    img.close()


def main():
    # Copy original into output
    import shutil
    shutil.copy2(str(SOURCE), str(OUT_DIR / "00_original.png"))

    # Get source dimensions
    src = Image.open(SOURCE)
    src_w, src_h = src.size
    src.close()
    print(f"Source: {src_w}x{src_h}")

    # Load source bytes
    source_bytes = SOURCE.read_bytes()
    # Determine MIME type
    mime = "image/png" if SOURCE.suffix.lower() == ".png" else "image/jpeg"

    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)

    raw_ref = types.RawReferenceImage(
        reference_id=1,
        reference_image=types.Image(image_bytes=source_bytes, mime_type=mime),
    )

    success = 0
    filtered = 0
    failed = 0

    for idx, (name, prompt) in enumerate(STYLES):
        out_path = OUT_DIR / f"{name}.jpg"
        if out_path.exists():
            print(f"[{idx+1}/20] {name} — already exists, skipping")
            success += 1
            continue

        print(f"[{idx+1}/20] {name} — generating...", end=" ", flush=True)

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

        ok = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.models.edit_image(
                    model=MODEL,
                    prompt=prompt,
                    reference_images=[raw_ref],
                    config=edit_config,
                )

                if not response.generated_images:
                    print("FILTERED (safety)")
                    filtered += 1
                    break

                gen = response.generated_images[0].image
                if hasattr(gen, "image_bytes") and gen.image_bytes:
                    out_path.write_bytes(gen.image_bytes)
                elif hasattr(gen, "_pil_image") and gen._pil_image:
                    gen._pil_image.save(str(out_path), format="JPEG", quality=92)
                else:
                    gen.save(str(out_path))

                if out_path.exists():
                    post_process(out_path, src_w, src_h)
                    print(f"OK ({out_path.stat().st_size // 1024}KB)")
                    success += 1
                    ok = True
                break

            except Exception as e:
                err = str(e)
                is_rate = "429" in err or "quota" in err.lower() or "resource" in err.lower()
                backoff = 10 * (2 ** (attempt - 1))
                if is_rate:
                    backoff = max(backoff, 30)
                if attempt < MAX_RETRIES:
                    print(f"retry {attempt} in {backoff}s...", end=" ", flush=True)
                    time.sleep(backoff)
                else:
                    print(f"FAILED: {err[:80]}")
                    failed += 1

        # Rate limit delay
        if idx < len(STYLES) - 1:
            time.sleep(DELAY)

    print(f"\nDone: {success} OK, {filtered} filtered, {failed} failed")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
