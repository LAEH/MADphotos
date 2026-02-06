# MADphotos

9,011 photographs. Shot over a decade on Leica rangefinders, a monochrome sensor with no Bayer filter, scanned analog film, and pocket action cameras. Most have never been seen by anyone.

The intent: treat every single image as if it deserves a curator, a critic, and an editor. Not batch processing — per-image intelligence. An AI studies the exposure, the composition, the mood, the color. It finds the red airplane against the blue sky, the green flash of a cat's eye in shadow. It writes editing instructions unique to that frame. Then another AI executes them. From that improved base, style variants bloom: analog film grain, cel-shaded illustration.

Everything tracked in one SQLite database. Every signal extractable. Every image searchable by what it means, not just what it's named.

## The Collection

| Camera | Body | Medium | Count |
|--------|------|--------|-------|
| Leica M8 | Digital (CCD) | IR-sensitive sensor | 3,533 |
| DJI Osmo Pro | Action | Digital sensor | 3,032 |
| Leica MP | Analog | Kodak Portra 400 VC / B&W film | 1,126 |
| Leica Monochrom | Monochrome | Pure B&W sensor (no Bayer filter) | 1,099 |
| Canon G12 | Compact | Digital sensor | 137 |
| DJI Osmo Memo | Action | Digital sensor | 84 |

Source formats: **5,138 JPEG** + **3,841 DNG** + **32 RAW** = **9,011** images.

## Three Apps

### [Show](https://madphotos-efbfb.web.app)

Blow people's minds. Continuously release new experiences guided by signals and new ideas — playful, elegant, smart, teasing, revealing, exciting. 14 experiments and counting, each a different answer to *"what happens when you give a creative mind 9,011 images with every possible signal?"*

**La Grille** · **Le Bento** · **La Similarité** · **La Dérive** · **Les Couleurs** · **Le Terrain de Jeu** · **Le Flot** · **La Chambre Noire** · **Les Visages** · **La Boussole** · **L'Observatoire** · **La Carte** · **La Machine à Écrire** · **Le Pendule**

### [State](https://laeh.github.io/MADphotos/)

The dashboard. The control room. Every signal, every model, every image — tracked, measured, monitored. Live status, system instructions, signal inventory, Journal de Bord.

### See

The native power image viewer. MADCurator — SwiftUI on macOS, reading directly from the SQLite database. Full-resolution display, 55 fields, 18 filters. The human eye decides what's worth showing.

## The Pipeline

10 Python scripts. `mad_completions.py` is the master orchestrator — it checks all 20 pipeline stages against the database, starts whatever's missing, and regenerates the dashboard.

| Script | Purpose |
|--------|---------|
| `mad_completions.py` | Master orchestrator — checks 20 stages, fixes gaps, updates State |
| `mad_pipeline.py` | Phase orchestrator — runs stages in sequence |
| `render_pipeline.py` | 6-tier resolution pyramid per image (64px to 3840px), plus 4-tier for AI variants |
| `photography_engine.py` | Gemini 2.5 Pro structured analysis: vibes, exposure, composition, color grading, edit instructions |
| `advanced_signals.py` | 7 ML models: aesthetic scoring, depth estimation, scene classification, style classification, OCR, BLIP captions, facial emotions |
| `enhance_engine.py` | Camera-aware per-image enhancement: white balance, exposure, shadows/highlights, contrast, saturation, sharpening |
| `imagen_engine.py` | 4 AI variants via Imagen 3: gemini_edit, pro_edit, nano_feel, cartoon |
| `gcs_sync.py` | Upload serving tiers to Google Cloud Storage |
| `mad_database.py` | SQLite schema — 24 tables, shared across all scripts |
| `generate_status_page.py` | Dashboard, system instructions, Journal de Bord |

Additional scripts: `export_gallery_data.py` (web data export), `serve_gallery.py` (local dev server).

## Signal Inventory — 18 Signals per Image

| Signal | Source | Fields |
|--------|--------|--------|
| EXIF | Pillow | Camera, lens, focal, aperture, shutter, ISO, GPS |
| Pixel Analysis | NumPy/OpenCV | Brightness, saturation, contrast, noise, WB shifts |
| Dominant Colors | K-means (LAB) | 5 clusters: hex, RGB, LAB, percentage |
| Face Detection | YuNet | 3,187 faces across 1,676 images: boxes, landmarks, area % |
| Object Detection | YOLOv8n | 14,534 detections across 5,363 images, 80 COCO classes |
| Perceptual Hashes | imagehash | pHash, aHash, dHash, wHash, blur, sharpness |
| Vectors | DINOv2 + SigLIP + CLIP | 768d + 768d + 512d = 2,048 dimensions (LanceDB) |
| Gemini Analysis | Gemini 2.5 Pro | Alt text, vibes, exposure, composition, grading, edit prompt |
| Aesthetic Score | LAION (CLIP MLP) | Score 1–10 |
| Depth | Depth Anything v2 | Near/mid/far %, complexity bucket |
| Scene | Places365 | Top 3 labels, indoor/outdoor |
| Style | Derived | street, portrait, landscape, macro, etc. |
| OCR | EasyOCR | Text regions, language, confidence |
| Captions | BLIP | Natural language description |
| Facial Emotions | ViT | 7-class emotion scores per face |
| Enhancement | Camera engine | WB, gamma, shadows, contrast, saturation, sharpening |
| AI Variants | Imagen 3 | gemini_edit, pro_edit, nano_feel, cartoon |

## Infrastructure

- **Database**: SQLite (`mad_photos.db`) — 24 tables, one source of truth
- **Vector Store**: LanceDB (`vectors.lance/`) — 9,011 images × 3 embedding models
- **Cloud**: GCS `gs://myproject-public-assets/art/MADphotos/` — versioned image hosting (original / enhanced / blind)
- **AI Models**: Gemini 2.5 Pro, Imagen 3, DINOv2, SigLIP, CLIP, YOLOv8n, YuNet, BLIP, EasyOCR, Depth Anything v2, Places365, LAION Aesthetic, ViT Emotion
- **Platform**: macOS, Python 3.9, Apple Silicon (MPS acceleration)
- **Web**: Vanilla JS, no framework — dark glassmorphism UI, 14 experience modules
- **Hosting**: Firebase (Show), GitHub Pages (State), GCS (Images)
