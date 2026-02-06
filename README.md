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

### See

The private power tool. A native macOS SwiftUI app for exploring, curating, and editing the collection. Browse by camera, vibe, time of day, location, aesthetic score. Keep or reject with a keystroke. Toggle between original and enhanced. Accept or reject AI-suggested locations. Every decision flows back into the database.

See is where the human decides what's worth showing to the world.

### Show

The public experience. Three web-based viewing modes designed for discovery and storytelling:

- **La Grille** — Filterable photo grid. Camera, vibe, time, setting, color.
- **La Derive** — Semantic drift. Click an image, follow where the vectors lead. DINOv2 finds texture, SigLIP finds meaning, CLIP finds subjects.
- **Les Couleurs** — Color space exploration. Navigate the collection by what it looks like.

Show only displays images that passed through See. Accepted and validated. The curated experience.

### State

The system dashboard. Real-time view of every pipeline, every signal, every model. Gemini analysis progress, camera fleet statistics, depth estimation, scene classification, enhancement metrics, vector store health. Plus sub-pages: Journal de Bord (the project narrative), system instructions, and experiments (Drift visualization, blind tests, mosaics).

State is the control room.

## The Pipeline

The processing pipeline runs 9 scripts orchestrated by `mad_pipeline.py`:

1. **Render** (`render_pipeline.py`) — 6-tier resolution pyramid per image (64px to 3840px), plus 4-tier for AI variants
2. **Analyze** (`photography_engine.py`) — Gemini 2.5 Pro structured analysis: vibes, exposure, composition, color grading, edit instructions, rotation
3. **Pixel Metrics** (`image_analysis.py`) — Luminance, white balance, noise, clipping, contrast, color temperature
4. **Vectors** (`vector_engine.py`) — Three embedding models (DINOv2, SigLIP, CLIP) into LanceDB for similarity search
5. **Signals** (`signal_extraction.py`) — EXIF, dominant colors (K-means LAB), face detection (YuNet), object detection (YOLOv8n), perceptual hashes
6. **Advanced Signals** (`advanced_signals.py`) — Aesthetic scoring, depth estimation, scene/style classification, OCR, captions, facial emotions
7. **Enhance** (`enhance_engine.py`) — Camera-aware per-image enhancement: white balance, exposure, shadows/highlights, contrast, saturation, sharpening
8. **Variants** (`imagen_engine.py`) — 4 AI variants via Imagen 3: gemini_edit, pro_edit, nano_feel, cartoon
9. **Sync** (`gcs_sync.py`) — Upload to Google Cloud Storage, track public URLs

## Infrastructure

- **Database**: SQLite (`mad_photos.db`) — 23 tables, one source of truth
- **Vector Store**: LanceDB (`vectors.lance/`) — 9,011 images x 3 models
- **Cloud**: GCS `gs://myproject-public-assets/art/MADphotos/`
- **Models**: Gemini 2.5 Pro, Imagen 3, DINOv2, SigLIP, CLIP, YOLOv8n, YuNet, BLIP, Depth Anything v2, Places365
- **Platform**: macOS, Python 3.9, Apple Silicon (MPS)
