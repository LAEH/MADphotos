"""Style library, cost constants, and paths for the suggest_image_variant pipeline."""
from __future__ import annotations

import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
GENERATED_DIR = PROJECT_ROOT / "backend" / "suggest_image_variant" / "output"

IMAGEN_MODEL = "imagen-3.0-capability-001"
GCP_PROJECT = "laeh380to760"
GCP_LOCATION = "us-central1"
UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Rate limiting
DELAY_BETWEEN_CALLS = 16  # seconds (~4/min Imagen limit)
MAX_RETRIES = 3
BASE_BACKOFF = 10

# Budget
COST_PER_IMAGE = 0.04  # Imagen 3 edit_image cost estimate
DEFAULT_BUDGET = 10.00
STYLES_PER_PHOTO = 2

# Performance tracking thresholds
DEAD_THRESHOLD = 0.10       # <10% acceptance rate = dead style
DEAD_MIN_REVIEWS = 15       # need this many reviews before declaring dead
EXPLORE_RATE = 0.20         # 20% chance slot 2 picks an undertested style
EXPLORE_MAX_REVIEWS = 5     # styles with fewer reviews than this are "undertested"
PERFORMANCE_CENTER = 0.45   # median acceptance rate — neutral point
PERFORMANCE_SCALE = 10.0    # multiplier for rate → score conversion
PERFORMANCE_MIN_TRUST = 8   # need this many reviews before applying performance modifier
EXPLORATION_BONUS = 2.0     # score bonus for styles with <3 reviews

# Orientation balance for bento — target portrait ratio in each generation batch.
# Bento grids need both portrait and landscape tiles; 0.45 means ~45% portrait.
BENTO_PORTRAIT_RATIO = 0.45

# Learned negative prompt from rejection patterns
NEGATIVE_PROMPT = (
    "photorealistic, dull colors, blurry, low quality, text, watermark, "
    "salmon pink tones, coral orange, muddy khaki, oversaturated, "
    "washed out, flat lighting, beige, cream, sepia, warm yellow, "
    "ochre, brown tones, pastel, muted earth tones, "
    "border, frame, decorative edge, vignette, mat, picture frame"
)

# Global color directive — appended to every prompt to enforce the palette
# Apple Developer Colors (no brown, no yellow): Red #FF3B30, Orange #FF9500,
# Green #34C759, Mint #00C7BE, Teal #30B0C7, Cyan #32ADE6, Blue #007AFF,
# Indigo #5856D6, Purple #AF52DE, Pink #FF2D55
COLOR_DIRECTIVE = (
    "CRITICAL COLOR RULE — Apple-inspired vibrant palette. "
    "Three modes — pick the one that best fits the mood: "
    "(1) BLACK DOMINANT: deep rich blacks with pure white accents and one explosive color pop "
    "from this palette: Red #FF3B30, Blue #007AFF, Green #34C759, Purple #AF52DE, Pink #FF2D55. "
    "(2) WHITE DOMINANT: clean pure white with jet black linework and one electric accent "
    "from: Cyan #32ADE6, Teal #30B0C7, Indigo #5856D6, Mint #00C7BE, Orange #FF9500. "
    "(3) COLOR EXPLOSION: jet black and pure white as structure, then BURST with 2-3 vivid colors "
    "from the full Apple palette — Red, Orange, Green, Mint, Teal, Cyan, Blue, Indigo, Purple, Pink. "
    "Make colors POP — saturated, electric, alive. Think neon on black, ink on white. "
    "NEVER use beige, cream, yellow, ochre, sepia, warm brown, pastel, or muted tones. "
    "Whites must be pure white (#FFF). Blacks must be deep and rich. "
    "Explore stunning textures: ink grain, paper fiber, spray stipple, brush drag, woodcut relief. "
    "NEVER add any border, frame, mat, edge decoration, or vignette. Fill the entire canvas edge to edge."
)

# Salmon/coral/khaki hue ranges to avoid (dominant_hue in degrees)
# Salmon/coral: ~0-20°, Khaki: ~45-65°
REJECTED_HUE_RANGES = [(0, 20), (45, 65)]

