# MADphotos

Photo curation and exploration project with two main components:

## Architecture

**Show** — Public-facing photo experience
- Path: `frontend/show/` (React 18 + TypeScript + Vite 6 + Tailwind v4 + Zustand)
- Source: `frontend/show/src/`
- Build output: `frontend/show/dist/`
- URL: https://madphotos.laeh.ai
- 6 interactive views for exploring curated photos
- Deployed to Firebase hosting `laeh-madphotos`

**System** — Internal dashboard and monitoring
- Path: `frontend/system/` (React + TypeScript)
- URL: https://madphotos.laeh.ai/system (static snapshot at deploy time)
- Project info, pipeline status, experiments, database overview
- Built to `frontend/show/dist/system/` at deploy time
- Local dev with live data: `python3 backend/serve_show.py` → http://localhost:3000/system

**System Experiments:**
- **Gemma** — Gemma model experiments
- **Mosaics** — Photo mosaic generation and viewing
- **Cartoon** — AI cartoon variant testing
- **Blind Test** — A/B testing for enhanced images

## Key paths
- DB: `images/mad_photos.db`
- Show source: `frontend/show/src/`
- Show build: `frontend/show/dist/`
- System app: `frontend/system/` (source) → `frontend/show/dist/system/` (built)
- Static data: `frontend/show/public/data/` (picks.json, stats.json, etc.)
- Firebase project: `laeh380to760`

## Show Source Structure
```
frontend/show/src/
├── main.tsx, App.tsx, index.css, tokens.css, shared.css
├── vite-env.d.ts
├── types/photo.ts
├── store/appStore.ts          # Zustand store (photos, lightbox, timers)
├── lib/                       # firebase, imageLoading, performanceTier, colorUtils, utils
├── hooks/                     # useTheme, useViewCleanup
├── components/
│   ├── layout/                # Shell, FloatingNav, SideMenu, ThemeToggle, experiences
│   └── ui/                    # Lightbox, ProgressiveImg, GlassTag, PaletteDots
└── views/
    ├── ColorsView.tsx + .css
    ├── CaptionView.tsx + .css
    ├── BentoView.tsx + .css
    ├── BoomView.tsx + .css
    ├── GameView.tsx + .css
    └── IsitView.tsx + .css + isit/{IsitSwipe.ts, IsitMinimap.tsx, IsitPills.tsx}
```

## Development

**Show dev server (Vite):**
```bash
cd frontend/show && npm run dev
# http://localhost:5173
```

**System only (Vite dev server):**
```bash
cd frontend/system && npm run dev
# http://localhost:5173 (live data via /api/* endpoints)
```

**Local dev with live data:**
```bash
python3 backend/serve_show.py
# Show: http://localhost:3000
# System (live): http://localhost:3000/system
```

## Build

```bash
cd frontend/show && npx vite build
```

Lazy-loaded views produce per-view JS + CSS chunks. Firebase SDK is split into its own chunk.

## Deploy

**Full sync + deploy:**
```bash
python3 backend/firestore_sync.py
```

What it does:
1. Pulls 5 Firestore collections → local SQLite (tinder-votes, couple-likes, couple-approves, couple-rejects, picks-votes)
2. Regenerates `picks.json` (tinder accepts minus picks rejects)
3. Regenerates static data for System dashboard
4. Builds System app (React) → `frontend/show/dist/system/`
5. Deploys both Show + System to Firebase

**Manual deploy (if no data changes):**
```bash
cd frontend/show && npx vite build
cp -r frontend/show/system/ frontend/show/dist/system/
firebase deploy --only hosting:laeh-madphotos
```

Dry run (no writes, just show counts):
```
python3 backend/firestore_sync.py --dry
```

## Quick stats
```sql
-- Vote counts by device
SELECT device, vote, COUNT(*) FROM firestore_tinder_votes GROUP BY device, vote;
-- Picks re-curation votes
SELECT vote, COUNT(*) FROM firestore_picks_votes GROUP BY vote;
```

