---
layout: default
title: MADphotos
---

<div style="text-align: center; padding: 4rem 1rem 2rem;">
  <h1 style="font-size: 3rem; font-weight: 200; letter-spacing: 0.3em; margin: 0;">MADphotos</h1>
  <p style="font-size: 1.1rem; color: #888; margin-top: 0.5rem; letter-spacing: 0.1em;">11,557 photographs. 6 rendering tiers. 5 AI styles. One pipeline.</p>
</div>

---

## What Is This

MADphotos is a personal photography archive turned into a living, machine-readable visual intelligence system.

The collection — over eleven thousand photographs shot on everything from analog film cameras to DJI Osmo drones to Canon G12s — represents years of looking at the world through a lens. Landscapes, portraits, monochrome studies, timelapse frames. The raw material of a photographer's eye.

The problem was simple: thousands of images sitting in folders, unprocessed, unoptimized, and invisible. No metadata beyond filenames like `cdnfz.dng`. No way to search by mood, color, or composition. No web-ready versions. No way to reimagine them.

MADphotos solves this by running every single photograph through a pipeline that:

1. **Renders** it into every size the modern web needs — from 4K displays to 64px blur-up placeholders
2. **Analyzes** it with AI — extracting the technical craft (exposure, sharpness, lens artifacts), the compositional choices (rule of thirds, leading lines, depth), the color story (dominant palette, semantic pops), and the narrative (mood, scene, a poetic one-line description)
3. **Reimagines** it in five distinct creative styles — from subtle film-stock warmth to full cartoon transformation — because every photograph contains more than one version of itself
4. **Serves** everything from a cloud bucket with responsive tiers, so any frontend can pick the perfect size and format

The end result is a comprehensive database where every image is not just a file but a richly described object with dozens of metadata fields, multiple responsive renditions, and five AI-generated creative interpretations — all queryable, all served, all connected.

---

## The Collection

**11,557 original photographs** across four collections, spanning analog film to digital to drone cinematography.

| Collection | Subjects | Formats |
|:-----------|:---------|:--------|
| **Analog** | Landscape, Portrait | JPG (scanned film) |
| **Digital** | Landscape, Portrait, G12, Timelapse | DNG, JPG, PNG |
| **Monochrome** | Landscape, Portrait | JPG |
| **Osmo** | OsmoPro, OsmoMemo | DNG, JPG |

---

## The Pipeline

A fully automated, resumable processing pipeline that transforms raw originals into web-ready assets with AI-powered analysis and creative variants.

### Phase 1 — Render

Every original decoded (DNG/RAW via `rawpy`, standard formats via Pillow), orientation-corrected, and rendered into a **6-tier responsive pyramid**:

```
full      3840px   JPEG 92      4K displays, Retina desktop
display   2048px   JPEG 88 + WebP 82   Desktop, tablets, hero images
mobile    1280px   JPEG 85 + WebP 80   Mobile phones
thumb      480px   JPEG 82 + WebP 78   Grid thumbnails
micro       64px   JPEG 70 + WebP 68   LQIP blur-up placeholders
gemini    2048px   JPEG 90      AI analysis input
```

Each image receives a deterministic UUID. A manifest and SQLite database track every file, every tier, every byte.

### Phase 2 — Sync to GCS

All rendered assets uploaded to Google Cloud Storage with immutable cache headers. Local space reclaimed between phases.

```
gs://myproject-public-assets/art/MADphotos/
```

### Phase 3 — Gemini Analysis

Every photograph analyzed by **Gemini 2.5 Pro** with a custom "Master Expert Eye" prompt. Structured JSON output covering:

- **Technical** — exposure, sharpness, lens artifacts
- **Composition** — technique, depth, geometry
- **Color** — palette (hex), semantic pops, grading style
- **Environment** — time of day, setting, weather
- **Narrative** — face count, vibe, poetic alt-text

### Phase 4 — AI Variants (Imagen 3)

Five creative transformations of every photograph via **Imagen 3** (`imagen-3.0-capability-001`):

| Variant | Style |
|:--------|:------|
| **light_enhance** | Professional lighting enhancement — shadow recovery, warm highlights |
| **nano_feel** | Organic analog film aesthetic — Portra 400 warmth, lifted blacks, subtle grain |
| **cartoon** | Vibrant cel-shaded illustration — bold outlines, Studio Ghibli energy |
| **cinematic** | Hollywood color grading — teal/orange, film grain, moody contrast |
| **dreamscape** | Ethereal painterly transformation — luminous pastels, atmospheric haze |

Each variant is rendered into its own 4-tier responsive pyramid (display, mobile, thumb, micro).

### Phase 5 — Comprehensive Database

A single SQLite database (`mad_photos.db`) stores **everything**:

- Image metadata (dimensions, aspect ratio, orientation, original file size)
- Every tier path (local + GCS URL) for originals and all 5 variants
- Full Gemini analysis (parsed into queryable columns)
- AI variant generation metadata (prompts, model, timing, safety status)
- Pipeline run history

---

## Architecture

```
mad_pipeline.py          Orchestrator — runs all phases in sequence
  render_pipeline.py     Multiprocessing image pyramid renderer
  gcs_sync.py            GCS upload with tracking and verification
  photography_engine.py  Gemini 2.5 Pro async analysis engine
  imagen_engine.py       Imagen 3 async variant generator
  mad_database.py        Shared SQLite schema and helpers
```

All scripts are **idempotent and resumable**. Ctrl-C at any point, re-run, and it picks up where it left off. API failures retry with exponential backoff.

---

## Numbers

| Metric | Value |
|:-------|:------|
| Original images | 11,557 |
| Rendering tiers per original | 6 (10 files: JPEG + WebP) |
| AI variants per image | 5 |
| Tiers per variant | 4 (8 files) |
| Total rendered files | ~**577,850** |
| Gemini analyses | 11,557 |
| Imagen API calls | ~57,785 |

---

## Status

### Day 1 — February 5, 2026

**Completed:**
- Designed full pipeline architecture
- Built all 6 scripts: render pipeline, Gemini analysis, Imagen variants, GCS sync, database layer, orchestrator
- Comprehensive SQLite schema with 6 tables and full indexing
- Pushed to GitHub with CI-ready structure

**Next:**
- Run render pipeline on full collection (~6-8 hours)
- Upload to GCS
- Begin Gemini analysis sweep (~2 hours)
- Start Imagen variant generation (~7-10 days, rate-limited)

---

<div style="text-align: center; padding: 2rem; color: #666; font-size: 0.85rem;">
  Built with rawpy, Pillow, Gemini 2.5 Pro, Imagen 3, and too much coffee.
</div>