# Style families — ensures pick_styles chooses diversity
FAMILIES = {
    "archer": "comic",
    "batman": "comic",
    "marvel": "comic",
    "gonzo": "ink",
    "sumie": "ink",
    "ukiyoe": "trad",
    "woodcut": "print",
    "scraperboard": "engrave",
    "linocut": "print",
    "shinkai": "shinkai",
    "hugopratt": "ink",
    "sincity": "noir",
    "saulbass": "poster",
    "banksy": "stencil",
    "mucha": "nouveau",
    "technicolor": "pop",
}

# ── 10-style library ────────────────────────────────────────────────────────

STYLES = {
    "archer": {
        "name": "Archer TV",
        "prompt": (
            "In the style of the Archer animated TV series. "
            "Clean vector illustration with bold black outlines and flat color blocks. "
            "Sharp geometric shadows, cel-shaded with subtle gradients. "
            "Stylish mid-century modern aesthetic with confident linework. "
            "Tinted with Teal #30B0C7 and Orange #FF9500 accents on black."
        ),
        "affinities": {"interior": 3, "night": 3, "urban": 2, "gritty": 2, "faces": 1},
        "penalties": {"nature": -2, "serene": -1},
    },
    "gonzo": {
        "name": "Gonzo / Steadman",
        "prompt": (
            "In the style of Ralph Steadman's gonzo illustrations. "
            "Explosive ink splatters, scratchy pen strokes, chaotic energy. "
            "Distorted perspective with visceral, raw emotion. "
            "Black ink dominant with violent splashes of Red #FF3B30 and Blue #007AFF. "
            "Loose, aggressive linework that feels alive and unpredictable. "
            "Ink splatter textures, drips, and raw brush marks on pure white."
        ),
        "affinities": {"gritty": 4, "urban": 3, "moody": 2, "chaotic": 2, "night": 2},
        "penalties": {"serene": -3, "peaceful": -2, "ethereal": -2},
    },
    "ukiyoe": {
        "name": "Ukiyo-e Woodblock",
        "prompt": (
            "Traditional Japanese ukiyo-e woodblock print style. "
            "Flat areas of color with flowing black outlines, no gradients. "
            "Stylized clouds, waves, or foliage patterns. "
            "Elegant composition inspired by Hokusai and Hiroshige. "
            "Indigo #5856D6 and Cyan #32ADE6 ink tones on pure white paper."
        ),
        "affinities": {"exterior": 3, "nature": 3, "serene": 2, "water": 2, "landscape_orient": 2},
        "penalties": {"interior": -2, "faces_many": -2},
    },
    "batman": {
        "name": "Batman TAS / Dark DC",
        "prompt": (
            "In the style of Batman: The Animated Series and dark DC Comics. "
            "Art deco architecture, deep noir shadows, dramatic backlighting. "
            "Bold geometric shapes, strong silhouettes, moody atmospheric perspective. "
            "Deep blacks with electric Blue #007AFF neon accents and Red #FF3B30 highlights. "
            "Cinematic and brooding, every shadow sculpted."
        ),
        "affinities": {"night": 4, "moody": 3, "urban": 3, "cinematic": 2, "dark": 2, "architectural": 2},
        "penalties": {"bright": -3, "airy": -2, "peaceful": -1},
    },
    "scraperboard": {
        "name": "Scraperboard / Scratchboard",
        "prompt": (
            "Scraperboard illustration — white lines scratched into black surface. "
            "The image revealed by removing black to expose white beneath. "
            "Fine parallel hatching and cross-hatching creating luminous forms from darkness. "
            "Hyper-detailed textures emerging from deep black ground. "
            "Occasional scratches reveal Mint #00C7BE or Cyan #32ADE6 beneath the black."
        ),
        "affinities": {"night": 4, "dark": 3, "moody": 3, "monochrome": 3, "cinematic": 2,
                        "exterior": 2, "no_faces": 2},
        "penalties": {"bright": -2, "colorful": -1},
    },
    "woodcut": {
        "name": "Japanese Woodcut",
        "prompt": (
            "Bold black and white woodcut print. "
            "Hand-carved linework with visible wood grain texture in solid black areas. "
            "Strong graphic contrast — pure black forms on pure white paper. "
            "Dramatic negative space, thick confident carved lines. "
            "Selective areas of Green #34C759 or Indigo #5856D6 ink overprint."
        ),
        "affinities": {"exterior": 3, "monochrome": 3, "moody": 2, "cinematic": 2,
                        "landscape_orient": 2, "dark": 1, "no_faces": 2},
        "penalties": {"bright": -1, "colorful": -1},
    },
    "sumie": {
        "name": "Sumi-e Ink Wash",
        "prompt": (
            "Traditional Japanese sumi-e ink wash painting. "
            "Pure black ink on pure white rice paper, minimal brushstrokes. "
            "Wet-on-wet technique creating soft gradients and atmospheric washes. "
            "Zen aesthetic — capture the essence with fewest strokes possible. "
            "One delicate accent of Teal #30B0C7 ink wash in the composition."
        ),
        "affinities": {"monochrome": 4, "serene": 2, "nature": 2, "minimal": 2, "no_faces": 2},
        "penalties": {"colorful": -2, "faces_many": -2, "urban": -1},
    },
    "marvel": {
        "name": "Marvel Comic Book",
        "prompt": (
            "In the style of classic Marvel comic book art by Jack Kirby and Jim Steranko. "
            "Dynamic composition with bold ink outlines and crosshatching. "
            "Halftone dot patterns with Red #FF3B30, Blue #007AFF, and Purple #AF52DE. "
            "Dramatic foreshortening, Kirby crackle energy effects. "
            "Strong chiaroscuro shadows, action-packed visual energy."
        ),
        "affinities": {"gritty": 2, "urban": 2, "moody": 1, "exterior": 1, "dynamic": 2},
        "penalties": {"serene": -2, "peaceful": -2, "ethereal": -1},
    },
    "linocut": {
        "name": "Linocut Print",
        "prompt": (
            "Bold linocut reduction print with vivid color layers. "
            "Thick black outlines carved from linoleum block. "
            "Flat saturated color layers — Orange #FF9500, Green #34C759, Pink #FF2D55 — "
            "printed with slight misregistration for handmade quality. "
            "Visible carving marks and ink texture from roller application."
        ),
        "affinities": {"exterior": 3, "urban": 2, "nature": 2, "landscape_orient": 2,
                        "no_faces": 2, "cinematic": 1},
        "penalties": {"interior": -1},
    },
    "shinkai": {
        "name": "Makoto Shinkai",
        "prompt": (
            "In the style of Makoto Shinkai's anime films (Your Name, Weathering with You). "
            "Hyper-detailed backgrounds with extraordinary light rendering. "
            "Dramatic skies with volumetric clouds and god rays. "
            "Deep Blue #007AFF skies, Cyan #32ADE6 light shafts, Pink #FF2D55 sunset glow. "
            "Photorealistic detail meets anime aesthetic. Cinematic widescreen."
        ),
        "affinities": {"cinematic": 3, "exterior": 3, "golden": 3, "landscape_orient": 2,
                        "vast": 2, "ethereal": 2, "nostalgic": 1},
        "penalties": {"interior": -2, "gritty": -2, "dark": -1},
    },
    # ── BOLD/GRAPHIC STYLES ──────────────────────────────────────────────────

    "hugopratt": {
        "name": "Hugo Pratt / Corto Maltese",
        "prompt": (
            "In the style of Hugo Pratt's Corto Maltese graphic novels. "
            "Bold black ink with masterful use of negative space. "
            "Large areas of solid black contrasting with clean white. "
            "Confident, fluid brushstrokes — minimal but expressive. "
            "Pure black and white with rare flash of Indigo #5856D6."
        ),
        "affinities": {"exterior": 3, "moody": 3, "cinematic": 2, "urban": 2, "night": 3,
                        "no_faces": 2, "monochrome": 3, "dark": 2},
        "penalties": {"bright": -2, "colorful": -2, "peaceful": -1},
    },
    "sincity": {
        "name": "Sin City / Frank Miller",
        "prompt": (
            "In the style of Frank Miller's Sin City. "
            "Extreme high-contrast black and white — no midtones. "
            "Everything is pure black or blinding white. "
            "Rain-slicked surfaces, dramatic backlighting, noir atmosphere. "
            "Angular, brutal composition with one searing Red #FF3B30 accent."
        ),
        "affinities": {"night": 4, "dark": 4, "gritty": 3, "moody": 3, "urban": 3,
                        "cinematic": 2, "monochrome": 2},
        "penalties": {"bright": -3, "serene": -3, "peaceful": -2, "nature": -1},
    },
    "saulbass": {
        "name": "Saul Bass Poster",
        "prompt": (
            "In the style of Saul Bass movie poster design. "
            "Bold geometric shapes, sharp angles, limited flat color palette. "
            "Strong graphic silhouettes reduced to essential forms. "
            "Paper-cut aesthetic with torn edges and overlapping planes. "
            "Black, white, and Orange #FF9500 or Red #FF3B30 only."
        ),
        "affinities": {"urban": 3, "cinematic": 3, "dark": 2, "gritty": 2,
                        "monochrome": 1, "no_faces": 2},
        "penalties": {"nature": -1, "serene": -2, "ethereal": -2},
    },
    "banksy": {
        "name": "Banksy / Stencil Art",
        "prompt": (
            "In the style of Banksy stencil street art. "
            "High-contrast spray-painted stencil on raw concrete wall. "
            "Graphic black and white with one explosive accent — "
            "Red #FF3B30 or Pink #FF2D55 spray paint dripping. "
            "Sharp stencil edges with spray overshoot and drips. "
            "Urban decay meets precise graphic design."
        ),
        "affinities": {"urban": 4, "gritty": 3, "exterior": 2, "dark": 1,
                        "chaotic": 2, "no_faces": 1},
        "penalties": {"serene": -2, "peaceful": -2, "dreamy": -2, "nature": -1},
    },
    "mucha": {
        "name": "Alphonse Mucha / Art Nouveau",
        "prompt": (
            "In the style of Alphonse Mucha's Art Nouveau posters. "
            "Elegant flowing lines with ornamental botanical patterns. "
            "Purple #AF52DE, Mint #00C7BE, and Indigo #5856D6 jewel tones "
            "on pure white with strong black outlines. "
            "Intricate pattern work, luxurious poster-like composition."
        ),
        "affinities": {"exterior": 2, "nature": 2, "golden": 2, "ethereal": 2,
                        "nostalgic": 2, "dreamy": 1},
        "penalties": {"gritty": -2, "dark": -1, "chaotic": -2},
    },
    # ── FULL-SPECTRUM COLOR ────────────────────────────────────────────────
    "technicolor": {
        "name": "Technicolor Pop",
        "prompt": (
            "Explosive full-spectrum color illustration. "
            "Every surface saturated to maximum — electric Red #FF3B30, "
            "vivid Blue #007AFF, blazing Orange #FF9500, acid Green #34C759, "
            "hot Pink #FF2D55, deep Purple #AF52DE, brilliant Cyan #32ADE6. "
            "Thick black outlines contain fields of pure flat saturated color. "
            "Pop art meets Fauvist explosion — Matisse cutouts on steroids. "
            "No white space, no muted tones, no subtlety. "
            "Every square inch radiates color. Visible brush texture and ink grain."
        ),
        "color_directive": (
            "CRITICAL COLOR RULE — MAXIMUM SATURATION. "
            "Use the FULL Apple palette simultaneously: Red #FF3B30, Orange #FF9500, "
            "Green #34C759, Mint #00C7BE, Teal #30B0C7, Cyan #32ADE6, Blue #007AFF, "
            "Indigo #5856D6, Purple #AF52DE, Pink #FF2D55. "
            "Black outlines for structure ONLY — not as dominant fill. "
            "NEVER use beige, cream, yellow, ochre, sepia, warm brown, pastel, or muted tones. "
            "Fill the entire canvas edge to edge. No border, frame, or vignette."
        ),
        "affinities": {"exterior": 3, "bright": 4, "colorful": 3, "vibrant": 3,
                        "playful": 2, "urban": 2, "nature": 2, "energetic": 2},
        "penalties": {"dark": -3, "monochrome": -4, "moody": -2, "night": -2},
    },
}