## Frontend Notes
- Vite hashed assets use immutable cache headers. No manual version bumping needed.
- `firebase.json` points `public` to `frontend/show/dist` with SPA catch-all rewrite.
- Service worker in `public/sw.js` — handles image caching (micro/thumb/image tiers).
- Performance tiers: tier-a (Safari/high-end), tier-b (no blur), tier-c (minimal).
- Theme: `data-theme="dark"` attribute on `<html>`, saved in localStorage.
- Old vanilla JS files preserved as `index-vanilla.html`, `app.js`, `isit.js`, etc. (can be removed once migration is verified).

## AI/ML Models & Tools

### Python Environments

**.venv-gen** (Python 3.13) — Primary AI/ML environment
- Location: `.venv-gen/`
- Key packages: torch 2.10, torchvision 0.25, transformers 5.1, google-genai 1.63, mflux 0.16.3, opencv-python, Pillow, numpy, scikit-learn, lancedb, ultralytics, easyocr, deepface
- Activate: `.venv-gen/bin/python3`

### Ollama Models (Local LLM)

All models served via Ollama at `http://localhost:11434/api/generate`.

| Model | Base | Purpose | Temp | Tokens |
|-------|------|---------|------|--------|
| `madphotos-critic` | gemma3:27b | Photography critique + structured analysis | 0.3 | 1500 |
| `gemma3:27b` | — | General vision/language (raw, no system prompt) | — | — |

**Modelfile:** `backend/Modelfile.madphotos`
- System prompt baked in: photo analysis returning JSON with description, subject, mood, composition, lighting, colors, crop recs, alternative stories, cartoon style recs
- Create/update: `ollama create madphotos-critic -f backend/Modelfile.madphotos`

### Cloud Models (Google Vertex AI)

| Model | API | Script | Purpose |
|-------|-----|--------|---------|
| Gemini 2.5 Pro | google-genai | `backend/gemini.py` | Deep photo analysis (semantic pops, color palette, grading, vibes) |
| Imagen 3 | Vertex AI | `backend/imagen.py` | 6 AI variant types (enhance, film, cartoon, cinematic, dreamscape, gemma_cartoon) |

- Project: `laeh380to760`, Location: `us-central1`
- Imagen rate limit: ~4 req/min (15s between calls)

### Local Image Generation

**mflux 0.16.3** (MLX-native Flux diffusion on Apple Silicon)
- Binary: `.venv-gen/bin/mflux-generate`
- Also in: `.venv-mflux/` (older mflux 0.2.1, Python 3.9 — legacy, prefer .venv-gen)
- HuggingFace auth required: gated models, token saved via `huggingface_hub.login()`
- Cached models (~31GB each) at `~/.cache/huggingface/hub/`:
  - `FLUX.1-dev` — higher quality, 20+ steps recommended
  - `FLUX.1-schnell` — fast (4 steps), lower quality

Available base models:
```
dev, schnell, krea-dev, dev-krea, qwen, fibo,
z-image, z-image-turbo, flux2-klein-4b, flux2-klein-9b,
flux2-klein-base-4b, flux2-klein-base-9b
```

Built-in LoRA styles:
```
couple, font, home, identity, illustration, portrait,
ppt, sandstorm, sparklers, storyboard
```

Key CLI flags:
```bash
.venv-gen/bin/mflux-generate \
  --model dev \                    # base model
  --quantize 4 \                   # 3/4/5/6/8 bit quantization
  --prompt "style description" \
  --image-path source.jpg \        # img2img mode (omit for txt2img)
  --image-strength 0.65 \          # 0.0=no change, 1.0=ignore source (default 0.4)
  --width 768 --height 512 \       # must be multiples of 64
  --steps 20 \                     # more steps = better quality
  --guidance 3.5 \                 # guidance scale
  --seed 42 \                      # reproducibility (omit for random)
  --lora-style illustration \      # built-in LoRA
  --lora-paths /path/to/lora.safetensors \  # custom LoRA
  --output result.png
```

