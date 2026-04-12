# MADphotos

Per-image AI photography pipeline. 9,011 photographs analyzed by 13 ML models, enhanced by camera-aware algorithms, styled by Imagen 3. Every signal stored in SQLite. Every image searchable by meaning.

## Starting on a new machine

**Read this first if you just cloned the repo.** MADphotos has ~65 GB of state that doesn't live in git — it lives in GCS and gets pulled with `sync-down.sh`. These steps take the repo from "fresh clone" to "can build + deploy + run the full pipeline".

### What's in git vs what's in GCS vs what you recreate locally

| Thing | Where | How it gets here |
|---|---|---|
| Source code (frontend, backend, scripts, Modelfile) | git | `git clone` |
| `requirements-gen.lock.txt`, `requirements-mflux.lock.txt` | git | `git clone` |
| `images/mad_photos.db` (~3.2 GB) | **GCS** `sync/mad_photos.db` | `sync-down.sh` |
| `frontend/show/public/data/*` (JSON + mosaic mp4s) | **GCS** `sync/data/` | `sync-down.sh` |
| `images/vectors.lance/` (~170 MB, LanceDB) | **GCS** `sync/vectors.lance/` | `sync-down.sh` |
| `backend/suggest_image_variant/output/` (~1.7 GB, irreplaceable Imagen outputs) | **GCS** `sync/variants/` | `sync-down.sh` |
| `images/rendered/` (~59 GB, 6-tier pyramids) | **GCS** `sync/rendered/` | `sync-down.sh` (big — use `--skip-rendered` to defer) |
| `images/originals/` (~105 GB, 9,017 source photos) | **GCS** `madphotos/originals/` | pulled on demand by the render pipeline |
| `.venv-gen/` (Python 3.13, torch/transformers/lancedb/etc, ~11 GB) | NOT synced | recreate from `requirements-gen.lock.txt` |
| `.venv-mflux/` (Python 3.9, legacy mflux 0.2.1) | NOT synced | recreate from `requirements-mflux.lock.txt` (only if you need the legacy path) |
| Ollama `madphotos-critic` model (~17 GB) | NOT synced | recreate with `ollama create -f backend/Modelfile.madphotos` |
| HuggingFace cache (Flux ~62 GB, VGG19 ~550 MB) | NOT synced | re-downloads automatically on first use |

### Step-by-step

```bash
# 1. Clone
git clone git@github.com:LAEH/MADphotos.git ~/Github/MADphotos
cd ~/Github/MADphotos

# 2. gcloud auth — required for sync-down (GCS), Firebase deploy, and Vertex AI (Gemini/Imagen)
gcloud auth login
gcloud auth application-default login
gcloud config set project laeh380to760

# 3. Pull state from GCS.
#    Full pull (~65 GB, takes a while because of the rendered/ tier pyramids):
./sync-down.sh
#
#    OR — frontend-only fast path (~5 GB, skips rendered/ so you can build Show/System immediately):
./sync-down.sh --skip-rendered
#    …then later, when you need the tier pyramids for pipeline work:
./sync-down.sh --only-rendered

# 4. Python env — primary (.venv-gen, Python 3.13)
python3.13 -m venv .venv-gen
.venv-gen/bin/pip install --upgrade pip
.venv-gen/bin/pip install -r requirements-gen.lock.txt
#    Sanity check:
.venv-gen/bin/python3 -c "import torch, lancedb, transformers, google.genai; print('venv-gen OK')"

# 5. Ollama (for madphotos-critic, the Gemma 27B photo analyst)
brew install ollama   # or download from ollama.com
ollama serve &         # background daemon
ollama pull gemma3:27b
ollama create madphotos-critic -f backend/Modelfile.madphotos
ollama list | grep madphotos-critic

# 6. Frontend deps
npm install --prefix frontend/show
npm install --prefix frontend/system

# 7. Firebase login (for deploy)
npx firebase login

# 8. Verify everything is wired up
python3 -m backend.MADphotos_ignition.run --status
#    Starts a health check across servers, DB, Ollama, and disk.

# 9. Launch dev servers and deploy when ready
python3 -m backend.MADphotos_ignition.run     # ignition: serve_show + Show vite + System vite
python3 -m backend.update_and_deploy.run      # full 10-phase deploy to Firebase
```

