# MADphotos Backend

9,011 photographs. Shot over a decade on Leica rangefinders, a monochrome sensor, scanned film, drones, and action cameras. Most have never been seen by anyone.

The backend is organized as **five agent folders**, each owning a distinct phase of the pipeline that turns a raw archive of unknowns into something alive on screens. They flow in sequence — signals feed curation, curation feeds deployment, and the dev environment keeps everything running while you work.

```
image_signals → suggest_image_enhancement → suggest_image_variant → update_and_deploy
                                                                          ↑
                                                            MADphotos_ignition (dev env)
```

Every agent folder gets a **yellow Finder label** so you can spot them at a glance.

---

## The Agents

### 1. `image_signals/` — Signal Extraction

**What it does:** Runs every available model against every image — local open-source models for vision tasks (faces, objects, depth, aesthetics, style, scenes, OCR, captions, colors, hashes), Gemini API for semantic analysis (vibes, composition, grading, time of day, weather), Gemma 27B for creative analysis (stories, crops, cartoon recs), and vector embeddings for similarity (DINOv2, SigLIP, CLIP).

**Why it matters:** Signals are the foundation. Every downstream experience — Show's 6 views, System's dashboards, the enhancement and variant agents — depends on the richness of what this agent extracts. A new signal table can unlock an entirely new experience. 24+ models, 33+ DB tables, 9,011 rows each.

**Entry point:** `python3 -m backend.image_signals.completions`

### 2. `suggest_image_enhancement/` — Enhancement Curation

**What it does:** Proposes non-destructive improvements to photographs — border crops (removing film rebates and scanner artifacts), exposure corrections, Gemma-suggested compositional crops, rotation fixes. Presents batches of ~30 proposals with before/after previews for the user to vote accept or reject.

**Why it matters:** The archive contains raw scans and uncorrected exposures. This agent uses the signals to identify what can be improved, but the user has final say. Every accepted enhancement becomes the new "enhanced" tier in Show. The agent learns from votes — types with higher acceptance rates get more proposals in future batches.

**Entry point:** `python3 -m backend.suggest_image_enhancement.propose`

### 3. `suggest_image_variant/` — Style Transfer

**What it does:** Generates AI art variants of photographs using Imagen 3, neural style transfer (VGG19), and local diffusion (mflux). Picks styles per image using affinity scoring — matching artistic styles to each photo's scene, depth, vibe, and objects. Presents variants for user voting. Accepted variants become new images in Show.

**Why it matters:** The archive is photographs. Variants expand it into illustration, painting, graphic art — new ways to see the same moments. 23+ defined styles across 6 families (Japanese, Western illustration, graphic, fine art, expressionist, pop culture). The agent tracks accept/reject rates per style, auto-excludes dead styles, and balances proven winners against undertested newcomers (80/20 exploit/explore).

**Entry point:** `python3 -m backend.suggest_image_variant.run`

### 4. `update_and_deploy/` — Deployment

**What it does:** Gets the project safely from working tree to production in 10 verified phases — preflight checks (no DB-writing processes running), git inspection, doc health, Firestore vote sync, gallery export (fingerprint-gated), System JSON regeneration, Vite builds, Firebase deploy, live URL verification, Finder tags + git commit.

**Why it matters:** Signals change, enhancements get accepted, variants get approved — all of that needs to flow to production. This agent ensures nothing deploys stale, nothing deploys while the DB is being written to, and every deploy is verified end-to-end. It also regenerates `photos.json`, the single data file that powers every Show experience.

**Entry point:** `python3 -m backend.update_and_deploy.run`

### 5. `MADphotos_ignition/` — Dev Environment

**What it does:** Automates the full startup sequence in 4 phases — pre-checks (git state, port scan, node_modules, DB health, Ollama status), server launch (Python API server on :3000, Show Vite on :5173, System Vite on :5174), health verification with retries, and optional companions (terminal monitor in a new window, native macOS See app, Ollama model report).

**Why it matters:** Three servers, multiple dependencies, port conflicts — ignition handles all of it idempotently. Run it twice and the second run skips everything already running, just verifies health. Shutdown mode gracefully kills all managed processes.

**Entry point:** `python3 -m backend.MADphotos_ignition.run`

---

## How They Fit Together

The mission is: **extract signal, curate with human input, ship to screens.**

**Signals** (`image_signals`) populate the database with everything the models can see — 33+ tables of structured data plus vector embeddings. This is the intelligence layer.

**Enhancement** (`suggest_image_enhancement`) and **Variants** (`suggest_image_variant`) use those signals to propose improvements and transformations. Both agents present their work to the user and learn from votes. The user's taste is the filter — the agents propose, the human curates.

**Deploy** (`update_and_deploy`) takes everything — the signals, the curated enhancements, the accepted variants — and ships it to production. Photos.json carries every signal to the Show app. System gets fresh dashboards. Firebase serves it all.

**Ignition** (`MADphotos_ignition`) keeps the dev environment alive so you can do all of the above without thinking about servers and ports.

---

## Other Backend Files

Not everything is in an agent folder. Standalone scripts handle specific tasks:

| File | Purpose |
|------|---------|
| `serve_show.py` | HTTP server — serves Show, System, and all API endpoints |
| `dashboard.py` | Generates System static JSON data from DB |
| `export_gallery.py` | Exports all signals to `photos.json` for Show |
| `monitor.py` | Terminal TUI — live process/Gemma/signal dashboard |
| `render.py` | Render image tiers (display/thumb/micro in JPEG+WebP) |
| `imagen.py` | Imagen 3 API wrapper |
| `firestore_sync.py` | Pull Firestore votes into SQLite |
| `extract_variant_colors.py` | Extract dominant colors from accepted variants |
| `trim_variant_borders.py` | Remove white borders from Imagen output |
| `database.py` | DB utilities and schema management |
| `api/` | API endpoint handlers (stats, cartoons, gemma, generated, inspectors) |
