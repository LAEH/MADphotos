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
DEAD_MIN_REVIEWS = 12       # need this many reviews before declaring dead (was 15)
STRUGGLING_THRESHOLD = 0.20 # <20% rate = struggling — heavy penalty but not excluded
STRUGGLING_MIN_REVIEWS = 10 # need this many reviews before declaring struggling
STRUGGLING_PENALTY = -5.0   # score penalty for struggling styles
EXPLORE_RATE = 0.20         # 20% chance slot 2 picks an undertested style
EXPLORE_MAX_REVIEWS = 5     # styles with fewer reviews than this are "undertested"
EXPLORE_MIN_RATE = 0.0      # don't explore styles with 0% and ≥3 reviews
EXPLORE_MIN_RATE_REVIEWS = 3
PERFORMANCE_CENTER = 0.45   # median acceptance rate — neutral point
PERFORMANCE_SCALE = 12.0    # multiplier for rate → score conversion (was 10)
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

# Global color directive — loose guidance, NOT prescriptive hex codes.
# Learned from 950+ reviews: user accepts dark/monochrome with organic color accents.
# Forced systematic colors (cyan, teal, red every time) feel artificial.
COLOR_DIRECTIVE = (
    "COLOR: The image should be dominated by deep blacks and strong whites. "
    "If color appears, let it arise naturally from the subject and style — "
    "one or two vivid accents that feel organic, not forced. "
    "NEVER use beige, cream, yellow, ochre, sepia, warm brown, pastel, or muted earth tones. "
    "Textures matter: ink grain, paper fiber, spray stipple, brush drag, carved relief. "
    "NEVER add any border, frame, mat, edge decoration, or vignette. Fill the entire canvas edge to edge."
)

# Salmon/coral/khaki hue ranges to avoid (dominant_hue in degrees)
# Salmon/coral: ~0-20°, Khaki: ~45-65°
REJECTED_HUE_RANGES = [(0, 20), (45, 65)]

# Style families — ensures pick_styles chooses diversity
FAMILIES = {
    # archer: retired — "comic"
    "batman": "comic",
    # marvel: retired — "comic"
    "gonzo": "ink",
    "sumie": "ink",
    "ukiyoe": "trad",
    "woodcut": "print",
    "scraperboard": "engrave",
    "linocut": "print",
    # shinkai: retired — "shinkai"
    "hugopratt": "ink",
    "sincity": "noir",
    "saulbass": "poster",
    "banksy": "stencil",
    "mucha": "nouveau",
    "technicolor": "pop",
    "charcoal": "charcoal",
    "stainedglass": "glass",
    "papercut": "paper",
    "wildstyle": "graffiti",
    "throwup": "graffiti",
    "wheatpaste": "street",
    "sprayabstract": "spray",
    "boldink": "ink",
    "minpunk": "punk",
    "malevich": "abstract",
    "risograph": "riso",
    "etching": "engrave",
    # Round 3 — wild paradigms
    "thermal": "scientific",
    "acidetch": "industrial",
    "azulejo": "ceramic",
    "sorayama": "airbrush",
    "brutalist": "sculpture",
    "nitratedecay": "decay",
    "sovietmosaic": "mosaic",
    "vectorcrt": "crt",
    "embroidery": "textile",
    "frost": "crystal",
    "kintsugi": "kintsugi",
    "verdigris": "patina",
    "shadowpuppet": "puppet",
    "circuitboard": "electronic",
    "plasma": "electric",
    "luminol": "forensic",
    "geological": "geology",
    "rorschach": "psych",
    "nebula": "astro",
    "basrelief": "relief",
}

# ── 10-style library ────────────────────────────────────────────────────────