### Multi-machine workflow — avoid DB drift

`mad_photos.db` is the ground truth. Only one machine should be writing it at a time, otherwise you'll silently clobber edits. Discipline:

1. **Before you start working on a machine** → run `./sync-down.sh --force` to refresh local DB from GCS. (Use `--force` to override the "same size, skip" shortcut — WAL state can be identical size but different content.)
2. **After any signal extraction / deploy / pipeline run** → run `./sync-up.sh` to push the updated DB + data + vectors + variants back up.
3. **If in doubt** → `gcloud storage ls -l gs://myproject-public-assets/madphotos/sync/mad_photos.db` shows the upload timestamp. Compare against `stat -f "%Sm" images/mad_photos.db` locally. If GCS is fresher, your local is stale — `sync-down --force` before touching anything.

`sync-up.sh` uses `rsync --checksums-only` for the directories (safe, incremental) and a direct `cp` for the DB file (always overwrites remote). It does **not** use `--delete-unmatched-destination`, so neither side ever deletes the other's files — missing-on-one-side just won't sync.

### Optional: `.venv-mflux` (only if you need the legacy mflux 0.2.1 path)

The modern mflux lives in `.venv-gen` (version 0.16.3). The legacy `.venv-mflux` environment was pinned to Python 3.9 + mflux 0.2.1 — only rebuild it if you have code that specifically imports from there.

```bash
python3.9 -m venv .venv-mflux
.venv-mflux/bin/pip install -r requirements-mflux.lock.txt
```

### Troubleshooting