# Mood → style affinity boosts (from Gemma mood analysis)
MOOD_STYLE_MAP = {
    "dreamy": {"shinkai": 3, "mucha": 2, "linocut": 1},
    "serene": {"ukiyoe": 3, "sumie": 3, "woodcut": 1},
    "peaceful": {"sumie": 2, "ukiyoe": 2, "woodcut": 1},
    "nostalgic": {"shinkai": 3, "scraperboard": 2, "woodcut": 1},
    "melancholic": {"shinkai": 3, "sumie": 2, "scraperboard": 2, "batman": 1},
    "moody": {"batman": 3, "gonzo": 2, "sincity": 3, "hugopratt": 2, "marvel": 1},
    "gritty": {"gonzo": 3, "sincity": 3, "banksy": 2, "marvel": 2, "batman": 1},
    "mysterious": {"batman": 3, "sincity": 2, "sumie": 2, "hugopratt": 2, "gonzo": 1},
    "dramatic": {"sincity": 3, "shinkai": 2, "batman": 2, "saulbass": 2, "marvel": 2},
    "whimsical": {"linocut": 3, "mucha": 2},
    "vibrant": {"technicolor": 4, "linocut": 3, "marvel": 2, "shinkai": 1},
    "ethereal": {"shinkai": 3, "mucha": 2, "linocut": 1},
    "energetic": {"technicolor": 3, "marvel": 3, "gonzo": 2, "banksy": 1, "archer": 1},
    "contemplative": {"sumie": 3, "scraperboard": 2, "ukiyoe": 2, "hugopratt": 1},
    "warm": {"technicolor": 2, "shinkai": 2, "linocut": 2, "mucha": 1},
    "cold": {"sincity": 3, "batman": 2, "scraperboard": 2, "sumie": 1},
    "playful": {"technicolor": 3, "linocut": 3, "archer": 2, "banksy": 1},
    "cinematic": {"saulbass": 3, "shinkai": 3, "sincity": 2, "batman": 2, "hugopratt": 1},
    "dark": {"sincity": 4, "batman": 3, "hugopratt": 2, "gonzo": 2},
    "bright": {"technicolor": 4, "linocut": 3, "shinkai": 2, "saulbass": 1},
    "tender": {"shinkai": 2, "sumie": 2, "woodcut": 1},
    "lonely": {"shinkai": 3, "hugopratt": 2, "sumie": 2, "sincity": 1, "batman": 1},
    "chaotic": {"gonzo": 4, "banksy": 3, "marvel": 2},
    "zen": {"sumie": 4, "ukiyoe": 2},
    "urban": {"banksy": 4, "archer": 3, "sincity": 2, "batman": 2, "gonzo": 1},
    "retro": {"saulbass": 3, "archer": 3, "marvel": 2, "mucha": 1},
}

