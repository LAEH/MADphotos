# MADphotos

Per-image AI photography pipeline. 9,011 photographs analyzed by 13 ML models, enhanced by camera-aware algorithms, styled by Imagen 3. Every signal stored in SQLite. Every image searchable by meaning.

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