- **`sync-down.sh` hangs on rendered/** → it's doing a 6M-file checksum-only rsync across 59 GB. First run takes 1-2 hours on fast internet. Use `--skip-rendered` if you don't need it right now.
- **`ollama create madphotos-critic` fails** → run `ollama serve` first and verify `curl http://localhost:11434/api/version` returns a JSON response.
- **`firebase deploy` fails with auth error** → `gcloud auth login` is NOT the same as `firebase login`. Run both.
- **`.venv-gen/bin/pip install` fails on torch** → make sure you're on Apple Silicon with Python 3.13; the lock file has MPS builds.
- **Vertex AI Imagen/Gemini calls fail** → `gcloud auth application-default login` (step 2 above) is the one that matters for server-side SDKs, not the plain `gcloud auth login`.

## Architecture

```
MADphotos/
├── frontend/
│   ├── show/                  Web gallery — 14 interactive experiences (Firebase)
│   ├── state/                 Dashboard — live stats, journal, instructions (GitHub Pages)
│   └── see/                   See — SwiftUI native curation app (two-window)
├── backend/                   19 Python scripts
│   └── models/                ML model weights (YuNet, YOLOv8n, Places365)
├── scripts/                   Shell automation (after_render.sh, full_reprocess.sh)
├── images/                    All data (gitignored)
│   ├── originals/             9,011 source images (5,138 JPG + 3,841 DNG + 32 RAW)
│   ├── rendered/              97,898 tier files — flat layout: {tier}/{format}/{uuid}.ext
│   ├── ai_variants/           Imagen 3 outputs (gemini_edit, pro_edit, nano_feel, cartoon)
│   ├── vectors.lance/         LanceDB — DINOv2 + SigLIP + CLIP embeddings
│   └── mad_photos.db          SQLite (WAL mode, 24 tables, ~3 GB)
├── docs/journal.md            Journal de Bord
├── requirements.txt           Python dependencies
└── firebase.json              Firebase Hosting config
```

## Pipeline

`completions.py` is the master orchestrator. It checks 20 pipeline stages against the database, starts whatever's missing, and regenerates the dashboard. `pipeline.py` runs stages in sequence for full runs.

### Scripts

| Script | What it does |
|--------|-------------|
| `completions.py` | Master orchestrator — checks 20 stages, fixes gaps, updates dashboard |
| `pipeline.py` | Sequential phase runner (render → upload → gemini → imagen → finalize) |
| `database.py` | SQLite schema (24 tables), exports `PROJECT_ROOT`, shared by all scripts |
| `render.py` | 6-tier resolution pyramid (64px → 3840px), 4-tier for AI variants |
| `gemini.py` | Gemini 2.5 Pro structured analysis (Vertex AI) |
| `imagen.py` | 4 AI variant types via Imagen 3 (Vertex AI, two-stage) |
| `signals.py` | EXIF extraction, dominant colors (K-means LAB), YuNet faces, YOLOv8 objects, perceptual hashes |
| `signals_advanced.py` | 7 ML models: aesthetic (LAION), depth (DAnything v2), scene (Places365), style, OCR (EasyOCR), captions (BLIP), emotions (ViT) |
| `pixel_analysis.py` | Histogram, white balance, contrast, noise — feeds enhancement engine |
| `enhance.py` | Camera-aware 6-step enhancement: WB → exposure → shadows/highlights → contrast → saturation → sharpening |
| `enhance_v2.py` | Signal-aware enhancement v2 |
| `vectors.py` | DINOv2 (768d) + SigLIP (768d) + CLIP (512d) embeddings into LanceDB |
| `upload.py` | GCS upload with tier/variant routing |
| `export_gallery.py` | Full signal export to `frontend/show/data/photos.json` (~28 MB) |
| `dashboard.py` | Dashboard HTML generator + live server (`:8080`) + Journal de Bord |
| `serve_show.py` | Local dev server for Show (`:3000`) |
| `mosaics.py` | 4096px mosaic generator sorted by N dimensions |
| `render_enhanced.py` | Render tier pyramids for enhanced images |
| `prep_blind_test.py` | Prepare 3-way blind A/B test (original vs enhanced v1 vs v2) |

### Path Resolution

All scripts resolve paths from `PROJECT_ROOT`:

```python
# database.py — the canonical root
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # → MADphotos/
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"

# All other scripts import it
import database as db
PROJECT_ROOT = db.PROJECT_ROOT
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
```

Scripts that use models (`signals.py`, `signals_advanced.py`) also define:
```python
BACKEND_DIR = Path(__file__).resolve().parent  # → backend/
YUNET_MODEL = BACKEND_DIR / "models" / "face_detection_yunet_2023mar.onnx"
```

## Signal Inventory

18 signal types per image. Every signal stored in SQLite.

| Signal | Model/Source | Output |
|--------|-------------|--------|
| EXIF | Pillow | Camera, lens, focal, aperture, shutter, ISO, GPS |
| Pixel Analysis | NumPy/OpenCV | Brightness, saturation, contrast, noise, WB shifts |
| Dominant Colors | K-means (LAB) | 5 clusters: hex, RGB, LAB, percentage |
| Faces | YuNet (OpenCV DNN) | 3,187 faces / 1,676 images: boxes, landmarks, area % |
| Objects | YOLOv8n (Ultralytics) | 14,534 detections / 5,363 images, 80 COCO classes |
| Hashes | imagehash | pHash, aHash, dHash, wHash + blur/sharpness scores |
| Vectors | DINOv2 + SigLIP + CLIP | 768d + 768d + 512d = 2,048 dimensions per image |
| Gemini | Gemini 2.5 Pro | Alt text, vibes, exposure, composition, grading, edit prompt |
| Aesthetic | LAION (CLIP MLP) | Score 1–10 |
| Depth | Depth Anything v2 | Near/mid/far %, complexity bucket |
| Scene | Places365 (ResNet50) | Top 3 labels, indoor/outdoor |
| Style | Derived | street, portrait, landscape, macro, etc. |
| OCR | EasyOCR | Text regions, language, confidence |
| Captions | BLIP | Natural language description |
| Emotions | ViT (DeepFace) | 7-class scores per detected face |
| Enhancement | Camera engine | Per-step adjustments (WB, gamma, shadows, contrast, sat, sharp) |
| Enhancement v2 | Signal-aware | Refined adjustments using all extracted signals |
| AI Variants | Imagen 3 | gemini_edit, pro_edit, nano_feel, cartoon |

## Rendered Tiers

Every image → 6-tier pyramid. AI variants → 4-tier. **97,898 files** total.

```
images/rendered/{tier}/{format}/{uuid}.ext    ← flat layout, no category subdirs
```

| Tier | Max px | Formats | Purpose |
|------|--------|---------|---------|
| full | 3840 | jpeg | AI pipeline source |
| display | 2048 | jpeg, webp | Full-screen viewing |
| mobile | 1280 | jpeg, webp | Mobile screens |
| thumb | 480 | jpeg, webp | Grids, lists |
| micro | 64 | jpeg, webp | Color swatches, placeholders |
| gemini | 2048 | jpeg | Gemini analysis input |
| original | native | jpeg | Unresized JPEG copies (5,138 images) |

## Camera Fleet

| Camera | Body | Medium | Count |
|--------|------|--------|-------|
| Leica M8 | Digital (CCD) | IR-sensitive sensor | 3,533 |
| DJI Osmo Pro | Action | Digital sensor | 3,032 |
| Leica MP | Analog | Kodak Portra 400 VC / B&W film | 1,126 |
| Leica Monochrom | Monochrome | Pure B&W sensor (no Bayer filter) | 1,099 |
| Canon G12 | Compact | Digital sensor | 137 |
| DJI Osmo Memo | Action | Digital sensor | 84 |

## Frontend

### Show — `frontend/show/`

Public-facing photo experience with 9 interactive views. Vanilla JS, no framework. Apple HIG design system with 74+ CSS custom properties. PWA with service worker for offline browsing. Each view explores the collection through a different lens.

**Picks** (😎) / **Colors** / **Relation** / **Bento** / **NYU** / **Couple** / **Boom** / **Caption** / **WIP** (Tinder)

Deployed at https://madphotos.laeh.ai

### System — `frontend/system/`

Internal dashboard for monitoring project state, pipeline progress, and experiments. React + TypeScript + Vite. Routes: status, journal, instructions, database overview, experiments (Gemma, mosaics, cartoon, blind test).

**Two modes:**
- **Production**: Static snapshot deployed at https://madphotos.laeh.ai/system (updated on each sync/deploy)
- **Development**: Live data via local API server at http://localhost:3000/system

Pre-built JSON data regenerated from `backend/dashboard.py` and deployed alongside Show for unified hosting.

## Infrastructure

| Component | Technology |
|-----------|-----------|
| Database | SQLite, WAL mode, 24 tables, `images/mad_photos.db` |
| Vectors | LanceDB, `images/vectors.lance/`, 9,011 x 3 models |
| Cloud Storage | GCS `gs://myproject-public-assets/art/MADphotos/` |
| AI Platform | GCP Vertex AI (Gemini 2.5 Pro + Imagen 3), project `madbox-e4a35` |
| Auth | Application Default Credentials (ADC), no API keys |
| Runtime | Python 3.9.6, Apple Silicon MPS acceleration |
| Web Hosting | Firebase (Show + System), GCS (images) |

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Check pipeline status
python3 backend/completions.py --status

# Run full pipeline
python3 backend/pipeline.py

# Run specific phase
python3 backend/pipeline.py --phase gemini

# Live dashboard
python3 backend/dashboard.py --serve

# Local dev server (Show + System with live data)
python3 backend/serve_show.py  # http://localhost:3000

# System dev only (Vite with live API)
cd frontend/system && npm run dev  # http://localhost:5173

# Full sync + deploy
python3 backend/firestore_sync.py

# Export gallery data
python3 backend/export_gallery.py --pretty
```

## Key Conventions

- **Python 3.9.6**: Use `from __future__ import annotations`, `Optional[X]` not `X | None`
- **UUIDs**: Deterministic from relative path, DNS namespace (`6ba7b810-...`)
- **Flat render layout**: `images/rendered/{tier}/{format}/{uuid}.ext` — never category subdirs
- **Incremental**: Every script skips already-processed images. Safe to re-run.
- **DNG/RAW**: `sips` with `-m sRGB Profile.icc` to avoid Display P3 purple cast
- **Monochrome camera**: Leica Monochrom has no Bayer filter — NEVER apply color correction