Script: `backend/generate_test_images.py`
- Reads prompts from `backend/style_prompts_test.json` (generated by `test_style_prompts.py` via Gemma 27b)
- Engines: `--engine mflux`, `--engine imagen`, `--engine both`
- Uses img2img mode: preserves source dimensions, rounds to 64px multiples
- Strength clamped to 0.55-0.70 range, 20 steps, 4-bit quantized dev model
- Usage: `.venv-gen/bin/python3 backend/generate_test_images.py --engine mflux`

Learnings from testing:
- **img2img for style transfer produces subtle results** — Flux is designed for image variation, not dramatic style changes
- `schnell` + 4 steps = nearly identical to source regardless of prompt
- `dev` + 20 steps + strength 0.55-0.70 = slightly better but still underwhelming for style transfer
- Higher strength (0.85+) loses composition entirely instead of changing style
- **For dramatic style transfer, use Neural Style Transfer (VGG19) instead** — see below
- mflux is better suited for: txt2img generation, image variations, LoRA-based stylization

**Neural Style Transfer** (VGG19 + PyTorch, runs on MPS)
- Script: `backend/neural_style_transfer.py`
- Method: Gatys et al. with auto-balanced style weights + detail preservation
- 5 curated styles from public domain masterworks:
  1. Van Gogh — Starry Night (swirling impasto)
  2. Klimt — The Kiss (gold decorative)
  3. Seurat — Sunday Afternoon (pointillism)
  4. Monet — Impression Sunrise (soft impressionism)
  5. Munch — The Scream (dramatic expressionism)
- Style references cached in: `backend/style_references/`
- Output: `backend/generated_test/YYYYMMDD_HHMMSS/`
- Usage: `.venv-gen/bin/python3 backend/neural_style_transfer.py --count 5 --steps 300 --size 512`
- Key params: `--style-ratio` (1e4=moderate, 5e4=strong), `--detail` (0-1, edge/luminance preservation)

### Analysis Scripts

| Script | Model | Purpose |
|--------|-------|---------|
| `backend/run_gemma_picks.py` | madphotos-critic (Ollama) | Batch analysis of all picks — description, crops, stories, tags |
| `backend/gemini.py` | Gemini 2.5 Pro | Deep technical + compositional analysis per photo |
| `backend/imagen.py` | Imagen 3 | Generate 6 types of AI image variants |
| `backend/test_style_prompts.py` | gemma3:27b (Ollama) | Generate 5 diverse style-transfer descriptors per photo |
| `backend/generate_test_images.py` | mflux (local) + Imagen | Apply style prompts via img2img |
| `backend/neural_style_transfer.py` | VGG19 (PyTorch) | Classic neural style transfer with 5 art references |
| `backend/gemma_viewer.py` | — | Live web viewer for Gemma processing progress (port 8787) |

### Signal Pipeline

**v1** (`backend/signals_advanced.py`): aesthetic, depth, scene, style, ocr, captions, emotions
**v2** (`backend/signals_v2.py`): aesthetic-v2, florence-captions, sam-segments, grounding-dino, ram-tags, rembg, pose, saliency

**Orchestrator:** `backend/completions.py` — checks all 24 pipeline stages, auto-starts missing

### Pre-trained Model Files
- `yolov8n.pt` (232 MB) — YOLOv8 Nano object detection
- `.laion_aesthetic_v2.pth` (3.7 MB) — LAION aesthetic scorer
- `.places365_resnet50.pth.tar` (97 MB) — Places365 scene classifier
- `face_detection_yunet_2023mar.onnx` (232 KB) — YuNet face detector
- VGG19 weights (~548 MB) — cached at `~/.cache/torch/hub/checkpoints/`

### Database Tables (AI-related)
- `gemma_picks` — Gemma 3 analysis results per pick
- `gemini_analysis` — Gemini 2.5 Pro structured analysis
- `ai_variants` — Imagen 3 generated variants (status, paths, generation time)
- Signal tables: `aesthetic`, `depth`, `scene`, `style`, `faces`, `objects`, `ocr`, `captions`, `emotions`