STYLES = {
    # Archer retired — 15% acceptance (20 reviews). Flat vector flattens photos.
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
    # Marvel retired — 19% acceptance (16 reviews). Halftone/comic flattens photos.
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
    # Shinkai retired — 0% acceptance (6 reviews). Anime aesthetic doesn't work with real photos.
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
    # ── EXPERIMENTAL STYLES (round 2 — surprise paradigms) ──────────────
    #
    # Round 1 failed: kollwitz 12%, constructivist 0%, punkzine 0%, cyanotype 0%
    # Lesson: dark-on-dark is boring. The SURPRISE creates the value.
    # Winners love: bold outlines + saturated color pops + graphic power + texture
    #
    # Round 2 strategy: visual paradigms that don't exist in traditional art.
    # Unexpected pairings. Things you've never seen applied to photography.

    "charcoal": {
        "name": "Charcoal on Paper",
        "prompt": (
            "Raw charcoal drawing on heavyweight white paper. "
            "Smudged, grainy, tactile — you can feel the charcoal dust. "
            "Deep velvety blacks rubbed into the paper grain. "
            "Aggressive mark-making: broad strokes, finger smudges, eraser lifts. "
            "High contrast with luminous white paper showing through. "
            "The physicality of working with hands — raw, immediate, unrefined. "
            "Pure black charcoal on white, with one ghost of Indigo #5856D6 conte crayon."
        ),
        "affinities": {"moody": 4, "dark": 3, "monochrome": 3, "dramatic": 2,
                        "interior": 2, "no_faces": 2, "cinematic": 2, "night": 2},
        "penalties": {"bright": -2, "colorful": -3, "playful": -2},
    },
    "stainedglass": {
        "name": "Stained Glass Cathedral",
        "prompt": (
            "Gothic cathedral stained glass window — the scene rendered in jewel-toned "
            "translucent glass panels separated by thick black lead came lines. "
            "Light floods through saturated glass: deep ruby, sapphire, emerald, amethyst. "
            "Each color panel glows with backlit luminosity as if the sun is behind it. "
            "The black lead framework creates bold graphic structure. "
            "Medieval craftsmanship meets explosive color — Notre-Dame on fire with light."
        ),
        "affinities": {"exterior": 3, "nature": 3, "serene": 2, "dramatic": 3,
                        "cinematic": 2, "ethereal": 3, "landscape_orient": 2,
                        "bright": 2, "colorful": 2, "no_faces": 1},
        "penalties": {"gritty": -1},
    },
    "papercut": {
        "name": "Paper Cut Shadowbox",
        "prompt": (
            "Multi-layered paper cut diorama — the scene built from stacked layers "
            "of laser-cut paper creating dramatic depth with real shadows between layers. "
            "Pure white paper layers in front, graduating to deep black at the back. "
            "Sharp geometric edges, architectural precision, dramatic parallax depth. "
            "Real shadows cast between paper layers create natural gradients. "
            "One or two accent layers in a vivid color that fits the scene. "
            "The craft of Bovey Lee paper cutting meets theatrical shadow boxes. "
            "Everything has crisp cut edges — nothing painted, everything carved from paper."
        ),
        "affinities": {"exterior": 3, "nature": 3, "landscape_orient": 3, "cinematic": 2,
                        "serene": 2, "dramatic": 2, "architectural": 2, "no_faces": 2},
        "penalties": {"gritty": -1, "chaotic": -2},
    },
    # ── STREET ART / GRAFFITI ──────────────────────────────────────────────
    "wildstyle": {
        "name": "Wildstyle Graffiti",
        "prompt": (
            "Wildstyle graffiti — complex interlocking angular letterforms that dissolve "
            "into abstract shapes. Arrows, connections, and extensions explode outward. "
            "Thick black outlines with sharp geometric fills. "
            "Spray paint on raw concrete wall — visible overspray halos, drip runs, cap splatter. "
            "Colors chosen by the wall and the moment — whatever cans are in the bag. "
            "The energy of painting fast at night. Every line has velocity and intention. "
            "Not pretty, not clean — alive. The wall texture shows through the paint."
        ),
        "affinities": {"urban": 5, "gritty": 4, "chaotic": 3, "energetic": 3,
                        "dark": 2, "night": 2, "exterior": 3, "moody": 1},
        "penalties": {"serene": -2, "peaceful": -3, "nature": -2, "ethereal": -2},
    },
    "throwup": {
        "name": "Throw-Up / Bubble",
        "prompt": (
            "The scene rendered as a massive throw-up graffiti mural on a raw concrete wall. "
            "Fat chrome silver spray paint fill with thick black outline — every form is a bubble letter shape. "
            "The image subjects become bold, chunky, rounded graffiti shapes. "
            "Heavy black outline with visible overspray halo around every edge. "
            "Drips running down from the bottom of each shape — gravity pulling wet paint. "
            "Concrete wall texture visible in gaps and through thin coverage areas. "
            "The urgency of painting fast — uneven chrome coverage, overlapping passes. "
            "One accent: electric Blue #007AFF or Red #FF3B30 dripping from a tag."
        ),
        "affinities": {"urban": 5, "gritty": 3, "exterior": 3, "dark": 2,
                        "moody": 2, "night": 2, "chaotic": 1},
        "penalties": {"serene": -3, "peaceful": -3, "nature": -2, "ethereal": -3},
    },
    "wheatpaste": {
        "name": "Wheatpaste Poster",
        "prompt": (
            "Wheatpaste street poster — the image printed on cheap paper and glued to a wall. "
            "Layers of older torn posters visible underneath. Paper peeling at the edges. "
            "High-contrast black and white print with raw halftone dots. "
            "Weathered by rain — ink bleeding, paper bubbling, paste cracking. "
            "The archaeology of a city wall: overlapping messages, torn fragments, time. "
            "JR or Shepard Fairey aesthetic — bold graphic portrait or scene on urban surface."
        ),
        "affinities": {"urban": 4, "gritty": 4, "moody": 3, "exterior": 3,
                        "dramatic": 2, "dark": 2, "cinematic": 2, "no_faces": 1},
        "penalties": {"serene": -2, "peaceful": -2, "nature": -1, "bright": -1},
    },
    "sprayabstract": {
        "name": "Spray Paint Layers",
        "prompt": (
            "Abstract spray paint on concrete — layers of color built up and partially covered. "
            "Each layer a different pass: mist, solid fill, drip, splatter, stencil edge. "
            "The archaeology of the wall — colors bleeding through from beneath. "
            "Matte spray finish on rough concrete texture. "
            "Not tagging, not letters — the image itself rendered in spray paint physics. "
            "Cap effects: fat caps for floods, skinny caps for detail lines. "
            "The paint does what spray paint does — clouds, runs, bleeds, hard edges."
        ),
        "affinities": {"urban": 4, "gritty": 3, "chaotic": 3, "moody": 3,
                        "dark": 2, "exterior": 3, "dramatic": 2, "energetic": 2},
        "penalties": {"serene": -2, "peaceful": -2, "nature": -1},
    },
    # ── MINIMALIST / ABSTRACT ──────────────────────────────────────────────
    "boldink": {
        "name": "Bold Ink Drawing",
        "prompt": (
            "Bold black ink drawing with confident, expressive linework. "
            "Mix of precise contours and loose gestural strokes. "
            "Strong contrast between black ink and white paper. "
            "Crosshatching and stippling for tonal depth. "
            "Raw, immediate quality with artistic energy. "
            "Minimal color — primarily monochrome with occasional ink wash accents."
        ),
        "affinities": {"monochrome": 4, "moody": 3, "dark": 3, "cinematic": 2,
                        "exterior": 2, "no_faces": 2, "gritty": 2, "urban": 2},
        "penalties": {"bright": -2, "colorful": -2, "playful": -1},
    },
    "minpunk": {
        "name": "Minimalist Punk",
        "prompt": (
            "Punk zine collage — photocopied to death, Xerox-degraded, cut and reassembled. "
            "Ransom-note aesthetic: torn paper fragments, visible tape, staple marks. "
            "Cheap photocopy grain — every generation of copy adds more contrast and artifacts. "
            "Black toner on white A4, maybe one harsh red or pink scream of color. "
            "Jamie Reid meets Crass Records. Anti-design that's more powerful than design. "
            "Deliberately crude, deliberately raw. Safety-pin energy. "
            "The image torn apart and stapled back together on a zine page."
        ),
        "affinities": {"urban": 4, "gritty": 5, "dark": 3, "moody": 3,
                        "chaotic": 4, "no_faces": 1, "monochrome": 2, "night": 2},
        "penalties": {"serene": -3, "peaceful": -3, "nature": -2, "ethereal": -3, "bright": -2},
    },
    "malevich": {
        "name": "Suprematist / Malevich",
        "prompt": (
            "Kazimir Malevich Suprematist composition — the photograph's essence "
            "abstracted into pure geometric forms floating on white space. "
            "Circles, squares, rectangles, crosses, and triangles in dynamic diagonal arrangement. "
            "Black, deep red, deep blue, and yellow on infinite white. "
            "No representation — only the geometric DNA of the original image. "
            "Each shape has weight, velocity, and tension against the others. "
            "The spiritual dimension of pure form. Painted with visible brushstrokes on canvas texture."
        ),
        "affinities": {"exterior": 3, "cinematic": 2, "dramatic": 3, "urban": 2,
                        "monochrome": 2, "landscape_orient": 2, "no_faces": 3,
                        "vast": 2, "architectural": 3, "minimal": 2},
        "penalties": {"faces": -2, "faces_many": -3, "chaotic": -1},
    },
    # ── NEW: texture-heavy styles that match winning pattern ──────────────
    "risograph": {
        "name": "Risograph Print",
        "prompt": (
            "Risograph print — the scene reproduced in 2-3 color layers with deliberate misregistration. "
            "Soy-based ink on uncoated paper — visible ink grain, dot pattern, paper fiber. "
            "Each color layer slightly offset, creating halftone moiré and accidental overlaps. "
            "Limited palette: one layer of deep black, one of fluorescent Pink #FF2D55 "
            "or electric Blue #007AFF, and one of Gold #FF9500 or Green #34C759. "
            "The beauty of imperfect mechanical reproduction — ink pooling in flat areas, "
            "starving in gradients. Cheap but gorgeous. Zine culture meets fine printing. "
            "Raw uncoated paper texture visible everywhere. Edge-to-edge, no border."
        ),
        "affinities": {"urban": 3, "moody": 2, "exterior": 2, "gritty": 2,
                        "no_faces": 2, "cinematic": 1, "monochrome": 1, "dark": 1},
        "penalties": {"ethereal": -1, "peaceful": -1},
    },
    "etching": {
        "name": "Copper Etching",
        "prompt": (
            "Copper plate etching — acid-bitten lines on metal, printed on dampened cotton rag paper. "
            "Fine crosshatching builds tone: dense hatching in shadows, open lines in highlights. "
            "The mark of the needle — every line deliberate, every crosshatch adding depth. "
            "Pure black ink pressed into white paper with slight plate emboss visible. "
            "Rembrandt-level mastery of light and dark through line weight alone. "
            "Areas of aquatint for tonal gradients — the acid eating copper in controlled bursts. "
            "Plate tone in the margins. The physicality of intaglio printing."
        ),
        "affinities": {"monochrome": 4, "moody": 3, "dark": 3, "cinematic": 2,
                        "exterior": 2, "night": 2, "no_faces": 2, "dramatic": 2},
        "penalties": {"bright": -2, "colorful": -3, "playful": -1},
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

    # ── ROUND 3: WILD PARADIGMS ─────────────────────────────────────────────
    #
    # Every territory below is NEW — no ink, no print, no comic, no street art.
    # Scientific imaging, material simulation, decay, natural phenomena,
    # electronic, geological, theatrical, psychological.
    #
    # Learned rule: dark-on-dark is boring. The SURPRISE creates the value.
    # Winners love: bold graphic identity + texture + high contrast + vivid accents.

    "thermal": {
        "name": "Thermal / FLIR Imaging",
        "prompt": (
            "Thermal infrared camera image — FLIR false-color heat signature visualization. "
            "Cold regions in deep black and purple, cool areas in blue, "
            "warm zones in vivid red and orange, hot spots blazing yellow and white. "
            "Scientific overlay aesthetic: temperature gradient, scan lines. "
            "Every surface remapped by its heat emission — faces glow, engines burn, "
            "shadows are ice-cold voids. The image as thermal intelligence data. "
            "Crisp scientific precision with alien beauty."
        ),
        "color_directive": (
            "COLOR: FALSE-COLOR THERMAL PALETTE ONLY. "
            "Cold = deep black → deep purple → Blue #007AFF. "
            "Warm = vivid Red #FF3B30 → Orange #FF9500 → blazing yellow → white. "
            "No natural colors — everything remapped by temperature. "
            "Background is cold black void. Hot subjects glow. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"exterior": 3, "night": 3, "urban": 3, "no_faces": 1,
                        "cinematic": 2, "dark": 2},
        "penalties": {"serene": -1, "ethereal": -2},
    },
    "acidetch": {
        "name": "Acid-Etched Steel Plate",
        "prompt": (
            "Industrial acid-etched steel plate — ferric chloride biting into cold-rolled steel. "
            "The image burned into bare metal by controlled chemical corrosion. "
            "Raw steel gray in highlights, deep black oxidation in shadows. "
            "Acid bite marks, etch resist edges, chemical tide lines where acid pooled. "
            "Heavy industrial aesthetic — welding shop, foundry, shipyard. "
            "One area of electric Blue #007AFF heat tint where steel was torched. "
            "The metal's crystalline grain structure visible in polished areas."
        ),
        "affinities": {"urban": 4, "gritty": 4, "dark": 3, "moody": 3,
                        "monochrome": 3, "no_faces": 2, "night": 2},
        "penalties": {"serene": -2, "peaceful": -2, "ethereal": -3, "bright": -2},
    },
    "azulejo": {
        "name": "Azulejo / Portuguese Tile",
        "prompt": (
            "Hand-painted Portuguese azulejo tile panel — cobalt blue on white tin-glazed ceramic. "
            "The scene rendered as a traditional Lisbon tile mural. "
            "Bold blue brushstrokes on pure white glaze, visible tile grid (15cm squares). "
            "Baroque ornamental borders, scrollwork, floral corner pieces. "
            "Some tiles cracked, grout lines visible, centuries of weather on the wall. "
            "The deep ultramarine blue has that specific azulejo richness — "
            "between navy and cobalt, slightly uneven from hand-painting."
        ),
        "color_directive": (
            "COLOR: COBALT BLUE AND WHITE ONLY. "
            "Deep ultramarine cobalt blue brushstrokes on pure white glaze. "
            "No other colors. The entire image in shades of one rich cobalt blue on white. "
            "Visible tile grid lines in pale gray. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"exterior": 4, "serene": 2, "landscape_orient": 3,
                        "urban": 2, "no_faces": 2},
        "penalties": {"gritty": -1, "chaotic": -2, "dark": -2},
    },
    "sorayama": {
        "name": "Sorayama / Chrome Airbrush",
        "prompt": (
            "Hajime Sorayama chrome airbrush hyperrealism — everything rendered in liquid chrome. "
            "Mirror-perfect metal reflections, mercury pooling, chrome distortion. "
            "The subject becomes a chrome sculpture reflecting its environment. "
            "Razor-sharp highlights, deep metallic shadows, perfect gradients. "
            "1980s Japanese airbrush mastery — pin-up magazine meets industrial design. "
            "Chrome, silver, gunmetal gray — with one reflection of electric Blue #007AFF "
            "or hot Pink #FF2D55 bouncing off the metal surface."
        ),
        "affinities": {"cinematic": 3, "dark": 2, "urban": 3,
                        "monochrome": 2, "no_faces": 1},
        "penalties": {"serene": -1},
    },
    "brutalist": {
        "name": "Brutalist Concrete Relief",
        "prompt": (
            "The image carved as a relief sculpture in raw board-formed concrete. "
            "Béton brut — Tadao Ando meets Le Corbusier. "
            "The wood grain of the formwork imprinted in the cement surface. "
            "Deep-set relief with dramatic raking light from one side, casting long shadows. "
            "Everything is one material: raw concrete gray. "
            "Form defined entirely by depth and shadow. "
            "Monolithic, monumental, brutally honest. No paint, no color — "
            "just cement, shadow, and the memory of the wooden forms."
        ),
        "affinities": {"urban": 4, "monochrome": 3, "dark": 2,
                        "no_faces": 3, "exterior": 2},
        "penalties": {"bright": -2, "ethereal": -2},
    },
    "nitratedecay": {
        "name": "Nitrate Film Decay",
        "prompt": (
            "Decomposing nitrate film stock — the image eating itself alive. "
            "Chemical burns bubbling through the emulsion, silver halide crystals separating. "
            "Color dyes splitting into raw cyan, magenta, and yellow components. "
            "Portions of the frame dissolving into abstract chemical patterns. "
            "Film sprocket holes visible at edges, base buckling from heat damage. "
            "The beauty of entropy — a photograph from 1920 finally surrendering to chemistry. "
            "Where the image survives it's sharp; where it decays, pure abstraction."
        ),
        "color_directive": (
            "COLOR: Chemical decomposition palette. "
            "Where intact: high-contrast black and white with silver sheen. "
            "Where decaying: raw film dyes — Cyan #32ADE6, Magenta #FF2D55, "
            "Yellow #FF9500 — separating and bleeding into each other. "
            "Chemical burns in deep amber and black. "
            "The contrast between preserved and destroyed areas is the drama. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"monochrome": 3, "nostalgic": 4, "dark": 3, "moody": 3,
                        "cinematic": 3, "no_faces": 2},
        "penalties": {"bright": -1},
    },
    "sovietmosaic": {
        "name": "Soviet Metro Mosaic",
        "prompt": (
            "Monumental Soviet-era metro station tile mosaic. "
            "The scene rendered in thousands of small glass smalti tesserae — "
            "each tile a distinct square of vivid color, visible grout lines between. "
            "Bold, heroic composition — simplified geometric forms at massive scale. "
            "The palette of Soviet mosaics: deep red, gold, midnight blue, white, black. "
            "Tesserae set at slight angles to catch light differently — the surface shimmers. "
            "The grandeur of Mayakovskaya station meets monumental public art. "
            "Every form reduced to its essential geometry, every color pure and unmodulated."
        ),
        "color_directive": (
            "COLOR: SOVIET MOSAIC PALETTE. "
            "Deep Red #FF3B30, gold amber, midnight Blue #007AFF, "
            "pure white, and jet black. Each color as a distinct tile. "
            "No gradients — each tessera is one solid color. "
            "The overall effect is bold and graphic through color juxtaposition. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"urban": 3, "cinematic": 2, "exterior": 2,
                        "dark": 1, "monochrome": 1},
        "penalties": {"ethereal": -2, "peaceful": -1},
    },
    "vectorcrt": {
        "name": "Vector CRT / Retro Display",
        "prompt": (
            "Early 1980s vector CRT display — Atari Asteroids, Tempest, Battlezone. "
            "Glowing phosphor lines on pure black screen. No fill, no solid areas — "
            "the entire image is wireframe outlines made of light. "
            "Green or amber phosphor glow with characteristic bloom and afterimage. "
            "Scanline artifacts, slight phosphor trail persistence. "
            "The image reduced to its essential contour lines, rendered in light on void. "
            "The romance of early computer graphics — when every vertex was precious."
        ),
        "color_directive": (
            "COLOR: PHOSPHOR GREEN OR AMBER ON PURE BLACK. "
            "Primary: bright Green #34C759 phosphor glow (or amber Orange #FF9500). "
            "Background: absolute black (CRT off-state). "
            "Phosphor bloom creates soft halos around bright lines. "
            "No other colors. Everything is glowing lines on void. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"urban": 3, "night": 4, "dark": 4, "cinematic": 2,
                        "monochrome": 2, "no_faces": 2},
        "penalties": {"bright": -3, "serene": -2},
    },
    "embroidery": {
        "name": "Silk Embroidery on Black",
        "prompt": (
            "Traditional silk embroidery on black velvet ground — the image stitched "
            "thread by thread in luminous colored silk. "
            "Visible stitch direction: satin stitch for broad fills, split stitch for fine lines, "
            "French knots for texture, couching for outlines. "
            "The silk catches light — shimmering highlights where thread direction changes. "
            "Rich but limited palette: Ruby #FF2D55, Sapphire #007AFF, "
            "Emerald #34C759, and Gold thread accents on deep black velvet. "
            "The craft of 1000 hours of handwork — every stitch deliberate."
        ),
        "affinities": {"dark": 3, "moody": 2, "cinematic": 2,
                        "no_faces": 2, "dreamy": 2, "serene": 1},
        "penalties": {"gritty": -2, "chaotic": -2, "urban": -1},
    },
    "frost": {
        "name": "Frost Flowers on Black Glass",
        "prompt": (
            "Ice crystal formations on a dark window — frost flowers growing across black glass. "
            "Natural fractal branching: fern-like dendrites, feathered plumes, geometric hexagons. "
            "The image emerges from the crystalline structures as if frozen into the glass. "
            "Cold blue-white ice on near-black background — maximum contrast. "
            "Individual crystal facets catch light like diamonds. "
            "The mathematics of crystallization — each branch follows the hexagonal ice lattice. "
            "Breathtaking cold beauty. Nature's own graphic design."
        ),
        "affinities": {"monochrome": 3, "dark": 3, "serene": 3,
                        "no_faces": 3, "night": 2},
        "penalties": {"urban": -1, "gritty": -2},
    },
    "kintsugi": {
        "name": "Kintsugi / Gold Repair",
        "prompt": (
            "Kintsugi — the Japanese art of golden repair. "
            "The image rendered on dark ceramic, then shattered and reassembled "
            "with bright gold lacquer filling every crack. "
            "Dark stoneware fragments: deep black, charcoal, midnight blue glazes. "
            "Veins of pure gold running through the breaks — celebrating the damage. "
            "Some cracks thin as hair, others wide rivers of gold. "
            "Wabi-sabi: the beauty of imperfection, impermanence, incompleteness. "
            "The gold doesn't hide the breaks — it illuminates them."
        ),
        "color_directive": (
            "COLOR: DARK CERAMIC + BRIGHT GOLD ONLY. "
            "Ceramic shards in deep black, charcoal, midnight blue. "
            "Repair veins in bright metallic gold — NOT yellow, NOT amber — "
            "true metallic gold that catches light. "
            "High contrast between dark fragments and luminous gold cracks. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"dark": 4, "moody": 3, "monochrome": 2,
                        "cinematic": 2, "no_faces": 2, "night": 2},
        "penalties": {"bright": -2, "chaotic": -1},
    },
    "verdigris": {
        "name": "Verdigris / Oxidized Bronze",
        "prompt": (
            "Oxidized bronze sculpture — the vivid turquoise-green patina of verdigris "
            "spreading across dark metal. "
            "The image as a bronze relief, centuries of atmospheric exposure creating "
            "patterns of copper carbonate over dark oxidized metal. "
            "Rich Mint #00C7BE and Teal #30B0C7 verdigris against near-black bronze. "
            "Chemical weathering patterns: water streaks, sheltered dark areas, "
            "exposed green surfaces. Like the Statue of Liberty's transformation. "
            "The dignity of metal surrendering to atmosphere over decades."
        ),
        "affinities": {"exterior": 4, "monochrome": 2, "dark": 3,
                        "no_faces": 2, "urban": 2, "nostalgic": 2},
        "penalties": {"bright": -2},
    },
    "shadowpuppet": {
        "name": "Wayang / Shadow Puppet",
        "prompt": (
            "Indonesian wayang kulit shadow puppet theater — "
            "the scene rendered as intricate leather puppet silhouettes backlit against a white screen. "
            "Filigree-detailed cutwork in the leather: arabesques, perforations, jointed limbs. "
            "Where leather is solid: pure black silhouette. "
            "Where leather is thin: warm amber-gold translucency as light passes through. "
            "The screen glows with the warm light of an oil lamp behind. "
            "Bold black shapes with jewel-like perforated patterns letting golden light through."
        ),
        "color_directive": (
            "COLOR: SHADOW AND GOLDEN LIGHT ONLY. "
            "Silhouettes in pure black. Backlight glow in warm amber gold through translucent areas. "
            "Screen background: warm white with golden cast. "
            "Only two tones: black shadow and golden light passing through perforated leather. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"cinematic": 3, "dark": 3, "night": 3,
                        "moody": 2, "no_faces": 1, "exterior": 2},
        "penalties": {"bright": -2, "gritty": -1},
    },
    "circuitboard": {
        "name": "Circuit Board / PCB",
        "prompt": (
            "Printed circuit board — the image rendered as electronic schematic on PCB. "
            "Green solder mask substrate as the base. "
            "Copper traces forming the image: signal paths, ground planes, via holes. "
            "White silkscreen component labels and reference designators. "
            "Through-hole solder pads as bright silver points of light. "
            "IC footprints, resistor symbols, capacitor outlines embedded in the design. "
            "The aesthetics of electronics manufacturing — precision, density, function as beauty."
        ),
        "color_directive": (
            "COLOR: PCB GREEN + COPPER + WHITE. "
            "Base: dark Green #34C759 solder mask. "
            "Traces: copper bronze metallic tones forming the image. "
            "Labels: white silkscreen text. Solder: bright silver points. "
            "NEVER use red, pink, purple, or warm tones. "
            "The palette of real circuit boards only. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"urban": 3, "night": 2,
                        "no_faces": 3, "dark": 2, "monochrome": 1},
        "penalties": {"serene": -2, "ethereal": -3},
    },
    "plasma": {
        "name": "Plasma / Tesla Discharge",
        "prompt": (
            "Tesla coil electrical discharge — Lichtenberg figures forming the image. "
            "Branching plasma filaments like frozen lightning, fractal tree structures. "
            "Electric violet-blue and white-hot plasma arcs against pitch black void. "
            "The natural fractal geometry of electrical breakdown through air. "
            "Some branches thick and bright, others hair-thin and fading. "
            "Ball lightning glow at junction points. Ionized air creating purple halos. "
            "The terrifying beauty of high-voltage discharge — millions of volts rendered visible."
        ),
        "color_directive": (
            "COLOR: ELECTRIC PLASMA ON BLACK VOID. "
            "Background: absolute black. "
            "Plasma: vivid Purple #AF52DE → Blue #007AFF → white-hot core. "
            "Secondary glow: Cyan #32ADE6 ionization halos. "
            "No warm colors. Everything is cold electric discharge. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"dark": 4, "night": 4, "chaotic": 2,
                        "cinematic": 2, "no_faces": 2},
        "penalties": {"bright": -3, "serene": -2, "peaceful": -3},
    },
    "luminol": {
        "name": "Luminol / UV Forensic",
        "prompt": (
            "Forensic luminol photography — selective fluorescent glow on pitch black. "
            "The image revealed only where luminol reacts: electric blue chemiluminescence "
            "emerging from absolute darkness. "
            "Some areas blazing with fluorescent Blue #007AFF and Cyan #32ADE6 glow, "
            "other areas invisible — pure black void. "
            "The aesthetic of crime scene investigation: what the naked eye cannot see. "
            "Harsh forensic flash illuminating selective areas against total darkness. "
            "Clinical, revelatory, unsettling."
        ),
        "affinities": {"dark": 5, "night": 4, "moody": 4, "gritty": 3,
                        "cinematic": 3, "monochrome": 2, "no_faces": 2, "urban": 2},
        "penalties": {"bright": -4, "serene": -3, "peaceful": -3},
    },
    "geological": {
        "name": "Geological Cross-Section",
        "prompt": (
            "The image rendered as a polished geological cross-section — "
            "horizontal rock strata in mineral colors, sliced through the earth's crust. "
            "Banded agate aesthetic: layers of deep blue azurite, rusty red hematite, "
            "jade green malachite, obsidian black basalt, crystalline quartz white. "
            "Crystal formations growing in voids — amethyst geodes, calcite needles. "
            "Mineral veins cutting diagonally across strata — bright metallic ore. "
            "The drama of deep geological time compressed into visible layers."
        ),
        "color_directive": (
            "COLOR: MINERAL PALETTE. "
            "Strata in: deep Blue #007AFF azurite, rust Red #FF3B30 hematite, "
            "jade Green #34C759 malachite, obsidian black, crystalline white. "
            "Metallic veins in silver and copper. "
            "Crystal formations in Purple #AF52DE amethyst and clear quartz. "
            "Rich, saturated mineral colors — nothing muddy or muted. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"landscape_orient": 3, "exterior": 3,
                        "no_faces": 3, "dark": 2, "monochrome": 1},
        "penalties": {"urban": -1, "chaotic": -1},
    },
    "rorschach": {
        "name": "Rorschach Inkblot",
        "prompt": (
            "Rorschach inkblot test card — the image abstracted into a bilaterally symmetrical "
            "ink pattern folded on white card stock. "
            "Pure black ink dropped and pressed: the image recognizable but distorted "
            "by the mirror-fold symmetry. "
            "Organic ink spread: feathered edges where ink wicked into paper fibers, "
            "dense black centers, lighter gray periphery. "
            "The psychology of pareidolia — your brain finding the image in the blot. "
            "Pure black ink on pure white card. Nothing else."
        ),
        "affinities": {"monochrome": 5, "dark": 3, "moody": 3,
                        "no_faces": 2, "cinematic": 1},
        "penalties": {"bright": -2},
    },
    "nebula": {
        "name": "Nebula / Deep Space JWST",
        "prompt": (
            "James Webb Space Telescope deep space image — the scene reimagined as a cosmic nebula. "
            "Gas clouds, stellar nurseries, cosmic dust lanes in false-color palette. "
            "Pillars of creation: towering gas columns with bright stellar cores. "
            "Background: infinite black void dotted with point-source stars. "
            "JWST infrared false-color: Teal #30B0C7 gas, Magenta #FF2D55 star-forming regions, "
            "Gold #FF9500 dust lanes, deep Blue #007AFF molecular hydrogen. "
            "The sublime scale of cosmic structures — gas clouds light-years across."
        ),
        "color_directive": (
            "COLOR: JWST FALSE-COLOR ASTRONOMICAL PALETTE. "
            "Background: absolute black cosmic void with white point-source stars. "
            "Gas and nebula in: Teal #30B0C7, Magenta #FF2D55, "
            "deep Blue #007AFF, Gold #FF9500. "
            "Stars as brilliant white points. "
            "Rich, vivid false colors on black — like actual JWST images. "
            "NEVER add borders, frames, or vignettes. Fill edge to edge."
        ),
        "affinities": {"dark": 4, "night": 4, "vast": 4,
                        "exterior": 3, "cinematic": 3, "ethereal": 3, "no_faces": 3},
        "penalties": {"urban": -2, "gritty": -3},
    },
    "basrelief": {
        "name": "Bas-Relief / Carved Stone",
        "prompt": (
            "Classical bas-relief sculpture carved in pale limestone or marble. "
            "Low-relief carving: forms raised just millimeters above the flat background. "
            "Dramatic raking light from the left side, casting long shadows in carved channels. "
            "Everything is one material, one color — form defined entirely by light and shadow. "
            "Classical sculpture technique: soft tissue rendered with subtle undulations, "
            "drapery with sharp fold lines, architectural elements with geometric precision. "
            "The image as if carved by a Renaissance master — Donatello's stiacciato technique. "
            "Pale stone with deep carved shadows. Monumental, timeless, tactile."
        ),
        "affinities": {"monochrome": 4, "cinematic": 3, "exterior": 3,
                        "no_faces": 1, "serene": 2},
        "penalties": {"urban": -1, "gritty": -2, "chaotic": -2},
    },
}

# Mood → style affinity boosts (from Gemma mood analysis)
MOOD_STYLE_MAP = {
    "dreamy": {"stainedglass": 2, "papercut": 2, "sumie": 2, "mucha": 2, "linocut": 1},
    "serene": {"papercut": 3, "stainedglass": 2, "sumie": 3, "malevich": 2, "woodcut": 1},
    "peaceful": {"papercut": 3, "sumie": 2, "malevich": 2, "woodcut": 1},
    "nostalgic": {"wheatpaste": 3, "stainedglass": 2, "scraperboard": 2, "woodcut": 1, "charcoal": 2, "boldink": 2, "risograph": 3, "etching": 2},
    "melancholic": {"wheatpaste": 3, "charcoal": 3, "boldink": 3, "sumie": 2, "scraperboard": 2, "batman": 1, "sprayabstract": 2, "minpunk": 2},
    "moody": {"sprayabstract": 3, "wheatpaste": 2, "batman": 3, "gonzo": 2, "sincity": 3, "hugopratt": 2, "charcoal": 2, "boldink": 3, "minpunk": 2},
    "gritty": {"wildstyle": 4, "throwup": 3, "sprayabstract": 3, "gonzo": 3, "sincity": 3, "banksy": 2, "batman": 1, "minpunk": 4, "boldink": 2},
    "mysterious": {"sprayabstract": 2, "stainedglass": 2, "batman": 3, "sincity": 2, "sumie": 2, "hugopratt": 2, "charcoal": 2, "malevich": 2},
    "dramatic": {"stainedglass": 3, "wildstyle": 2, "sincity": 3, "batman": 2, "saulbass": 2, "malevich": 3, "boldink": 2},
    "whimsical": {"papercut": 3, "linocut": 3, "mucha": 2, "throwup": 1},
    "vibrant": {"technicolor": 4, "stainedglass": 4, "wildstyle": 3, "linocut": 3},
    "ethereal": {"stainedglass": 3, "papercut": 2, "mucha": 2, "malevich": 1},
    "energetic": {"wildstyle": 4, "throwup": 3, "technicolor": 3, "gonzo": 2, "banksy": 1, "sprayabstract": 3, "minpunk": 3},
    "contemplative": {"papercut": 3, "sumie": 3, "scraperboard": 2, "charcoal": 3, "malevich": 3, "boldink": 2, "etching": 3},
    "warm": {"stainedglass": 3, "technicolor": 2, "linocut": 2},
    "cold": {"sincity": 3, "batman": 2, "scraperboard": 2, "sprayabstract": 2, "malevich": 2},
    "playful": {"throwup": 3, "technicolor": 3, "stainedglass": 2, "linocut": 3, "banksy": 1},
    "cinematic": {"wheatpaste": 2, "stainedglass": 2, "saulbass": 3, "sincity": 2, "batman": 2, "hugopratt": 1, "boldink": 2},
    "dark": {"sprayabstract": 3, "sincity": 4, "batman": 3, "hugopratt": 2, "gonzo": 2, "charcoal": 3, "boldink": 3, "minpunk": 3},
    "bright": {"stainedglass": 3, "technicolor": 4, "wildstyle": 2, "linocut": 3, "saulbass": 1},
    "tender": {"papercut": 3, "sumie": 2, "woodcut": 1, "charcoal": 1},
    "lonely": {"wheatpaste": 3, "hugopratt": 2, "sumie": 2, "sincity": 1, "batman": 1, "charcoal": 2, "papercut": 2, "minpunk": 2, "malevich": 2},
    "chaotic": {"wildstyle": 5, "gonzo": 4, "banksy": 3, "sprayabstract": 3, "throwup": 2, "minpunk": 4},
    "zen": {"papercut": 3, "sumie": 4, "malevich": 3},
    "urban": {"wildstyle": 5, "throwup": 4, "sprayabstract": 4, "wheatpaste": 3, "banksy": 4, "sincity": 2, "batman": 2, "gonzo": 1, "minpunk": 3},
    "retro": {"wheatpaste": 3, "saulbass": 3, "stainedglass": 2, "mucha": 1, "minpunk": 2, "risograph": 3},
    "raw": {"sprayabstract": 4, "charcoal": 4, "wildstyle": 3, "gonzo": 2, "minpunk": 4, "boldink": 3},
    "industrial": {"sprayabstract": 3, "wildstyle": 2, "wheatpaste": 2, "batman": 1, "malevich": 2, "minpunk": 2},
    "desolate": {"wheatpaste": 3, "charcoal": 3, "sincity": 2, "scraperboard": 2, "sprayabstract": 2, "malevich": 2},
    "stark": {"malevich": 4, "boldink": 3, "sincity": 3, "minpunk": 2},
    "minimal": {"malevich": 4, "sumie": 3, "boldink": 2, "papercut": 2},
    "abstract": {"malevich": 5, "sprayabstract": 2, "wildstyle": 1},
    "powerful": {"boldink": 4, "sincity": 3, "wildstyle": 3, "malevich": 2, "minpunk": 2},
    "intense": {"boldink": 3, "sincity": 3, "minpunk": 3, "wildstyle": 2, "gonzo": 2},
    "rebellious": {"minpunk": 5, "wildstyle": 4, "throwup": 3, "banksy": 3, "gonzo": 2},
    "somber": {"charcoal": 3, "boldink": 3, "malevich": 2, "sincity": 2, "wheatpaste": 2, "etching": 3},
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
    "charcoal": "charcoal",
    "conte": "charcoal",
    "sketch": "charcoal",
    "stained glass": "stainedglass",
    "cathedral": "stainedglass",
    "vitrail": "stainedglass",
    "paper cut": "papercut",
    "paper craft": "papercut",
    "diorama": "papercut",
    "graffiti": "wildstyle",
    "wildstyle": "wildstyle",
    "tagging": "throwup",
    "bubble letters": "throwup",
    "throw up": "throwup",
    "wheatpaste": "wheatpaste",
    "poster art": "wheatpaste",
    "shepard fairey": "wheatpaste",
    "obey": "wheatpaste",
    "spray paint": "sprayabstract",
    "aerosol": "sprayabstract",
    "bold ink": "boldink",
    "ink drawing": "boldink",
    "expressive ink": "boldink",
    "brush ink": "boldink",
    "punk": "minpunk",
    "zine": "minpunk",
    "xerox": "minpunk",
    "photocopy": "minpunk",
    "collage": "minpunk",
    "ransom": "minpunk",
    "malevich": "malevich",
    "suprematis": "malevich",
    "geometric abstract": "malevich",
    "constructivis": "malevich",
    "abstract": "malevich",
    "art deco": "saulbass",
    "hopper": "boldink",
    "syd mead": "malevich",
    "risograph": "risograph",
    "riso": "risograph",
    "zine print": "risograph",
    "etching": "etching",
    "engraving": "etching",
    "intaglio": "etching",
    "rembrandt": "etching",
    "dürer": "etching",
    "durer": "etching",
    "crosshatch": "etching",
    # Round 3 — wild paradigm mappings
    "chrome": "sorayama",
    "metallic": "sorayama",
    "airbrush": "sorayama",
    "retro computer": "vectorcrt",
    "tron": "vectorcrt",
    "wireframe": "vectorcrt",
    "mosaic": "sovietmosaic",
    "tile": "azulejo",
    "ceramic": "azulejo",
    "portuguese": "azulejo",
    "embroidery": "embroidery",
    "textile": "embroidery",
    "needlework": "embroidery",
    "circuit": "circuitboard",
    "electronic": "circuitboard",
    "space": "nebula",
    "cosmic": "nebula",
    "nebula": "nebula",
    "jwst": "nebula",
    "shadow puppet": "shadowpuppet",
    "wayang": "shadowpuppet",
    "silhouette": "shadowpuppet",
    "relief": "basrelief",
    "sculpture": "basrelief",
    "carved stone": "basrelief",
    "kintsugi": "kintsugi",
    "gold repair": "kintsugi",
    "wabi sabi": "kintsugi",
    "thermal": "thermal",
    "heat map": "thermal",
    "flir": "thermal",
    "frost": "frost",
    "ice crystal": "frost",
    "oxidized": "verdigris",
    "patina": "verdigris",
    "bronze": "verdigris",
    "inkblot": "rorschach",
    "rorschach": "rorschach",
    "acid etch": "acidetch",
    "corroded": "acidetch",
    "industrial metal": "acidetch",
    "concrete": "brutalist",
    "brutalist": "brutalist",
    "brutalism": "brutalist",
    "film decay": "nitratedecay",
    "nitrate": "nitratedecay",
    "decomposing film": "nitratedecay",
    "plasma": "plasma",
    "lightning": "plasma",
    "tesla": "plasma",
    "luminol": "luminol",
    "forensic": "luminol",
    "uv glow": "luminol",
    "geological": "geological",
    "mineral": "geological",
    "agate": "geological",
    "geode": "geological",
}

# ── Round 3 MOOD_STYLE_MAP extensions ──────────────────────────────────────
# Extend mood→style mapping with the 20 wild paradigm styles.
_MOOD_ROUND3 = {
    "dreamy": {"nebula": 3, "frost": 2, "embroidery": 2},
    "serene": {"frost": 3, "azulejo": 2, "basrelief": 2, "geological": 1},
    "peaceful": {"frost": 2, "azulejo": 2, "basrelief": 2},
    "nostalgic": {"nitratedecay": 4, "sovietmosaic": 2, "shadowpuppet": 2},
    "melancholic": {"nitratedecay": 3, "kintsugi": 3, "verdigris": 2},
    "moody": {"luminol": 3, "kintsugi": 2, "acidetch": 2, "nitratedecay": 2},
    "gritty": {"acidetch": 4, "circuitboard": 2, "thermal": 2},
    "mysterious": {"luminol": 4, "shadowpuppet": 3, "plasma": 2, "frost": 2},
    "dramatic": {"plasma": 3, "kintsugi": 3, "sovietmosaic": 2, "shadowpuppet": 2, "basrelief": 2},
    "whimsical": {"embroidery": 2},
    "vibrant": {"sovietmosaic": 3, "nebula": 3, "geological": 2},
    "ethereal": {"nebula": 4, "frost": 3, "embroidery": 2},
    "energetic": {"plasma": 3, "thermal": 2, "vectorcrt": 2},
    "contemplative": {"kintsugi": 3, "basrelief": 3, "geological": 2, "frost": 2},
    "warm": {"shadowpuppet": 3, "embroidery": 2, "sovietmosaic": 2},
    "cold": {"frost": 4, "luminol": 3, "thermal": 2, "acidetch": 2},
    "playful": {"azulejo": 2, "geological": 1},
    "cinematic": {"thermal": 2, "luminol": 3, "nitratedecay": 2, "sorayama": 2},
    "dark": {"luminol": 4, "plasma": 3, "kintsugi": 3, "acidetch": 3},
    "bright": {"azulejo": 2, "nebula": 2, "sovietmosaic": 2, "geological": 2},
    "tender": {"embroidery": 3, "kintsugi": 2, "frost": 1},
    "lonely": {"frost": 3, "luminol": 2, "verdigris": 2, "rorschach": 2},
    "chaotic": {"plasma": 3, "nitratedecay": 2},
    "zen": {"kintsugi": 3, "frost": 2, "basrelief": 2},
    "urban": {"circuitboard": 2, "acidetch": 2, "thermal": 2, "vectorcrt": 2},
    "retro": {"nitratedecay": 3, "vectorcrt": 3, "sovietmosaic": 2},
    "raw": {"acidetch": 3, "rorschach": 2},
    "industrial": {"acidetch": 4, "circuitboard": 3, "thermal": 2, "brutalist": 4},
    "desolate": {"frost": 3, "luminol": 2, "verdigris": 3, "nitratedecay": 2},
    "stark": {"rorschach": 3, "brutalist": 3, "thermal": 2},
    "minimal": {"rorschach": 3, "frost": 2, "basrelief": 2},
    "abstract": {"rorschach": 4, "plasma": 2},
    "powerful": {"brutalist": 3, "plasma": 2, "sorayama": 2, "sovietmosaic": 2},
    "intense": {"plasma": 3, "luminol": 2, "thermal": 2},
    "rebellious": {"acidetch": 2, "vectorcrt": 1},
    "somber": {"kintsugi": 3, "verdigris": 2, "nitratedecay": 2, "basrelief": 2},
}
for _mood, _boosts in _MOOD_ROUND3.items():
    if _mood in MOOD_STYLE_MAP:
        MOOD_STYLE_MAP[_mood].update(_boosts)
    else:
        MOOD_STYLE_MAP[_mood] = _boosts
