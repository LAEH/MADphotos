# MADphotos

Photo archive of 9,011 photographs. The backend is organized as **five agent folders** that form a pipeline: extract signals from every image, curate the best material with human input, and ship it to screens. See `backend/README.md` for the full agent architecture.

## New machine? Read this first

If this is a fresh clone on a machine that has never run MADphotos before, the canonical onboarding checklist lives in **`README.md` → "Starting on a new machine"**. Follow it top to bottom. It covers: `gcloud auth`, `sync-down.sh` (pulls ~65 GB of DB + tier pyramids + vectors + variant outputs from GCS), `.venv-gen` recreation from `requirements-gen.lock.txt`, Ollama `madphotos-critic` creation from `backend/Modelfile.madphotos`, Firebase login, and the ignition/deploy commands.

**Multi-machine DB discipline:** `mad_photos.db` is the ground truth and only one machine should be writing it at a time. Before touching anything on a new session, run `./sync-down.sh --force` to refresh the DB from GCS. After any pipeline or deploy run, run `./sync-up.sh` to push it back.

## Welcome

When the user starts a new session (first message, greeting, or says "hello", "hi", "start", etc.), display this welcome:

```
MADphotosMADphotosMADphotosMADphotosMADphotos
MADphotosMADphotosMADphotosMADphotosMADphotos
MADphotosMADphotosMADphotosMADphotosMADphotos
MADphotosMADphotosMADphotosMADphotosMADphotos
MADphotosMADphotosMADphotosMADphotosMADphotos
MADphotosMADphotosMADphotosMADphotosMADphotos
MADphotosMADphotosMADphotosMADphotosMADphotos
```

Then list available commands:

| Command | What it does |
|---------|-------------|
| **ignition** | Launch dev servers (serve_show, Show vite, System vite) |
| **shutdown** | Stop all running servers |
| **deploy** | 10-phase verified deployment to Firebase |
| **signals** | Run signal extraction pipeline (24+ models) |
| **enhance** | Propose image enhancements for review |
| **variants** | Generate AI art variants |
| **prepare** | Pre-compute Show data (bentos, pairs, scores) |
| **status** | Check server health + running processes |
| **myteam** | Show all 6 agents — see `myteam.md` |

## Agents

| Agent | Mission | Entry Point |
|-------|---------|-------------|
| `image_signals/` | Run 24+ models against every image — the intelligence layer | `python3 -m backend.image_signals.completions` |
| `suggest_image_enhancement/` | Propose non-destructive improvements, user votes accept/reject | `python3 -m backend.suggest_image_enhancement.propose` |
| `suggest_image_variant/` | Generate AI art variants with learned style selection | `python3 -m backend.suggest_image_variant.run` |
| `update_and_deploy/` | 10-phase verified deployment to Firebase production | `python3 -m backend.update_and_deploy.run` |
| `prepare_show/` | Pre-compute Show data — bentos, pairs, scores, indices | `python3 -m backend.prepare_show.run` |
| `MADphotos_ignition/` | Dev environment startup — servers, health, companions | `python3 -m backend.MADphotos_ignition.run` |

## MADphotos ignition

When the user says "ignition" or "MADphotos ignition", run the ignition agent:

```bash
python3 -m backend.MADphotos_ignition.run
```

**Scope:** Only care about MADphotos processes. Other Python/Node processes running on this machine (other projects, scrapers, etc.) are out of scope — do not report on them, do not kill them.

When the user says "shutdown", shut down **all** MADphotos processes:

1. Run `python3 -m backend.MADphotos_ignition.run --shutdown` (kills servers + vite)
2. Then find and kill any remaining MADphotos processes: signal extraction (`extract_signals`, `run_gemma`, `completions`, `gemini.py`, `export_gallery`, `signals_v2`, `signals_advanced`), variant generation (`imagen`, `neural_style`, `generate_test`, `smart_variants`), enhancement (`enhance_exposure`), See.app, and any other process launched from the MADphotos directory. Confirm what was killed.

When the user says "deploy", run:

```bash
python3 -m backend.update_and_deploy.run
```