# Gemma cartoon_style → our style key mapping
CARTOON_STYLE_MAP = {
    "studio ghibli": "ghibli",
    "ghibli": "ghibli",
    "miyazaki": "ghibli",
    "makoto shinkai": "shinkai",
    "shinkai": "shinkai",
    "your name": "shinkai",
    "pixar": "linocut",
    "disney": "linocut",
    "3d render": "linocut",
    "comic book": "marvel",
    "marvel": "marvel",
    "manga": "marvel",
    "anime": "shinkai",
    "watercolor": "sumie",
    "ink wash": "sumie",
    "sumi-e": "sumie",
    "ukiyo-e": "ukiyoe",
    "woodblock": "ukiyoe",
    "moebius": "woodcut",
    "ligne claire": "woodcut",
    "european comic": "woodcut",
    "noir": "batman",
    "dark": "batman",
    "pop art": "technicolor",
    "vector": "archer",
    "vintage cartoon": "archer",
    "cartoon network": "archer",
    "concept art": "shinkai",
    "graphic novel": "gonzo",
    "sin city": "sincity",
    "frank miller": "sincity",
    "noir": "sincity",
    "stencil": "banksy",
    "street art": "banksy",
    "graffiti": "banksy",
    "poster": "saulbass",
    "art nouveau": "mucha",
    "mucha": "mucha",
    "corto maltese": "hugopratt",
    "hugo pratt": "hugopratt",
    "fauvist": "technicolor",
    "colorful": "technicolor",
}