When the user says "signals", run:

```bash
python3 -m backend.image_signals.completions
```

When the user says "enhance", run:

```bash
python3 -m backend.suggest_image_enhancement.propose
```

When the user says "variants", run:

```bash
python3 -m backend.suggest_image_variant.run
```

When the user says "prepare", run:

```bash
python3 -m backend.prepare_show.run
```

When the user says "status" or "MADphotos status", perform a **thorough diagnostic report**:

1. **Servers** — check what's running (serve_show :3000, Show vite :5173, System vite :5174, Ollama :11434)
2. **Processes** — find any running Python/signal/generation processes (`ps aux | grep python`)
3. **Pipeline health** — query DB for signal coverage gaps, failed/incomplete runs, stale data
4. **Variants & enhancements** — check `ai_variants` and `enhancement_plans` status counts
5. **Git state** — uncommitted changes, current branch, ahead/behind remote
6. **Disk** — DB size, rendered tiers count, vector store health
7. **Next steps** — propose 3-5 concrete actions to improve signal extraction, data consumption in Show, and visual quality of experiences

Run `python3 -m backend.MADphotos_ignition.run --status` for server health, then supplement with direct DB queries and filesystem checks to build the full picture.

This automates the full startup: pre-checks (git, ports, deps, DB, Ollama) → server launch (serve_show :3000, Show vite :5173, System vite :5174) → health verification → ready URLs.

Flags: `--prechecks`, `--health`, `--status`, `--shutdown`, `--monitor`, `--see`, `--dry`, `--force`, `--tags`. See `backend/MADphotos_ignition/CLAUDE.md` for full docs.

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

**Unified deploy pipeline** (`backend/update_and_deploy/`):
```bash
python3 -m backend.update_and_deploy.run            # full 10-phase pipeline
python3 -m backend.update_and_deploy.run --dry       # dry run
python3 -m backend.update_and_deploy.run --preflight # safety check only
python3 -m backend.update_and_deploy.run --data      # regen System JSON only
python3 -m backend.update_and_deploy.run --build     # Vite builds only
python3 -m backend.update_and_deploy.run --deploy    # Firebase deploy only
python3 -m backend.update_and_deploy.run --tags      # set Finder labels only
```

10 phases: Preflight → Inspect → Docs → Sync → Export → Data → Build → Deploy → Verify → Postflight

Modifiers: `--wait` (poll until blockers clear), `--force` (ignore blockers), `--no-git` (skip commit), `--full` (force gallery re-export)

**Legacy shim:** `scripts/deploy.py` forwards to the agent.

**Firestore sync only:**
```bash
python3 backend/firestore_sync.py          # sync + regenerate picks.json
python3 backend/firestore_sync.py --dry    # show counts without writing
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
| Gemini 2.5 Pro | google-genai | `backend/image_signals/gemini.py` | Deep photo analysis (semantic pops, color palette, grading, vibes) |
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
- Style references cached in: `backend/suggest_image_variant/style_references/`
- Output: `backend/suggest_image_variant/output/YYYYMMDD_HHMMSS/`
- Usage: `.venv-gen/bin/python3 backend/neural_style_transfer.py --count 5 --steps 300 --size 512`
- Key params: `--style-ratio` (1e4=moderate, 5e4=strong), `--detail` (0-1, edge/luminance preservation)

### Analysis Scripts

| Script | Model | Purpose |
|--------|-------|---------|
| `backend/image_signals/run_gemma_analysis.py` | madphotos-critic (Ollama 27B) | **Unified** Gemma analysis — all signals in one prompt per image |
| `backend/image_signals/legacy/run_gemma_picks.py` | madphotos-critic-4b (Ollama) | Legacy: description, crops, stories, tags (superseded by run_gemma_analysis) |
| `backend/image_signals/legacy/run_gemma_composition.py` | gemma3:27b (Ollama) | Legacy: visual_weight, archetype, energy, color_temp (superseded by run_gemma_analysis) |
| `backend/image_signals/gemini.py` | Gemini 2.5 Pro | Deep technical + compositional analysis per photo |
| `backend/imagen.py` | Imagen 3 | Generate 6 types of AI image variants |
| `backend/suggest_image_variant/smart_variants_v1.py` | Imagen 3 | Smart style variants with per-image prompts (legacy) |
| `backend/suggest_image_variant/smart_variants_v2.py` | Imagen 3 | V2 variant generation pipeline (legacy) |
| `backend/suggest_image_enhancement/enhance_exposure.py` | — | Exposure adjustment for underexposed photos |
| `backend/suggest_image_variant/style_prompts.py` | gemma3:27b (Ollama) | Generate 5 diverse style-transfer descriptors per photo (legacy) |
| `backend/suggest_image_variant/test_images.py` | mflux (local) + Imagen | Apply style prompts via img2img (legacy) |
| `backend/suggest_image_variant/neural_style.py` | VGG19 (PyTorch) | Classic neural style transfer with 5 art references |
| `backend/export_gallery.py` | — | Export all signals to photos.json + auxiliary data files |

### Gemma Analysis (Unified)

**Script:** `backend/image_signals/run_gemma_analysis.py` — one prompt, one table, all signals per image.

**Table:** `gemma_analysis` — replaces `gemma_picks` + `gemma_composition`.

**Signals per image:** description, subject, story, mood, composition, lighting, colors, texture, technical, strength, tags, print_worthy, crops (1:1, 2:3, 3:2, 16:9), 5 story variations (silly, poetic, surrealist, noir, romantic), cartoon_style, visual_weight (1-10), energy_direction, archetype, color_temp.

**CLI:**
```bash
python3 backend/image_signals/run_gemma_analysis.py              # process pending picks
python3 backend/image_signals/run_gemma_analysis.py --workers 8   # parallel (overnight)
python3 backend/image_signals/run_gemma_analysis.py --migrate     # seed from legacy tables (no Ollama)
python3 backend/image_signals/run_gemma_analysis.py --rerun       # reprocess all
python3 backend/image_signals/run_gemma_analysis.py --limit 10    # test run
```

**Resume logic:** skips completed rows; reprocesses migrated rows missing composition signals.

### Signal Pipeline

**v1** (`backend/image_signals/signals_advanced.py`): aesthetic, depth, scene, style, ocr, captions, emotions
**v2** (`backend/image_signals/signals_v2.py`): aesthetic-v2, florence-captions, sam-segments, grounding-dino, ram-tags, rembg, pose, saliency

**Orchestrator:** `backend/image_signals/completions.py` — checks all 24 pipeline stages, auto-starts missing

### Pre-trained Model Files
- `yolov8n.pt` (232 MB) — YOLOv8 Nano object detection
- `.laion_aesthetic_v2.pth` (3.7 MB) — LAION aesthetic scorer
- `.places365_resnet50.pth.tar` (97 MB) — Places365 scene classifier
- `face_detection_yunet_2023mar.onnx` (232 KB) — YuNet face detector
- VGG19 weights (~548 MB) — cached at `~/.cache/torch/hub/checkpoints/`

### Database Tables (AI-related)
- `gemma_analysis` — **Unified** Gemma signals per pick (description, crops, composition, stories, all fields)
- `gemma_picks` — Legacy Gemma analysis (superseded by gemma_analysis)
- `gemma_composition` — Legacy composition signals (superseded by gemma_analysis)
- `gemini_analysis` — Gemini 2.5 Pro structured analysis
- `ai_variants` — Imagen 3 generated variants (status, paths, generation time)
- `enhancement_plans` — Exposure enhancement proposals and review status
- Signal tables: `aesthetic_scores`, `aesthetic_scores_v2`, `depth_estimation`, `scene_classification`, `style_classification`, `face_detections`, `facial_emotions`, `face_identities`, `object_detections`, `open_detections`, `ocr_detections`, `image_captions`, `florence_captions`, `image_tags`, `saliency_maps`, `foreground_masks`, `segmentation_masks`, `pose_detections`, `image_analysis`, `dominant_colors`, `unified_texts`, `unified_labels`, `image_locations`, `border_crops`, `exif_metadata`
