# Journal de Bord — MADphotos

> The story of 9,011 photographs and the machine that sees them.

---

## The Beginning

9,011 photographs. A decade of shooting. Five cameras: a Leica M8 with its IR-sensitive CCD, a Leica Monochrom that captures pure luminance with no Bayer filter, a Leica MP loaded with Kodak Portra 400 VC and scanned frame by frame, a DJI Osmo Pro strapped to a helmet, a Canon G12 in a back pocket. Most of these images have never been seen by anyone.

Every single frame now runs through 10 AI models. Gemini 2.5 Pro reads each photograph and writes structured analysis — vibes, exposure, composition, color grading, per-image editing instructions. Three embedding models (DINOv2 for texture, SigLIP for semantics, CLIP for concepts) map every image into vector space. Depth Anything v2 estimates monocular depth. Places365 classifies the scene. A LAION aesthetic predictor scores visual quality. YuNet finds faces, then a ViT emotion classifier reads expressions. YOLOv8n detects objects. EasyOCR extracts text. BLIP writes captions. K-means clustering in LAB space pulls dominant colors. Imagen 3 generates four style variants per image.

One database. 23 tables. Every signal queryable. Every image searchable by what it means.

---

## The Numbers

- **9,011** photographs across 5 camera bodies (3,533 M8 / 3,032 Osmo Pro / 1,126 MP / 1,099 Monochrom / 221 G12+Memo)
- **10 AI models** per image: Gemini 2.5 Pro, DINOv2, SigLIP, CLIP, Depth Anything v2, Places365, BLIP, YuNet + ViT Emotions, YOLOv8n, EasyOCR
- **6 resolution tiers** per image: micro (64px), thumb (480px), mobile (1280px), display (2048px), full (3840px), gemini (2048px)
- **4 AI variant types**: gemini_edit, pro_edit, nano_feel, cartoon (via Imagen 3)
- **~52 GB** rendered tier files
- **23 SQLite tables**, one source of truth
- **3 apps**: See (native curator), Show (web gallery), State (dashboard)

---

## 2026-02-05

### 19:00 — Laying the Foundation *("Build me a pipeline")*

**Intent.** The starting point: 11,557 photographs in a folder, organized by medium — Analog, Digital, Monochrome, Osmo, G12. No metadata, no organization beyond folders. The goal: build a pipeline that can process every single image through AI analysis and enhancement. That meant: database schema, UUID generation, file registration, and a multi-tier rendering system.

> Built `mad_database.py` (SQLite schema), `render_pipeline.py` (6-tier resolution pyramid), `mad_pipeline.py` (orchestrator). Registered 9,011 images. Rendered all tiers: thumb, micro, mobile, display, full, original.

---

### 20:00 — The Rendering Pyramid *("We need different sizes for different uses")*

**Intent.** A 40MB RAW scan is useless for a thumbnail grid. A 200px thumb is useless for printing. We needed a pyramid: thumb (200px) for grid navigation, micro (480px) for previews, mobile (1080px) for phones, display (1920px) for screens, full (3840px) for AI processing and printing.

> 6 tiers × 9,011 images = 54,066 rendered files. ~52 GB total. Each tier in JPEG format with quality appropriate to its purpose.

---

### 20:30 — Wiring the AI Engines *("Now the interesting part")*

**Intent.** Two AI engines: one that sees (Gemini 2.5 Pro for analysis) and one that edits (Imagen 3 for enhancement). The analysis engine studies each photograph and writes structured JSON: exposure, composition, color palette, mood, editing instructions. The editing engine uses those instructions to improve the image.

> Built `photography_engine.py` (Gemini analysis) and `imagen_engine.py` (Imagen editing with 4 variant types).

---

### 21:10 — Launching Gemini Analysis *("Let's run all the images analysis now")*

**Intent.** The rendering pipeline had already processed all 9,011 images into a 6-tier resolution pyramid. The next step was the one that mattered most: having Gemini 2.5 Pro actually look at every photograph and understand it. Not metadata extraction — real visual analysis. What's the exposure doing? What draws the eye? What color palette dominates? What's the mood? And critically: what would a professional editor do to improve this specific image? We wanted structured, per-image intelligence that would later drive the AI editing.

> Launched `photography_engine.py` on all 9,011 images. Gemini 2.5 Pro via Vertex AI, concurrency 5, exponential backoff with max 5 retries.

---

### 21:15 — Building the Live Dashboard *("Build me a pretty minimal black and white web page")*

**Intent.** We needed to see what was happening. 9,011 images going through an AI analysis pipeline takes hours. Just watching a terminal scroll is useless — we wanted a dashboard that shows the big picture: how many images are done, how fast they're going, what the database looks like, what categories exist. Something clean, monospace, black and white. A control room.

> Created `generate_status_page.py` — live server mode (`--serve`) polls the DB every 5s. Stat cards, progress bar, category tables. All real-time.

---

### 21:20 — Auditing the Database Schema *("Did we get all the infos we wanted?")*

**Intent.** A gut check. The Gemini analysis was returning rich data — but was all of it actually being saved in a queryable way? If the data is buried in a raw JSON blob, you can't later ask "show me all photos with cinematic grading."

**Discovered.** Three critical fields — `lighting_fix`, `color_fix`, and `overall_edit_prompt` — had no DB columns. The `overall_edit_prompt` was particularly important: it's the per-image instruction that would later drive the AI editor.

> Added 3 columns, updated upsert, backfilled 156 rows from raw JSON. Restarted analysis.

---

### 21:30 — Seeing What the Machine Sees *("I want to see one example of full data")*

**Intent.** Schemas are abstract. We wanted to see what the machine actually says about a photograph — the complete analysis, live, updating as new images are processed. This is how you build trust in the system.

> Added "Sample Analysis" section to dashboard — full Gemini JSON, syntax-highlighted, refreshing every 5s.

---

### 21:40 — Evaluating the Next Phase *("What can you work on next?")*

**Intent.** The Gemini analysis was going to take hours. Rather than wait, we wanted to understand what the next phases looked like. What's ready? What's blocked?

**Discovered.** The Imagen engine had 5 hardcoded prompts and was completely ignoring Gemini's per-image editing advice. All that carefully generated `overall_edit_prompt` — thrown away. Also sourcing from 2048px when 3840px was available.

---

### 21:50 — The Two-Stage Architecture *("The cartoon could be better on an improved edited image")*

**Intent.** The key insight of the session. A cartoon of an underexposed, color-cast image inherits those problems. A cartoon of a properly edited image starts from a much better place. The Gemini analysis gives us image-specific editing instructions. Use those first, then build style variants on top.

> Rewired `imagen_engine.py` into two stages. Stage 1: edits from original (Gemini-guided + generic). Stage 2: styles from the enhanced result.

---

### 21:55 — Naming the Four Variants *("Why do you call it light_enhance?")*

**Intent.** Names matter. It's not a lighting fix anymore — it's a full Gemini-driven edit. And we want a second edit type for A/B comparison.

> Renamed to `gemini_edit` + `pro_edit`. Dropped cinematic/dreamscape. Final 4: gemini_edit, pro_edit, nano_feel, cartoon.

---

### 22:00 — Upgrading to 4K Source *("Make sure we get the largest size")*

**Intent.** Imagen 3 outputs at input resolution. We were feeding 2048px, had 3840px available. Free quality upgrade.

> Changed source to full tier (3840px). All variants now 4K.

---

### 22:05 — Adding Rotation Detection *("Add one question: should we rotate the image")*

**Intent.** Some photos are misoriented — EXIF data lost, scanned film upside down. Rather than a separate detection pass, ask Gemini while it's already looking.

> Added `should_rotate` (none/cw90/ccw90/180) to prompt and DB. Restarted analysis for remaining 8,698 images.

---

### 22:10 — First Visual Comparison *("Once you have 100, open the folders for me to inspect")*

**Intent.** Before committing to 9,011 images worth of API calls, we need to see results. Are Gemini-guided edits actually better than generic ones? 100 is enough to judge.

> Launched gemini_edit + pro_edit for 100 images each, from 4K source. Visual comparison pending.

---

### 22:15 — Tracking Imagen Progress *("Add all this tracking to the monitor page")*

**Intent.** Three processes running simultaneously — Gemini analysis, gemini_edit, pro_edit — and no visibility into Imagen progress or rotation data.

> Added per-variant progress bars (success/failed/filtered) and rotation recommendation pills to dashboard.

---

### 22:20 — Telling the Story *(Journal de Bord)*

**Intent.** This project is a process, not just a result. The decisions — why two-stage, why ask about rotation, why these 4 variants — are the story.

> Created this document. Served at `/journal`. Updated every session.

---

### 22:45 — The Enhancement Showdown *("The edits are not that good, there is often a white balance problem")*

**Intent.** The first 100 Imagen edits came back with persistent white balance issues. Imagen 3 is a generative model — it can't do precise color math. We needed to separate the deterministic work (white balance correction) from the creative work (exposure, contrast).

**Discovered.** Tested three approaches: Imagen with simplified prompts (guidance 30), OpenCV (GrayworldWB + CLAHE + auto gamma), and Pillow (grey world + autocontrast + brightness). All three produced decent but different results. None was clearly superior.

> Built a blind test: 20 images, 4 columns (original + 3 shuffled enhancements), click your favorite. Served at `/blind-test`.

---

### 23:00 — The Blind Test Results *("OpenCV 5, Pillow 5, Imagen 4, Skipped 6")*

**Intent.** Let the eyes decide, not the theory. A three-way tie with 30% rejected meant no method was good enough alone. The key insight: curation before enhancement. Don't waste effort improving images that have no potential.

> Decision: wait for Gemini analysis on all 9,011 images, then build a curation interface to reject weak images before generating any edits. Enhancement approach TBD based on curated subset.

---

### 23:10 — Designing the Curation Interface *("Create an interface to navigate the images with all the tags")*

**Intent.** With Gemini analyzing every photograph's exposure, composition, color palette, vibe, and setting — we have the metadata to make smart decisions. The interface should let a human quickly scan thousands of images, filter by any dimension, and reject the ones with no potential. Only the survivors get enhanced.

> Planned: thumbnail grid with filter pills (grading, vibe, time, setting, composition, exposure), keyboard-driven reject/keep workflow, progress tracker. Building once Gemini completes (~24h).

---

## 2026-02-06

### 00:00 — Scrubbing the Secret *("IMPORTANT push asap to remove my api keys")*

**Intent.** A Google API key had been committed in the initial git push as a fallback in `photography_engine.py`. It needed to go — not just from the current code, but from the entire git history. Every commit, every diff, every reflog entry.

> Installed `git-filter-repo`, rewrote all history to replace the key with `REDACTED_API_KEY`, removed the fallback entirely (now env-var-only), force-pushed the cleaned history to GitHub. Key revocation recommended.

---

### 00:15 — MADCurator: A Native App *("Create a native app so it is faster? Apple style/rigor")*

**Intent.** The curation interface needed to handle 9,011+ images with instant filtering, smooth scrolling, and keyboard-driven workflow. A web app would struggle. A native SwiftUI macOS app reads directly from the SQLite database, loads thumbnails from the rendered tier on disk, and keeps everything in-process.

> Built `MADCurator.app` — SwiftUI, NavigationSplitView with sidebar/grid/detail, SQLite3 C API, NSCache for 2000 thumbnails, Keep/Reject with K/R keys, arrow navigation.

---

### 00:30 — Faceted Search *("Create a way better navigation system with union and intersection simple queries")*

**Intent.** The first sidebar was a vertical list of single-select pills — click one, see results, click another, lose the first. No multi-select, no compound queries, no visibility into what you're filtering. Scrolling through 15 sections of tags with no context was painful.

**Solution.** Proper faceted search: multi-select within each dimension (union/OR), intersection across dimensions (AND). Contextual counts that update in real-time — options with zero matches disappear. A query bar above the grid showing the active expression with `∪` and `∩` operators. Removable chips. For vibes: a toggle between "Any of these" and "All of these".

> Rewrote 4 files (Models, PhotoStore, FilterSidebar, ContentView). FlowLayout chips with counts. Empty sections auto-hide. ~2ms faceted recomputation for 9k images.

---

### 01:30 — Three Experiences *("Build me a web gallery with three ways to see the photos")*

**Intent.** The native curator app is for work — deciding what's good. But the photographs themselves deserve to be seen, explored, discovered. Not a grid-of-thumbnails photo gallery — three different ways to navigate through semantic space. La Grille (filter by vibes, grading, time, composition), La Dérive (drift through connected photos by shared meaning), Les Couleurs (explore by color palette and semantic pops).

**Architecture.** New data export script (`export_gallery_data.py`) queries the 634 analyzed photos from SQLite, extracts palettes, vibes, semantic pops, and precomputes a drift connection graph — top 6 neighbors per photo scored by shared vibes, color proximity, matching objects, and same setting. Outputs a single `photos.json` (1.3 MB) with everything the frontend needs.

**Design.** Dark (#0a0a0a), monospace, glassmorphism. No framework — vanilla HTML/CSS/JS. Glass tags with `backdrop-filter: blur(12px)` bloom on hover. Progressive image loading (micro → thumb → display). Justified row layout. Lazy loading via IntersectionObserver.

> Built `export_gallery_data.py`, `serve_gallery.py` (port 3000), and 6 web files: `index.html`, `style.css`, `app.js`, `grid.js`, `drift.js`, `colors.js`. 634 photos with full semantic data. Three experiences ready for iteration.

---

### 01:45 — The DNG Purple Cast *("this look like it is from DNG wrongly transformed")*

**Intent.** Render all 3,841 DNG files properly. They'd been through the pipeline but every image had a purple/magenta color cast.

**Root cause.** macOS `sips` converts DNG to TIFF in Display P3 color space. Pillow reads the pixels but saves to JPEG without converting to sRGB. Browsers and image viewers interpret the JPEG as sRGB, shifting reds and blues — hence the purple tint.

**Fix.** Added `-m /System/Library/ColorSync/Profiles/sRGB Profile.icc` to the `sips` command in `_decode_raw_sips()`. This converts to sRGB at decode time. Verified: re-rendered DNGs look correct.

> Fixed `render_pipeline.py`. Also switched `photography_engine.py` from API key to Vertex AI ADC (the key was the one that got committed and removed). Fixed `IMAGE_DIR` path and `find_gemini_jpeg` to match flat layout.

---

### 02:00 — The `rendered/originals/` Saga *("why does this folder still exists?")*

**Intent.** Keep the rendered directory clean and organized. One layout, no duplicates, no confusion.

**What went wrong.** The render pipeline's `output_dir` defaulted to `rendered/originals/` — which kept recreating the folder after every deletion. Meanwhile, the first batch of images (5,138 JPEGs) was in a flat layout (`rendered/{tier}/jpeg/{uuid}.jpg`) and the DNG re-renders landed in a nested layout (`rendered/originals/{tier}/jpeg/{cat}/{sub}/{uuid}.jpg`). Two different layouts, two different folders, total mess.

**Lesson.** Before re-running a pipeline that creates files, check where it outputs. Don't just purge DB entries and re-run — verify the `output_dir` matches the expected layout first.

**Resolution.** Fixed `render_pipeline.py` to output directly to `rendered/` (not `rendered/originals/`). Removed category subdirectories from tier paths (flat layout: `rendered/{tier}/{fmt}/{uuid}.ext`). Moved 38,410 DNG tier files from nested to flat. Deleted `rendered/originals/` for good. The canonical layout is now:

```
rendered/
  {tier}/jpeg/{uuid}.jpg
  {tier}/webp/{uuid}.webp
  original/jpeg/{uuid}.jpg   ← native-resolution JPEG (only for JPEG-sourced)
```

---

### 02:10 — Fixing MADCurator *("the vibe label look wrong with some ]")*

**Intent.** The native curator app was showing garbled vibe labels like `"Candid"]·11` instead of `Candid·11`.

**Root cause.** The `vibeList` computed property in `Models.swift` was splitting the vibe string on commas — but the DB stores a JSON array (`["Moody", "Nostalgic", "Stylish"]`). Splitting `["Moody", "Nostalgic", "Stylish"]` on `,` gives `["Moody"`, `"Nostalgic"`, `"Stylish"]`.

**Fix.** Replaced comma-split with `JSONSerialization` parsing. Also added collapsible vibe filter: vibes with 5+ photos shown by default, rest behind "all X more" toggle. Updated `Database.swift` to load `tiers.local_path` from DB so thumbnails work regardless of file layout.

> Fixed 3 files: Models.swift, FilterSidebar.swift, Database.swift + PhotoStore.swift.

---

### 11:00 — Camera Provenance *("analog where images taken with Leica MP camera with film")*

**Intent.** Every photograph has a camera behind it, and every camera has a personality. The Leica MP shoots Kodak Portra 400 VC — vivid color film that shifts warm under tungsten light, which explains the white balance problems on night shots. The Leica M8 has a CCD sensor with known IR contamination that adds magenta to dark fabrics. The Leica Monochrom has no Bayer filter — pure B&W sensor, never apply color corrections. The Canon G12 is a compact with the worst auto white balance in the set. The DJI Osmo Pro and Memo are action cameras with wide lenses.

**Why it matters for auto-enhance.** Generic color correction treats every image the same. But a warm-shifted Portra night shot needs different treatment than an IR-contaminated M8 frame. The camera body tells us *what kind of wrong* the image is. The film stock tells us *what kind of grain* is an asset vs. artifact. This is the difference between fixing and destroying.

> Added `camera_body`, `film_stock`, `medium`, `is_monochrome` columns to `images` table. Built migration system in `mad_database.py`. Populated all 8,807 images from category/subcategory mapping. 77 Analog shots detected as monochrome via Gemini grading_style.

---

### 11:15 — Pixel-Level Analysis *("run programatic image analysis")*

**Intent.** Gemini tells us *what's in the photo* — vibes, composition, mood. But for auto-enhance we need to know *what's wrong with the pixels*. Histogram shape, white balance deviation, contrast ratio, noise level, saturation distribution. Two complementary data sources: semantic (Gemini) + technical (pixel math).

**Architecture.** New script `image_analysis.py` reads each display-tier JPEG (2048px), converts to numpy arrays, and computes 20 metrics: luminance histogram (clipping, dynamic range, low/high key), channel means and WB shifts, color cast classification, HSV saturation, dominant hue via circular mean, Michelson contrast, Laplacian noise estimate. Results stored in new `image_analysis` table. 16-bin per-channel histograms stored as JSON for visualization.

**Results.** 8,763 images analyzed at 28/s. The data immediately reveals camera-specific patterns:

| Camera | WB Red | Color Cast % | Noise | Shadow Clip |
|--------|--------|-------------|-------|-------------|
| Leica M8 | +0.091 | 66% | 1.5 | 11.6% |
| DJI Osmo Pro | +0.042 | 61% | 1.4 | 1.8% |
| Leica MP (Portra) | +0.063 | 68% | 4.3 | 11.2% |
| Leica Monochrom | 0.000 | 0% | 1.7 | 21.3% |
| Canon G12 | +0.167 | 80% | 1.9 | 12.7% |

The Portra film grain (noise=4.3) is 3× higher than digital cameras — that's real silver halide texture we want to preserve, not denoise. The Canon G12 has the worst white balance (+0.167 red shift) and 80% of its images need correction. The Leica Monochrom confirms zero color cast, zero saturation — only tone curves needed.

> Created `image_analysis.py`, added `image_analysis` table to schema. 8,763 images analyzed in ~310s.

---

### 11:30 — Camera Filter in MADCurator *("in the app I should see the filters for Camera")*

**Intent.** Now that every image knows its camera, the curator should let you filter by it. See all Leica MP shots together, compare Canon G12 against M8 side by side.

> Added camera_body to PhotoItem, FilterDimension, FilterState, FacetedOptions. Added "Camera" section to FilterSidebar. Added Camera metadata section to DetailView (body, film stock, medium, monochrome). App rebuilt successfully.

---

### 12:00 — Apple-Grade Design Upgrade *("Elevate MADCurator to Apple HIG standards")*

**Intent.** The functional app worked but looked utilitarian. The photographs deserve a frame that does them justice — polished interactions, refined materials, meaningful animations. Photography-first design where the UI recedes and the images breathe.

**What changed across 6 files:**

*Models.swift* — Added `SemanticPop` struct with color-to-NSColor mapping, `paletteColors` computed property (parses hex from Gemini's raw_json color palette), `semanticPopsList` parser, and `NSColor.fromHex` extension. Also added `colorPaletteJSON` field loaded from DB via `json_extract()`.

*ImageGrid.swift* — Grid now breathes: minimum 160px/maximum 240px cells with 4pt spacing. Thumbnails use `.fit` instead of `.fill+clip` to show actual composition. Hover effect with subtle 1.02 scale + shadow via spring animation. Selection replaced hard border with rounded overlay ring + spring. Rejected photos fade to 0.3 AND desaturate. Right-click context menu: Keep/Reject/Copy UUID.

*DetailView.swift* — Hero image fills width with no height cap, black surround. Camera badge shows SF Symbol + body name + film stock inline. Color palette as 5 colored circles (the requested color pills). Semantic pops as colored dot + object label in pills. Alt text in quoted block style with accent-colored left border. Vibes rendered as glass pills using `.ultraThinMaterial` with subtle border. Curation buttons wider with press scale animation. Section headers now have SF Symbol icons. Spacing increased to 20pt between sections.

*FilterSidebar.swift* — Every section gets an SF Symbol icon (camera, paintpalette, sparkles, clock, mappin, cube, etc). Active sections show accent-colored icon + dot indicator. Filter chips darken on hover. Search field taller with clear button. Sidebar uses `.regularMaterial` for vibrancy. `@FocusState` added for search field.

*ContentView.swift* — Empty state shows camera.viewfinder icon + lighter weight text. Query bar operators styled as tiny pills. Active chips get subtle shadow. Toolbar moved to `.status` placement. Escape key deselects current photo. Removed duplicate onKeyPress handlers (menu commands handle k/r/arrows).

*MADCuratorApp.swift* — Unified toolbar style. View menu with sidebar toggle (Cmd+Opt+S).

> Built cleanly on first try. 6 files modified, 0 new files. The monospace aesthetic preserved throughout — it's intentional, not default.

---

### 12:30 — Vector Engine *("Store 3 vectors for each image for later use in navigation")*

**Intent.** The web gallery's La Dérive experience drifts through connected photographs — but the connections were computed from shared vibes and colors, which is shallow. Real visual similarity requires embeddings from models that actually *see* the image. Three different models for three different kinds of seeing:

- **DINOv2** (`facebook/dinov2-base`, 768d) — self-supervised vision transformer trained without labels. Sees composition, texture, spatial layout. Two images with similar geometric arrangements score high even if the subjects differ. This is the "artistic eye."
- **SigLIP** (`google/siglip-base-patch16-224`, 768d) — multimodal model with shared image/text embedding space. Sees meaning: "golden hour portrait" or "rainy street" as concepts. Enables text-to-image search. This is the "semantic brain."
- **CLIP** (`openai/clip-vit-base-patch32`, 512d) — similar to SigLIP but optimized for precise subject matching. Two photos of the same building score very high. This is the "duplicate detector."

**Architecture.** `vector_engine.py` processes one model at a time (to fit in memory), extracts L2-normalized vectors on Apple Silicon MPS, stores them in LanceDB as FixedSizeList float32 arrays. PyArrow schema ensures proper vector types for cosine similarity search. Incremental processing — only new images get vectorized.

**Modes:** `--search UUID` (find similar via all 3 models), `--text "query"` (semantic search via SigLIP), `--duplicates 0.95` (find near-dupes via CLIP).

**Dependencies installed:** PyTorch 2.8.0 (MPS), Transformers 4.57.6, LanceDB 0.27.1, sentencepiece, protobuf. All models verified working on MPS with 20 test images. Ready for full 9,276-image extraction.

> Created `vector_engine.py`. Tested extraction + LanceDB storage + similarity search on 20 images. Three distinct similarity rankings confirmed — each model sees differently.

---

### 13:00 — Full Vector Extraction *("go")*

**Intent.** Run all 9,276 images through all three models. The 20-image test proved the pipeline works — time to fill the database.

**Results.** 9,011 images vectorized (265 skipped — no display tier file). All three models completed on MPS:

| Model | Vectors | Time | Dimension |
|-------|---------|------|-----------|
| DINOv2 | 9,011 | 6m 12s | 768 |
| SigLIP | 9,011 | 5m 47s | 768 |
| CLIP | 9,011 | 5m 28s | 512 |
| **Total** | **9,011 triples** | **17.6 min** | — |

Processing rate: 8.8 images/second across all three models. LanceDB stores 9,011 rows with proper `FixedSizeList<float32>` columns. Similarity search, text search, and duplicate detection all verified working on the full dataset.

> `vectors.lance/` — 9,011 complete vector triples. Ready for La Dérive integration.

---

### 13:30 — Full System Dashboard *("Show me all that is there, all the stats")*

**Intent.** The original dashboard showed Gemini analysis progress, category tables, render tiers, and variant generation — about 40% of the system. Missing: camera fleet with per-body pixel metrics, pixel analysis distributions (color cast, color temperature), vector store status, curation progress, Gemini semantic insights (vibes, time of day, setting, exposure, composition), source format breakdown, and storage usage. The user wanted one page that shows everything.

**What changed.** Complete rewrite of `generate_status_page.py`. The `get_stats()` function now collects 40+ fields from 6 tables plus LanceDB. The HTML template gained 8 new sections: top stat cards row (8 cards with sub-labels and status badges), Camera Fleet table (body, count, medium, film stock, luminance, WB shifts color-coded red/blue, noise, shadow clip), Pixel Analysis (color cast pills with colored dots, color temperature distribution), Vector Store (3 model cards with descriptions, row count, disk size, completion badge), Gemini Insights (3-column grading/time/setting tables, exposure/composition/vibe/rotation pills), Curation progress, Storage summary, and source format breakdown.

> Rewrote `generate_status_page.py` — 1,635 lines (was 1,367). 8 stat cards, 13 sections, live-polling every 5s. All routes preserved: `/journal`, `/blind-test`.

---

## 2026-02-06

### 14:20 — Dashboard Left Sidebar Navigation & Tier Format Fix

**Intent.** Two user requests: (1) the Render Tiers table showed file counts nearly double the image counts with no explanation — needed to clarify that display/mobile/thumb/micro tiers produce both JPEG and WebP; (2) add a persistent left sidebar navigation to access all dashboard sections and the Journal without scrolling.

**What changed.** Layout restructured from single centered column to `display: flex` with a 200px sticky sidebar + main content area. Sidebar has grouped links (Analysis, Insights, Pipeline, Data) with scroll-spy highlighting that tracks the active section. All 13 sections got anchor IDs. The Render Tiers table gained JPEG/WebP columns and an explanatory note. Responsive: on mobile the sidebar collapses to a horizontal link bar. Also verified camera-friendly subcategory names are working (Leica Digital, Leica Analog, Leica Monochrom, Canon G12, DJI Osmo Pro, DJI Osmo Memo).

> Dashboard now has proper navigation. Tier breakdown shows: full/gemini/original = JPEG only, display/mobile/thumb/micro = JPEG + WebP.

---

### 14:30 — Signal Extraction Progress Check

The 5-phase signal extraction (launched previous session) is running through 9,011 images:
- **EXIF metadata**: 9,011/9,011 — complete (1,820 with GPS coordinates)
- **Dominant colors**: 45,051 rows (9,011 × 5 clusters) — complete
- **Face detection**: 3,187 faces found so far — in progress
- **Object detection**: 1,418 objects found so far — in progress
- **Perceptual hashes**: pending

> Still running. YuNet face detection and YOLOv8 object detection processing through the collection.

---

### 15:00 — Signal Extraction Complete

All 5 phases finished in 21 minutes (1,256s). Final results:
- **EXIF metadata**: 9,011 rows (1,820 with GPS)
- **Dominant colors**: 45,051 clusters (5 per image, K-means in LAB space)
- **Face detection**: 5,686 faces across 1,676 images (YuNet, 31 img/s)
- **Object detection**: 14,931 detections across 5,363 images (YOLOv8n, 29 img/s)
- **Perceptual hashes**: 9,276 rows with pHash/aHash/dHash/wHash + blur/sharpness/entropy

Top objects: person (4,752), car (3,603), traffic light (1,051), cat (977). Dashboard now shows actual color pills (colored circles from average RGB per color name) instead of text, and object labels correctly.

> Every photograph now has: EXIF, 5 dominant colors, face boxes, object labels, 4 perceptual hashes, quality metrics. Combined with Gemini analysis + pixel analysis + 3 vector embeddings = comprehensive signal coverage.

---

### 15:10 — Dashboard Polish

Render Tiers table now shows each tier/format separately (e.g. `display/jpeg`, `display/webp`) instead of trying to merge them. Removed the Recent Analyses section (Sample Gemini Output is sufficient). Color pills render as actual colored circles with counts. Object detection shows real YOLO labels.

---

### 15:30 — Unified Pill/Tag Design System

**Intent.** Every data dimension — grading, time of day, setting, categories, cameras, vibes, colors, objects — used a different visual format: some tables, some inline text, some badges. They all represent the same thing: a filterable label with a count. The user pointed out these will become clickable filters, so they need one consistent format.

**What changed.** Converted all data sections from `rows()` (table format) to `pills()` (dark background, white text, rounded corners). Pill CSS: `background: var(--fg)`, label bold, count semi-transparent. Color pills special-cased with actual colored circles from averaged RGB values. Section title hierarchy: parent headings (GEMINI INSIGHTS, CAMERA FLEET) are black, larger, bold with bottom border; sub-headings (Grading, Time of Day) are smaller, muted gray. Layout: Gemini Insights first two rows in three-column grid.

> Every data point in the dashboard now speaks the same visual language. Ready for filter interaction.

---

### 16:00 — Multi-Page Architecture

**Intent.** The dashboard sidebar navigation was only on the main page. The README, Journal, Mosaics, and Blind Test pages were standalone HTML — no sidebar, no consistent navigation. The user wanted the same left menu on every page.

**What changed.** Created `page_shell(title, content, active="")` — a shared HTML wrapper that provides the sidebar + flex layout for any sub-page. The sidebar highlights the active page. Updated `render_readme()`, `render_journal()`, and `render_mosaics()` to use `page_shell()` instead of standalone templates. Journal page preserves its markdown-specific CSS via embedded `<style>` block.

> All pages now share one navigation UI. The dashboard feels like one app, not separate pages.

---

### 16:15 — Mosaic Generation

**Intent.** See all 9,011 photographs at once — not scrolling through a grid, but tiled into one 4096px square image. Like a satellite view of the collection. Different sort orders reveal different patterns: sort by brightness and you see a gradient from black to white; sort by hue and you see a rainbow; sort by category and you see camera-specific color signatures.

**What changed.** Created `generate_mosaics.py` — reads micro tier (64px) thumbnails, arranges them in a square grid (~95×95 at 43px tiles), saves 4096px JPEG mosaics. 14 sort variants: random, by_category, by_camera, by_brightness, by_hue, by_saturation, by_colortemp, by_dominant_color, by_contrast, by_sharpness, by_time_of_day, by_grading, by_faces, by_latitude. Dimensions with partial data (time_of_day: 5,039 images, latitude: 1,820) produce smaller mosaics. Metadata saved to `mosaics.json`. Added `/mosaics` route and gallery page to dashboard.

> 14 mosaics totaling 93 MB in `rendered/mosaics/`. The by_hue mosaic is a particularly beautiful rainbow. The by_latitude mosaic (1,820 GPS-tagged images) reveals geographic patterns in shooting style.

---

### 16:30 — System Instructions Page

**Intent.** As the project grows, development principles need to be documented where both the user and the AI assistant can reference them. Not in a CLAUDE.md that only the AI sees — in the dashboard, visible to everyone.

**What changed.** Created `render_instructions()` function with comprehensive development guidelines organized into 8 sections: Vision (signal augmentation philosophy), Signal Completeness (every image gets every signal), Performance (batch processing, MPS acceleration, incremental work), Data Integrity (no duplicates, no orphans, flat layout), Code Quality (Python 3.9, type hints, error handling), AI Analysis (Gemini guidelines, camera-aware processing), Dashboard & Monitoring (real-time stats, journal discipline), and Current Signal Inventory (table of all 12+ signals with source/status). Added `/instructions` route and sidebar link on all pages.

> The project now has a living reference document accessible at http://localhost:8080/instructions.

---

### 16:45 — Gemini Processing Blocked

**Intent.** Resume Gemini analysis (55.9% complete, 3,972 images pending). Attempted restart but GCP Application Default Credentials have expired.

**Status.** `photography_engine.py` fails immediately with "Reauthentication is needed. Please run `gcloud auth application-default login`". All local/programmatic analysis is complete (EXIF, pixel, colors, faces, objects, hashes, vectors). Only Gemini semantic analysis remains blocked on re-authentication.

---

### 17:00 — The Enhancement Engine *("Pure signal-driven corrections")*

**Intent.** Every image has different problems. A warm Portra night shot needs different treatment than an IR-contaminated M8 frame. The Canon G12 has the worst auto WB. The Monochrom sensor is pure B&W — never touch color. We use all the signals we collected (pixel analysis, camera body, medium, film stock) to compute per-image recipes, not batch presets. No AI, no style transfer — pure deterministic corrections.

**Architecture.** New script `enhance_engine.py` with 6 camera profiles (`CameraProfile` dataclass) and 6 processing steps per image:

1. **White Balance** — Grey-world channel scaling. Strength varies: G12 at 0.7 (aggressive), M8 at 0.5 (careful — some warmth is CCD character), MP/Portra at 0.3 (preserve film warmth). Monochrom: skip entirely.
2. **Exposure** — Gamma correction toward 110-120 brightness. Guards against correcting intentional low-key/high-key. Film gets gentler correction.
3. **Shadow/Highlight Recovery** — Selective tone curve. Lifts crushed shadows, pulls blown highlights. Monochrom exception: only recover if clipping > 30% (heavy shadows are stylistic).
4. **Contrast** — Adaptive S-curve applied to luminance only (preserves color). Strength from 0 (skip) to 0.6 (strong) based on measured contrast ratio.
5. **Saturation** — HSV scaling. Monochrom: skip. Portra: cap at 1.10x (already vivid). G12: up to 1.20x (compact cameras are flat).
6. **Noise-Aware Sharpening** — Pillow UnsharpMask. Film (noise>3): radius=0.8, percent=40 (preserve grain). Clean digital: radius=1.5, percent=80. Monochrom: crisp edges.

**Results.** 20-image test batch at 17 images/second, 0 errors. Camera-specific corrections verified:
- M8: WB shift reduced from +0.085 to +0.040 (50% correction)
- Monochrom: zero color change (WB untouched)
- G12: WB reduced from +0.188 to +0.066 (aggressive 70%)
- MP/Portra: WB from +0.412 to +0.275 (gentle 30% — preserving film warmth)

New DB table `enhancement_plans` stores every recipe as queryable JSON with pre/post metrics. Output: `rendered/enhanced/jpeg/{uuid}.jpg` at 2048px for review.

> Created `enhance_engine.py`, added `enhancement_plans` table to `mad_database.py`. Ready for full 9,011-image run.

---

### 17:15 — The Endgame Vision *("The incredible experience")*

**Intent.** A fundamental clarification of the project's architecture. Two audiences, two apps, one pipeline.

**The private side**: MADCurator (native SwiftUI app) is the review tool. The user examines every image — original, enhanced, AI variants — and accepts or rejects. This is where curation happens: the human eye decides what's worth showing.

**The public side**: The web gallery (La Grille, La Dérive, Les Couleurs) shows ONLY accepted images. No pending, no rejected. The experience is curated. Every photograph that makes it to the public gallery was looked at, considered, and chosen.

**New images**: The collection grows. New photographs get dropped into `originals/`. The pipeline handles incremental ingestion: register → render tiers → pixel analysis → Gemini analysis → signal extraction → vector embeddings → enhancement → curation. Every script already supports incremental mode (skip existing, process new).

> This is the architecture going forward: signal everything, enhance everything, curate selectively, publish only the best.

---

### 17:20 — Gemini Re-authenticated

**Intent.** Resume the stuck Gemini analysis (5,039/9,011 done, 3,902 remaining). User re-ran `gcloud auth application-default login`. Vertex AI client verified working. Relaunched `photography_engine.py` in background.

> PID 92782 running. 3,902 images to analyze.

---

### 17:30 — Full Enhancement Run *("I want it all")*

**Intent.** Run the enhancement engine on every single photograph in the collection.

**Results.** 9,256 images enhanced in 282 seconds. Zero errors. 32.8 images/second with 8 workers. Every image now has a camera-aware enhanced copy at `rendered/enhanced/jpeg/{uuid}.jpg` (2048px, JPEG quality 92).

Before/after metrics confirm camera-specific corrections are working as designed:
- **Leica M8** (3,533 images): WB shift +0.090 → +0.047 (47% correction)
- **Leica Monochrom** (1,099 images): WB unchanged at 0.000 (never touched)
- **Canon G12** (137 images): WB shift +0.167 → +0.060 (64% correction, most aggressive)
- **Leica MP** (1,126 images): WB shift +0.063 → +0.038 (40% correction, preserving film warmth)
- **DJI Osmo Pro** (3,032 images): WB shift +0.057 → +0.026 (54% correction)

Steps applied across the collection: 78% WB correction, 100% sharpening, 49% saturation, 44% shadow/highlight recovery, 42% contrast, 37% exposure correction. Each recipe is saved in the `enhancement_plans` table with full before/after metrics.

> `rendered/enhanced/jpeg/` — 9,256 enhanced images. Ready for review in MADCurator.

---

### 17:40 — Dashboard Responsive + GitHub Pages Deployment

**Intent.** The dashboard (`docs/index.html`) is what shows on GitHub Pages. It needed to be fully responsive for mobile/tablet, and show the timestamp of when it was last generated. Also needed a GitHub Actions workflow to auto-deploy on push.

**What changed.** Added mobile breakpoints: tables get horizontal scroll wrapper (`.table-wrap`) so they don't break layout on narrow screens. Stats grid goes to single column below 440px. Stat card values shrink on mobile. Static build now embeds generation timestamp in the subtitle ("snapshot 2026-02-06 13:41 UTC"). Sidebar links redirect to GitHub URLs in static mode (no server routes). Created `.github/workflows/deploy-dashboard.yml` — deploys `docs/` to GitHub Pages on push to main.

> Dashboard is responsive. Workflow ready. Run `python3 generate_status_page.py` before pushing to update the snapshot.

---

### 18:30 — MADCurator Major Upgrade: Location Intelligence + All Signals + Power UX

**Intent.** Transform MADCurator from a curation-only tool into the ultimate image intelligence console. Every signal the pipeline has collected (EXIF, aesthetic scores, depth maps, scene classification, style labels, captions, OCR, emotions, enhancements, face/object counts) should be visible in the detail panel. Add a location system with GPS pre-population, manual tagging, and temporal propagation. Add enhanced image comparison. Add power keyboard shortcuts for speed.

**What changed across 9 files:**

*Python (1 file):* `mad_database.py` — New `image_locations` table (uuid, location_name, lat/lon, source, confidence, propagated_from, accepted).

*Swift (8 files):*
- **Models.swift** — PhotoItem grew from ~25 fields to ~55 fields. Added location (7 fields), aesthetic score (2), depth estimation (4), scene classification (6), style (2), caption, OCR, emotions, EXIF date/GPS, enhancement metrics (7), detection counts (2). New computed properties: `aestheticStars`, `aestheticBucket`, `scenesList`, `hasLocation`, `hasEnhancement`, `hasOCRText`. New filter dimensions: location, style, aesthetic, hasText.

- **Database.swift** — `loadPhotos()` query now JOINs 9 tables (was 3): images, gemini_analysis, tiers(x2), image_locations, aesthetic_scores, depth_estimation, scene_classification, style_classification, image_captions, exif_metadata, enhancement_plans. Plus 4 correlated subqueries for object/face counts, OCR text aggregation, and emotion summaries. New methods: `setLocation()`, `propagateLocation()` (temporal scoring: same-day=0.95, ±1d=0.85, ±3d=0.70, ±7d=0.60), `acceptLocation()`, `rejectLocation()`.

- **PhotoStore.swift** — 4 new filter dimensions with faceted counts. `showEnhanced` toggle state. `isFullscreen` mode. `showInfoPanel` toggle. `currentImagePath()` switches between display and enhanced tier. Location set/accept/reject with automatic propagation + data reload. Search now includes location, caption, OCR text.

- **FilterSidebar.swift** — 4 new sections: Location (mappin.and.ellipse icon), Style (theatermasks), Aesthetic (star, with Excellent/Good/Average/Poor buckets), Has Text (text.viewfinder, boolean yes/no).

- **DetailView.swift** — 9 new signal sections: EXIF (date taken + GPS coords), Location (editable field + confirm, propagated accept/reject), Caption (BLIP italic text), Aesthetic (5-star rating with orange stars), Style (purple badge + confidence), Scene (top 3 as pills with percentages), Depth Map (near/mid/far colored percentage bars), Enhancement (before→after metrics with delta arrows), OCR (quoted block with yellow accent), Emotions (pills), Detections (face/object counts). Enhanced/Original badge on hero image. Enhanced toggle button in curation bar.

- **ContentView.swift** — New keyboard shortcuts: E (toggle enhanced), Space (fullscreen), I (toggle info panel), Y (accept propagated location), N (reject propagated location). Fullscreen mode renders black background with just the image. Info panel toggle shows image-only view.

- **ImageGrid.swift** — Location pin icon (mappin.circle.fill) on thumbnails for geolocated images. Aesthetic score indicator (top-right corner) color-coded green/orange/red.

- **MADCuratorApp.swift** — New View menu: Toggle Enhanced (E), Toggle Info Panel (I), Toggle Fullscreen (Space), Focus Search (Cmd+F).

**Build.** All 8 Swift files compile cleanly in 4.11 seconds. Zero warnings, zero errors.

> MADCurator now surfaces every signal collected by the pipeline. 55 data fields per image, 18 filter dimensions, 11 keyboard shortcuts.

---

### 14:30 — Dashboard Redesign: Apple HIG Design System + Dark Mode + HF-Style Tags

**Intent.** The old dashboard used monospace fonts, hardcoded hex colors, raw pixel values, and a flat monochrome aesthetic. The user wanted a proper design system with Apple rigor, a dark mode toggle, and HuggingFace-style tags with category icons.

**What changed.** Complete rewrite of the dashboard's visual layer in `generate_status_page.py`:

*Design Token System (Apple HIG):*
- **Typography**: SF Pro Display for headings, SF Pro Text for body, SF Mono for data. 8-step type scale (11px to 34px) matching Apple HIG.
- **Spacing**: 4px-based scale (--space-1 through --space-16). Every margin, padding, and gap uses tokens.
- **Colors**: Apple system palette (blue, green, indigo, orange, pink, purple, red, teal, yellow, mint, cyan, brown) as CSS variables.
- **Radius**: 4-level scale (6px, 10px, 14px, 20px, 9999px). Cards get --radius-lg, badges get --radius-sm, pills get --radius-full.
- **Shadows**: 3 levels (sm, md, lg) that adapt to dark mode.
- **Transitions**: Shared easing curve and duration tokens.

*Dark/Light Theme:*
- Theme toggle in sidebar bottom (sun/moon icon). State persists via localStorage.
- Light theme default. All 25+ semantic color tokens switch between themes via `[data-theme]` selectors.
- Theme-aware: badges, tags, cards, tables, progress bars, JSON syntax highlighting all adapt.

*HuggingFace-Style Tags:*
- New `.tag` component with colored icon square + label + count. Replaces flat `.pill` class.
- 14 icon categories with Apple-colored tinted backgrounds: camera (blue), eye (indigo), palette (orange), sun (yellow), location (pink), scene (green), mood (purple), time (teal), style (pink), depth (mint), object (cyan), face (brown), format (gray), film (red).
- Dominant color tags use actual color dots instead of icons.

*New Dashboard Section — Advanced Signals:*
- **Depth Estimation**: Animated near/mid/far percentage bar (blue/teal/indigo), complexity buckets as tags. Shows 9,011 images analyzed, avg near 54.2%, mid 25.1%, far 20.8%.
- **Scene Classification**: Top 15 scenes as tags, environment breakdown (indoor/outdoor/unknown). 9,011 classified.
- **Enhancement Engine**: Status tags showing all 9,011 images enhanced.
- **Locations**: Source breakdown, GPS from EXIF count (1,820).

*Token Audit:*
- All sub-pages (Journal, Mosaics, Instructions, Blind Test) migrated from hardcoded hex/rem to design tokens.
- Zero raw hex colors in PAGE_HTML CSS. Zero raw pixel values outside token definitions.
- All `rgba()` values are intentional opacity modifiers for overlays/shadows, not standalone colors.

*`get_stats()` extended:*
- 15 new data fields: aesthetic_count/avg/min/max/labels, depth_count/avg_near/mid/far/complexity_buckets, scene_count/top_scenes/scene_environments, enhancement_count/statuses, location_count/sources/accepted.
- Total stats dict: 70 keys (was ~55).

**Discovered.** Scene classification already ran to completion (9,011 images) since last check. Aesthetic scores show poor discrimination — all 9,011 images rated "excellent" with scores 8.22-10.0. This model needs recalibration.

## 2026-02-06

### 16:15 — Drift Page: Vector Nearest Neighbor Visualization

Built a new `/drift` page for the dashboard. The concept: sample 10 random images, and for each one, show the 4 nearest neighbors according to each of the 3 embedding models (DINOv2, SigLIP, CLIP). This creates a visual comparison of what each model "sees" — DINOv2 finds composition and texture similarity, SigLIP finds semantic meaning, CLIP matches subjects.

Implementation: `render_drift()` function queries LanceDB directly (0.02s per search), serves thumbnails via new `/thumb/{uuid}` endpoint from `rendered/thumb/jpeg/`. Each section is a card with 3 rows (one per model), showing the query image (blue border) and 4 neighbors with L2 distance overlays. Design uses existing Apple HIG design tokens. "Reshuffle" link reloads for a new random sample.

### 16:18 — Running 3 Missing Analysis Models in Parallel

Launched 3 concurrent `advanced_signals.py` processes:
- **OCR/Text Detection** (EasyOCR) — 793/9,011 done, continuing from previous partial run
- **Image Captions** (BLIP) — 0/9,011, loading model on MPS
- **Facial Emotions** (DeepFace) — FAILED: `No module named 'tensorflow'`

Installing TensorFlow + DeepFace to unblock the emotions phase. The other two processes are running in parallel, each writing to separate DB tables so no conflicts. OCR uses CPU (EasyOCR limitation on MPS), BLIP runs on Apple Silicon GPU.

### 16:45 — TensorFlow Broke Everything

Installing TensorFlow 2.20 + Keras 3.10 for DeepFace caused a C++ mutex crash in PyTorch/transformers. BLIP couldn't even load on CPU — `libc++abi: terminating due to uncaught exception of type std::__1::system_error: mutex lock failed`. Solution: uninstall TensorFlow entirely, rewrite the emotions phase to use `trpakov/vit-face-expression` (a ViT model that runs on PyTorch). Fixed column name mismatch in face_detections (`w`/`h` not `width`/`height`). Added SQLite retry logic with exponential backoff for concurrent write locks. All 3 models now running in parallel successfully.

### 17:10 — Dashboard UI Overhaul: Tags, Sidebar, README

Replaced all ugly icon-squares on tags with emojis — scenes get landscapes, cameras get camera emoji, locations get pins, vibes get sparkles, etc. Reduced tag border-radius from full pill to 6px. Added more padding for breathing room. Enhancement section now shows camera body breakdown (Leica M8: 3,533, DJI Osmo Pro: 3,032, etc.) instead of just "enhanced: 9,011".

Restructured sidebar: removed "Pages" header, put README on top, renamed main dashboard to "State". Grouped Drift, Blind Test, and Mosaics under collapsible "Experiments" section. Dashboard section anchors now toggle open/closed.

Rewrote README with project vision: the 3 apps (See/Show/State), the intent, the full pipeline. Fixed image count everywhere from 11,557 to 9,011 (the actual count in originals/).

Journal de Bord entries now render as Twitter/X-style cards with borders, rounded corners, hover effects, and thread connector lines between entries.

### 17:30 — SVG Icon System for Tags

User feedback: emojis too noisy. Replaced all emoji tags with a custom inline SVG icon system — 16 hand-picked icons (camera, scene, depth, pin, palette, sun, star, sunset, bulb, frame, sparkle, rotate, film, box, eye, home). Each tag calls `tags(data, containerId, iconKey)` which looks up the SVG from the `IC` map. Clean, colored, consistent. Taller padding for breathing room.

### 17:45 — Apple.com-Style README & System Instructions Update

README page redesigned with apple.com-inspired cards: max-width 640px, generous whitespace, styled tables, refined typography. System Instructions page updated with current signal inventory — 16 signals total (9 complete, 3 in progress, 4 not started). Removed "Future Signals" section that was outdated — most of those are now running.

### 18:00 — Enhancement Engine V2: Signal-Aware Processing

Built `enhance_engine_v2.py` — a new enhancement engine that uses ALL available signals to make per-image editing decisions. Beyond the v1 camera-aware pixel metrics, v2 incorporates:

- **Depth estimation** — foreground-dominant scenes get sharper contrast, landscapes get atmospheric protection
- **Scene classification** — warm interiors get warmer WB, nature scenes get saturation boost, dark scenes get shadow lift
- **Style classification** — street photography gets higher contrast + desaturation, portraits get softer processing
- **Gemini vibes** — moody images stay darker with more contrast, vibrant images get saturation boost, golden hour gets warmth
- **Face detection** — images with faces get more conservative exposure correction and gentler sharpening

The engine reads all signals via LEFT JOINs (works even without all signals), computes a layered recipe where each signal modulates the base camera profile, and outputs to `rendered/enhanced_v2/jpeg/`. Includes `PRAGMA busy_timeout=120000` and 10-retry loops for SQLite contention.

### 18:15 — Blind Test Redesign: True 3-Way Comparison

Rewrote the blind test page for a proper A/B/C comparison. New design:
- 100 rows, each with Original + Enhanced v1 + Enhanced v2 in **random order per row**
- No labels until reveal — images marked only A, B, C
- Selected image elevates with shadow and blue border (translateY -4px, 24px box-shadow)
- Live scoreboard showing picks vs. remaining
- Reveal shows color-coded horizontal bar chart (Original=gray, V1=blue, V2=green)
- `prep_blind_test.py` script handles diverse sampling across cameras and styles

Stopped OCR process temporarily (12+ hours ETA, 0.2/s) to reduce DB contention — was causing lock failures across all processes. Captions and emotions continue running.

### 18:30 — V2 Enhancement Complete: 9,276 Images, Zero Errors

Enhancement Engine V2 completed in 427.7 seconds (21.7 images/s). All 9,276 images processed with zero errors. The signal-aware recipes work — each image now has a second enhanced version that was computed using depth, scene, style, Gemini vibes, and face detection data. Output lives in `rendered/enhanced_v2/jpeg/`.

Blind test generated: 100 diverse images sampled across all 6 cameras (41 M8, 33 Osmo Pro, 12 Monochrom, 12 MP, 1 G12, 1 Memo). Each row has 3 versions (original, v1, v2) in random order — all 6 permutations represented. The moment of truth: http://localhost:8080/blind-test

### 18:35 — Hero Landing on State Dashboard

Added a hero section to the State dashboard. Full-bleed brightness-sorted mosaic (9,011 tiny images) as background with dark gradient overlay. Title: "MADphotos / 9,011 photographs". Mission statement explains the per-image intelligence philosophy. Responsive down to 440px. Hero mosaic resized to 1200px (513KB) for GitHub Pages. Pushed and deployed.

### 18:40 — Git Push: The Big One

37 files, 16,564 insertions. The full pipeline code, all 3 apps (See/Show/State), 16 analysis signals, dual enhancement engines, blind test system, web gallery, GitHub Pages deployment workflow. OCR restarted after the v2 enhancement freed up DB locks.

## 2026-02-06

### 17:30 — OCR Sharding: 3x Parallel Workers

OCR was crawling at 0.2/s — 12+ hour ETA for 8,000 remaining images. Added `--shard N/M` argument to `advanced_signals.py` that partitions work by `hash(uuid) % M == N`. Killed the single OCR process and launched 3 parallel workers: shard 0/3 (2,684 images), shard 1/3 (2,733), shard 2/3 (2,671). Each runs its own EasyOCR reader on CPU. Combined throughput should be ~0.6/s, bringing ETA down to ~4 hours. Emotions already at 1,367/1,676 — almost done on its own.

### 17:45 — The Landing Page: Magazine-Quality README

Created a gorgeous dark-themed landing page for GitHub Pages (`docs/index.html`). Full-viewport hero with the brightness-sorted mosaic, giant "9,011" counter with gradient text, the mission statement, and a smooth-scroll "Explore" button. Below: navigation cards (State, Journal de Bord, GitHub) with colored accent borders, the camera collection list, three apps section (See/Show/State), the 9-stage pipeline with numbered step indicators, infrastructure grid, and 10 model pills. All mobile-first: base CSS is for phones, `min-width` media queries at 640px, 960px, 1200px. Pure dark (#0A0A0A) with Apple SF Pro typography.

Dashboard moved to `docs/state.html`. Added `.nojekyll` to bypass Jekyll processing. Sidebar links updated for static file routing.

### 17:55 — Dashboard: Card Redesign + Mobile Responsive

Removed the redundant Gemini Analysis progress section — that data was duplicated in the top cards. Redesigned top stat cards: replaced "Gemini AI", "Pixel Analysis", "GCS Uploads" with "AI Models Active" (shows X/10 models complete), "Enhanced" (enhancement plans with %), "Faces Found" (total faces + emotion count), "Vector Embeddings" (count × 3 models). Cards sorted by activity/interest.

Mobile CSS completely reworked: hamburger menu for sidebar at <900px with backdrop blur, sticky top bar, cards always 2-column on mobile, tables scroll horizontally, hero collapses gracefully (hides tagline/mission on small screens). Media queries switched from max-width to min-width (mobile-first).

### 19:10 — Landing Page: Mosaic Floats Right

Rewrote the landing page hero entirely. Instead of a full-width dark overlay image, the mosaic is now a beautiful rounded rectangle (`border-radius: 20px`, `box-shadow: var(--shadow-lg)`) floating to the right of the title and subtitle text on desktop, taking the height of the text content. On mobile (<700px), it stacks on top as a wide banner. The title "9,011" + "photographs, unedited" sits left, the rounded mosaic card sits right. Clean Apple layout — text breathes, image is decorative not dominant.

### 19:12 — Full Sidebar Sync + Collapse Toggle

Unified the sidebar across all 7 pages: README, State, Journal, Instructions, Drift, Blind Test, Mosaics. All pages now share the identical sidebar structure with the same links. Added a collapsible sidebar system: on desktop, a "Hide sidebar" button at the bottom collapses the sidebar to zero width with a smooth CSS transition; a floating hamburger button appears at the top-left to bring it back. State persisted in `localStorage` so it survives page navigation. On mobile (<900px), the collapse button is hidden — mobile uses the existing hamburger/top-bar pattern instead.

### 19:18 — Dashboard Cards: Element Table Redesign

Replaced the 8 plain white stat cards with a dramatic two-section layout inspired by periodic table element cards:

**3 Hero Cards** at the top — bold gradient backgrounds (blue, green, purple) with white text, showing Collection (9,011 photographs), Intelligence (total signals extracted across all models), and Output (rendered files + enhanced + AI variants).

**17-Element Intelligence Grid** below — each model gets its own tinted card with a unique hue-based color scheme (HSL custom properties), showing: model name, description, image count, a mini progress bar, and a status badge (complete/in-progress/pending). All 17 models listed: Gemini 2.5 Pro, Pixel Analysis, DINOv2, SigLIP, CLIP, YuNet, YOLOv8n, NIMA, Depth Anything v2, Places365, Style Net, BLIP, EasyOCR, Emotions, Enhancement Engine, K-means LAB, EXIF Parser. Each card's description includes live stats like "3,247 faces found" or "avg 4.8 aesthetic score."

### 19:18 — Static Site: All 6 Pages Generated

Ran `generate_static()` — successfully output all 6 pages to `docs/`: state.html (75KB), journal.html (36KB), instructions.html (18KB), drift.html (44KB), blind-test.html (112KB), mosaics.html (24KB). All sidebar links properly rewritten from server routes (`/journal`) to static paths (`journal.html`). Every page has the collapsible sidebar, theme toggle, and hamburger menu.

### 19:30 — GCS Bucket Architecture: Versioned Image Hosting

Designed and implemented a clean versioned structure for the GCS bucket. All images now live under `v/{version}/{tier}/{format}/{uuid}.ext`. The "version" dimension covers: `original` (base photographs), `enhanced` (camera-aware enhancement v1), `enhanced_v2` (signal-aware enhancement), and future AI variants. Each version has its own tier pyramid (display, mobile, thumb, micro). URL pattern is fully programmatic — any web app can construct image URLs from just a UUID and version name. Rewrote `gcs_sync.py` completely to support the new layout with `--version` and `--tiers` flags.

### 19:34 — Enhanced v1 Tier Rendering + GCS Upload Begins

Started rendering the enhanced v1 tier pyramid — the enhanced images existed only as 2048px JPEGs. Now generating mobile (1280px), thumb (480px), micro (64px) in JPEG + WebP for all 9,011 images. Original serving tiers (thumb JPEG/WebP: 132MB) already uploaded to GCS. Blind test images (300 files, 169MB) uploaded to `v/blind/` on GCS. Static pages updated to reference GCS URLs directly — no more local `docs/blind/` directory (saved 169MB from the repo).

### 19:35 — Blind Test Verdict: Enhanced v1 and v2 Are Nearly Identical

Investigation confirmed the user's observation: enhanced v1 and v2 differ by a mean of only 0.50 pixels (max 12). The v2 enhancement (signal-aware) adds subtle depth, scene, and style corrections on top of v1's base camera-aware processing — but the perceptual difference is negligible. For the "Show" web app, we'll focus on enhanced v1 as the primary improved version. All enhancement parameters are fully saved in `enhancement_plans` and `enhancement_plans_v2` tables for future recipe tuning.

### 19:44 — Enhanced v1 Tier Rendering Complete: Zero Errors

All 9,011 enhanced v1 images rendered into 7 tier/format combinations: display/webp, mobile/jpeg, mobile/webp, thumb/jpeg, thumb/webp, micro/jpeg, micro/webp. Zero errors across the entire batch. The `render_enhanced_tiers.py` script processed everything using 8 parallel workers, downscaling from the existing 2048px display-tier JPEGs with appropriate sharpening per tier.

### 19:48 — GCS Upload: Originals Complete, Enhanced In Progress

All original serving tiers successfully uploaded to GCS: display, mobile, thumb, micro in both JPEG and WebP — 8 directories, ~72K files total. Each directory got immutable cache headers (`max-age=31536000`). Enhanced v1 tiers uploading next — same 8 directories. Public URLs verified working: `https://storage.googleapis.com/myproject-public-assets/art/MADphotos/v/original/{tier}/{format}/{uuid}.ext`.

### 19:50 — State UI: GCS Filmstrip + Preload Animations

Added a horizontal filmstrip of 40 randomly sampled photographs below the manifesto on the State page. Images load from GCS (`v/original/thumb/jpeg/`) with a cubic-bezier fade-in animation — each image starts at `opacity: 0; scale: 1.08` and smoothly transitions to `opacity: 1; scale: 1` on load. Same treatment applied to drift page neighbor thumbnails. Removed all local image serving handlers — everything now served from GCS. No more `/thumb/` or `/blind/` local routes.

---

### 20:00 — State UI: Mosaic Hero + Compact Model Cards

**Intent.** User rejected the horizontal filmstrip ("why is there a row of images?"). Wanted a mosaic on the right side of the title area and more compact Signal Extraction cards.

**What changed.** Replaced the filmstrip with a mosaic-on-right hero layout: `.state-hero` flex container with text on left and a 280px rounded mosaic image on right, fading in with cubic-bezier animation on load. The 17-element intelligence grid cards were compacted dramatically: grid cells from 200px to 160px minimum, padding reduced to 8px, model descriptions and percentage labels hidden, font sizes shrunk, progress bars to 2px height. The result is a dense overview where all 17 models fit on screen without scrolling.

---

### 20:15 — Journal de Bord: Full Content + Event Type Labels + Genesis

**Intent.** The journal renderer was truncating all event content to first sentences and dropping paragraphs entirely. User wanted full event details as a beautiful stream with categorized event labels.

**What changed.** Complete rewrite of `render_journal()` in `generate_status_page.py`:

- **Full content**: Removed `first_sentence()` truncation and `skip_rest` logic. All paragraphs, blockquotes, lists, tables, and code blocks now render completely.
- **Event type labels**: Auto-classification system with 9 categories (Deploy, Infrastructure, Pipeline, AI, Investigation, UI/UX, Security, Architecture, Signal) using regex pattern matching on title + body. Each event gets up to 2 colored pill labels using `color-mix()` for subtle tinted backgrounds.
- **Removed intro sections**: "The Beginning" and "The Numbers" prose blocks no longer appear in the Journal de Bord — they were redundant with the timeline.
- **Genesis event**: Special indigo-bordered card at the bottom of the timeline summarizing the project vision: the 3 apps (See/Show/State), the mission, the endgame.
- **Rich formatting**: Tables render properly, code fences get `<pre><code>` blocks, **Solution.** and other bold-prefixed paragraphs get distinct styling, all markdown inline formatting (bold, italic, code) preserved.

---

### 20:30 — System Instructions: Complete Project Briefing

**Intent.** When starting a new AI session, context is everything. Added a comprehensive "Project Briefing" section at the top of the System Instructions page — everything a new session needs to be immediately productive: the 5 cameras with their quirks and enhancement rules, all 9 scripts with purposes, critical technical rules (Python 3.9, Vertex AI only, flat layout, DNG color space), hard-won lessons (Monochrom is sacred, film grain is an asset, TF+PyTorch don't mix, LAION scores are useless), GCS bucket structure, MADCurator architecture, web gallery setup, journal format, and a done/in-progress/next status summary. Rendered as an indigo-bordered card at the top of `/instructions`.

---

## 2026-02-06

### 22:00 — Show: 14 Image Experiences Built

**Intent.** Transform the web gallery from 3 experiences into 14 extraordinary ways to explore 9,011 photographs. Every signal extracted by the pipeline should power a different kind of encounter with the images.

> Complete rewrite of the web gallery architecture. Launcher page with 14 experience cards. New `export_gallery_data.py` exports ALL 9,011 images with 47 signal fields each (not just the 5,038 Gemini-analyzed). Four data files generated: `photos.json` (15.8MB), `faces.json` (315KB, 1,676 faces with emotions), `game_rounds.json` (49KB, 200 precomputed connection pairs), `stream_sequence.json` (336KB, palette-optimized viewing order).

**New experiences:** Le Bento (Mondrian mosaic with chromatic harmony), La Similarité (renamed from drift — semantic neighbors with inverted-index matching), La Dérive (new creative structural drift using composition/depth/brightness), Le Terrain de Jeu (connection game with 8s timer and streak scoring), Le Flot (infinite curated stream with monochrome breathers), La Chambre Noire (toggleable signal layers: colors, depth, objects, faces, OCR, metadata), Les Visages (face wall with emotion filtering), La Boussole (4-axis compass navigation), L'Observatoire (6 data panels: cameras, aesthetics, time, styles, emotions, outliers), La Carte (GPS dots on dark canvas map), La Machine à Écrire (weighted text search across all fields), Le Pendule (aesthetic taste test).

**Design system:** Category-colored tags (vibe=amber, grading=blue, time=golden, setting=green, scene=teal, emotion=pink, camera=silver, style=purple) with capitalized text, subtle borders, hover states. Applied across grid, lightbox, and all experiences.

---

### 22:30 — State Dashboard: Cleanup + Creative Direction + Self-Instructions

**Intent.** User flagged that State dashboard content was completely outdated. Project Briefing still said "3 experiences", Imagen Variants section was irrelevant, signal counts were stale.

> Removed Imagen Variant Generation section entirely (HTML, CSS, JavaScript). Updated Project Briefing: Show now lists all 14 experiences. Updated signal completion counts (Gemini 6,203/9,011, OCR complete, BLIP 8,933/9,011, Emotions 1,367/1,676). Updated "Done vs. Next" to reflect actual state. Added "Creative Direction for Show" section to instructions — signal-aware storytelling, emotional moments, minimalist UI.

**Self-instruction written:** Added mandatory rule to MEMORY.md — always update `generate_status_page.py` instructions when architecture changes, just like the journal. Also added creative direction mandate: Show experiences must be designed by someone who is simultaneously developer, architect, ML engineer, Apple-level designer, and emotionally intelligent creative director. Pairing two laughing faces IS funny. A rose next to rose accents IS pretty.

---

### 22:45 — State Instructions Page Restyled

**Intent.** User pointed out System Instructions page was completely outdated in style and content. Needed card-based layout, not a wall of text.

> Complete rewrite of `render_instructions()`: card-based layout with colored accent borders (indigo=briefing, pink=creative, green=status), 2-column grids for cameras and architecture, app trio boxes, category-themed signal inventory table. Added incremental ingestion pipeline card. Removed verbose Development Principles prose — replaced with compact actionable rules.

---

### 22:50 — State Dashboard: Category-Themed Tags + Compact Journal

**Intent.** Tags in State dashboard all looked identical. User wanted category-specific color theming like in Show. Journal events were too long — needed compact default with click-to-expand.

> Added 7 category color classes to State tags: vibe=orange, grading=blue, time=gold, setting=green, exposure=teal, composition=purple, camera=silver. Updated `tags()` JS function to accept category parameter. Journal events now collapsed by default — show title + labels + key "why it matters" line. Click toggles full body.

---

### 23:00 — Landing Page: Bold Mission + Game is ON

**Intent.** Mission statement needed to stand out. Changed "on different screens" to "on screens". Added "GAME IS ON." tagline.

> Mission text now bold black (weight 700) at base font size. Added uppercase "GAME IS ON." below in muted gray with caps tracking. Deployed to GitHub Pages.

---

### 00:30 — Signals Progressing Overnight

**Intent.** Check-in on all background analysis processes running since the previous session.

> Five processes still alive: 3 OCR shards (28%, 2,543/9,011), photography_engine for Gemini (68.9%, 6,210/9,011), facial emotions (79.7%, 2,541/3,187 faces). Face detections jumped from 1,676 to 3,187 — more faces discovered as analysis expanded. Emotions climbed from 1,367 to 2,541. BLIP captions stuck at 9,006/9,011 — 5 images blocked by SQLite locks from concurrent OCR shards. Will retry once OCR finishes.

---

### 01:00 — Emotions Bug: Normalized Coordinates Were Producing 1×1 Pixel Crops

**Intent.** The facial emotions process completed 2,545 face classifications, but investigation revealed ALL of them were garbage. Face detection stores coordinates as normalized values (0-1 range), but the emotion code treated them as pixel coordinates — producing 0×0 or 1×1 pixel crops fed to the ViT classifier. Every emotion label was nonsense.

> Fixed `advanced_signals.py` to multiply normalized coordinates by image dimensions before cropping. Added minimum crop size check (10px). Moved try/except to per-face level so one bad face doesn't skip the whole image. Deleted all bad emotion data. Re-running with --force, but OCR shards are locking the DB. Will retry once OCR finishes.

---

### 01:15 — La Dérive: Real DINOv2 Visual Drift

**Intent.** Transform La Dérive from metadata-based heuristics into real visual embedding similarity. The user wants incredible pairs: completely different images that share abstract visual structure — a bridge and a ribcage, a shoe and a ramp. DINOv2 captures texture and structure, not content.

> Precomputed 8 nearest DINOv2 neighbors for all 9,011 images (768d vectors, cosine similarity). Exported to `drift_neighbors.json` (5.2MB). Rewrote `drift.js` to load and navigate these embedding-based neighbors. Added `loadDriftNeighbors()` to `app.js`. Added subtle similarity score bar to neighbor cards.

---

### 01:20 — State: Accurate Signal Inventory + Sidebar Fix + "As of" Timestamp

**Intent.** State dashboard showed stale numbers ("16/16 signals, 6,203 Gemini"). The signal inventory claimed everything was done when only 12/18 signals were complete. Sidebar items shifted on click due to border-left appearing.

> Updated `render_instructions()` with accurate counts for all 18 signals (green checkmarks for complete, live numbers for in-progress). Fixed sidebar shift by giving all links a transparent 3px left border at baseline. Added "As of [date]" timestamp in hero subtitle for static deployments. Deployed to GitHub Pages and Firebase.

---

### 23:10 — Three Apps: Intent Over State

**Intent.** The Three Apps descriptions (Show, State, See) read like a feature list. They should express intent and purpose. Show exists to blow minds and delight. State is the control room. See is the native power viewer where the human eye decides.

> Rewrote all Three Apps descriptions in the briefing (System Instructions), Genesis event (Journal), and README.md. Removed "Then human curation. Then a public gallery that only shows the accepted best" — the apps speak for themselves now. Show leads the trio: "Blow people's minds. Continuously release new experiences guided by signals and new ideas. Delightful, playful, elegant, smart, teasing, revealing, exciting — on every screen."

---

### 23:15 — README Gets Card Layout

**Intent.** README page was plain rendered markdown while System Instructions had beautiful card-based layout with colored accent borders and pill labels. They should match.

> Rewrote `render_readme()` from a generic markdown-to-HTML converter into a section-aware card renderer. Each ## section becomes an `inst-card` with a colored pill label (Hardware/orange, Creative/pink, Architecture/blue, Infrastructure/teal). Three Apps section renders as `app-trio` boxes. Tables, lists, and ordered lists all render correctly inside cards.

---

### 23:19 — Similarity: Interactive Vector Explorer

**Intent.** The old Drift page was a static dump of 10 random images with their neighbors — no interaction, no navigation. The user described an interactive experience twice. Now it's real: a dynamic similarity explorer with a live API.

> Rewrote `render_drift()` into an interactive single-page app. Start with a random image shown large. Below it: 3 model sections (DINOv2/SigLIP/CLIP) each with an 8-neighbor grid. Click any neighbor to navigate there — it becomes the new query. Breadcrumb trail tracks your journey. Back button. Random button. New API endpoints: `/api/similarity/<uuid>` returns 8 nearest neighbors per model, `/api/similarity/random` picks a random starting image. Lazy lancedb connection shared across requests.

---

### 23:15 — Sidebar: Drift → Similarity

**Intent.** User still saw "Drift" in the sidebar navigation. The experiments section in `page_shell()` hadn't been renamed.

> Renamed the sidebar link from "Drift" to "Similarity" in `page_shell()`. The web gallery already had both La Similarité (semantic) and La Dérive (structural) as separate, correctly named experiences.

---

## 2026-02-07

### 00:50 — Master Orchestrator: mad_completions.py

The project had a recurring problem: analysis processes would hang, die silently, or never start. The user would wake up to find nothing completed. No more.

> Built `mad_completions.py` — a master orchestrator that checks all 20 pipeline stages against the database: infrastructure (rendering, EXIF, colors, hashes), models (11 CV models + Gemini + vectors), enhancement, AI variants, and GCS uploads. For any gap found, it identifies the correct fix script and starts it with proper `PYTHONUNBUFFERED=1` logging. Resource-aware: only one GPU-heavy process at a time, API processes run alongside. `--watch` mode loops until everything reaches 100%. After each cycle, regenerates the State dashboard so it always reflects reality. Previously, the Gemini engine had been silently stuck for 8 hours because it was started with `--limit` instead of `--test`. The orchestrator makes manual process babysitting obsolete.

---

### 00:55 — Signal Status: 14/20 Stages Complete

Running processes finally producing real output. Gemini analysis at 70% (6,294/9,011). OCR running at 47% (4,223/9,011). All other signals at 100%. Emotions was already done — the 19% was misleading because only 1,676 images have faces, and all 1,676 have emotions.

> Updated State dashboard with accurate numbers across the board. Signal Inventory table now shows BLIP Captions DONE (9,011), Facial Emotions DONE (1,676 images with faces), Gemini at 6,294, OCR at 4,223. Architecture section updated from "9 Python Scripts" to 10 with the new orchestrator. Next priorities: finish Gemini + OCR, then GCS upload pipeline.

---

### 02:00 — Expert Team: CSS Performance Overhaul

Applied the 6-expert system (FPS, Smooth Animator, Logic & Resilience, Tech Stack, Clean Code, QA) to the entire Show codebase, starting with the foundation: `style.css` and `app.js`.

> **CSS**: Removed `backdrop-filter: blur(12px)` from `.glass-tag` — this was the single worst performance killer, creating 100+ GPU blur passes on grid views. Replaced all 14 instances of `transition: all` with specific properties (`border-color, background, color, transform, opacity`). Added Apple HIG motion grammar (`--ease-out-expo`, `--ease-out-quart`, `--ease-spring`) and timing variables (`--duration-fast/normal/slow`). Added `content-visibility: hidden` for inactive views. Added `@media (prefers-reduced-motion: reduce)`. Added `will-change: transform` on animated elements.

> **app.js**: Added `fetchJSON()` with HTTP status validation. Timer management (`registerTimer()`, `clearAllTimers()`) called on every view switch to prevent interval/rAF leaks. Progressive lightbox loading (micro → display). `hashchange` listener for browser back/forward. Error boundaries with try/catch around experience init. Scroll-to-top on view switch. Extracted constants.

---

### 02:30 — Expert Team: Experience Module Fixes

Swept all 14 experience modules for the same issues.

> **game.js**: Replaced `setInterval(50ms)` (20fps!) with `requestAnimationFrame` for the timer bar — now silky smooth at 60fps. Uses `performance.now()` for precise timing. Added `answered` guard preventing double-click exploits. Progressive image loading for game photos.

> **bento.js**: Registered crossfade interval with `registerTimer()` so it gets cleaned up on view switch. Crossfade now uses `transitionend` event instead of blind `setTimeout(800)` — respects actual CSS transition timing and `prefers-reduced-motion`. Uses `loadProgressive()` for display-tier images.

> **grid.js**: Added debounced filter rendering (80ms) so rapid tag clicks don't trigger 5000-photo re-layout per click. Cached `gridLastVisible` array eliminates double-filtering for count display.

> **All modules**: Removed stale `*Initialized` flags from all 11 experience modules. These prevented re-initialization when navigating back to an experience, causing stale state. Now every experience rebuilds fresh on entry, and `clearAllTimers()` handles cleanup.

> **compass.js**: Replaced `shuffleArray([...all]).slice(0, 500)` (copies entire 9k array to sample 500) with stride-based sampling — zero allocations.

> **map.js**: Added retina canvas support (`devicePixelRatio`-aware sizing). Dots are now crisp on HiDPI displays.

> **typewriter.js**: Replaced inline setTimeout debounce with shared `debounce()` utility from app.js.

---

### 03:00 — Design Token Audit: Hardcoded Styles → CSS Variables

Scanned all 15 JS files for hardcoded styles that bypass the design system. Found 34 style assignments — 9 needed migration.

> Added 13 new CSS tokens: `--emo-happy/sad/angry/surprise/fear/disgust/neutral/contempt` (emotion colors), `--color-error` (error red), `--depth-near/mid/far` (depth layer visualization). Migrated `faces.js` from hardcoded `EMOTION_COLORS` map to `emoColor()` that reads from CSS variables. Replaced inline `style="color:#ef5350"` in app.js error states with `.loading.error` CSS class. Migrated darkroom depth bars from hardcoded `rgba()` to `var(--depth-*)`. Made map canvas read `--bg` and `--glass-border` from CSS tokens. The remaining 25 assignments are legitimate dynamic values (computed widths, animation states, layout calculations) that can't be static tokens.

---

### 03:30 — Apple System Colors: Full Design System Migration

Replaced every custom color in the Show web gallery with Apple's official system color palette. The app now has a single source of truth: 12 vibrant colors + 6 grays from Apple HIG, with automatic dark/light adaptation via `prefers-color-scheme`.

> **`:root`**: Replaced all 8 custom category colors (`--c-vibe`, `--c-grading`, etc.) with references to system colors (`var(--system-orange)`, `var(--system-blue)`, etc.). Same for 8 emotion colors. Added `@media (prefers-color-scheme: dark)` with Apple's dark-mode hue shifts — the blue in dark is NOT the blue in light. The depth layer colors now use Apple cyan/green/red. Even the `--bg-elevated` and `--text` values aligned to Apple's gray scale.

> **Glass tags**: All 8 category tag styles migrated from hardcoded `rgba()` to `color-mix(in srgb, var(--system-*) X%, transparent)`. This means when system colors shift between light/dark mode, every tag automatically adapts. No more maintaining parallel color values.

> **Badges, game buttons, observatory bars**: All hardcoded hex colors replaced with system color references. Only one hex remains in the entire CSS: `--bg: #0a0a0a` — the photography app's true black background, intentionally darker than Apple's deepest gray.

> **`colors.js`**: The `colorNameToHex()` function became `colorNameToCSS()` — it now reads Apple system colors from CSS variables at runtime. The gray bucket color reads `--system-gray`.

---

### 03:45 — State Dashboard: Sidebar Fix

Fixed the broken "Gemini Progress" link in the State dashboard sidebar — the `#sec-gemini` anchor didn't exist on the page. Added `id="sec-gemini"` to the Models section. Restructured the sidebar so dashboard sub-items (Models, Signals, Vector Store, Camera Fleet, Render Tiers, Storage, Pipeline Runs, Sample Output) are now nested under a collapsible "State" group instead of being in a separate "Dashboard" section. Added `.sb-sub` CSS class for indented sub-navigation.

---

## 2026-02-07

### 00:15 — Show: Light-First Design System Rewrite

Complete rewrite of `web/style.css` — flipped from dark-only to a light-first design system with proper `@media (prefers-color-scheme: dark)`. Photography-immersive experiences (Le Bento, La Chambre Noire, Le Flot, La Carte) keep forced-dark via CSS custom property overrides on their container elements. Everything else gets clean, bright Apple-style surfaces in light mode.

> **New token layer**: `--fill-primary/secondary/tertiary/quaternary` (Apple Fill Colors), `--shadow-sm/md/lg` (light vs dark shadow), `--header-bg` (frosted header), `--separator`, `--bg-tertiary`. Typography switched from monospace to system font as default. Radius bumped to 12px/8px. All surfaces, glass layers, and fills now respect both modes.

> **AI-alive animations**: Added `@keyframes ai-shimmer` (traveling gradient), `ai-gradient` (cycling color gradient), `fade-up` (entrance reveal), `ai-pulse` (subtle breathing). Header gets a traveling blue→purple→pink accent line via `#header::after`. Loading indicator changed from spinner text to a shimmer gradient bar. Launcher cards cascade in with staggered `animation-delay`. Every view transition gets a `fade-up` entrance. Lazy images fade in via CSS attribute selector (`img[data-src] { opacity: 0 }`).

---

### 00:30 — Hardcoded Style Purge: 14 JS Files Fixed

Audited all 15 JS experience modules for styles that bypass the CSS design system. Found 24 violations across 8 files — 14 high-priority, 8 medium, 2 low.

> **grid.js**: Replaced two inline flex/wrap/gap blocks with `.grid-overlay-tags` and `.filter-active-section` CSS classes.

> **colors.js**: Four fixes — grid inline styles → `.colors-grid` / `.colors-grid-bucket` classes, swatch 6-line inline styles → `.color-swatch-sm` class, empty state inline styles → `.empty-state` class.

> **pendulum.js**: Replaced `style.fontSize = '28px'` with `.pendulum-results-title` CSS class.

> **drift.js / similarity.js / observatory.js**: Replaced `style.cursor = 'pointer'` with shared `.clickable-img` CSS class.

---

### 00:40 — State App: AI-Alive Design Update

Applied the AI-native design language to the State dashboard (`generate_status_page.py`). The State app now has the same sense of intelligence as Show.

> **Sidebar AI accent**: Added a 2px animated gradient line (blue→purple→pink→orange) on the sidebar's right edge via `::after`, cycling with `ai-gradient` at 35% opacity. Both the main status CSS and the `page_shell()` shared layout get it.

> **Animations**: Added `@keyframes ai-shimmer`, `fade-up`, and `ai-gradient` to both CSS contexts. State hero gets `fade-up 0.6s`. Main content areas animate in with `fade-up 0.5s`. Element grid cards stagger their entrance (4 groups, 60ms increments).

> **Section title accent**: Every `.section-title` gets a 60px gradient underline (blue→purple) at 60% opacity via `::after` — a subtle visual signature.

> **Token migration**: Fixed 4 hardcoded camera tag icon colors (`#86868b`, `#a1a1a6`, `#6e6e73`, `#98989d`) → `var(--muted)` / `var(--fg-secondary)`. Fixed `METHOD_COLORS` in blind-test JS from hardcoded hex to runtime `getComputedStyle()` reads of `--muted`, `--apple-blue`, `--apple-green`. Fixed skipped-row color from `#86868B` → `var(--muted)`.

> Regenerated all 6 static HTML pages (state, journal, instructions, drift, blind-test, mosaics).

---

### 08:30 — Gemini Re-Analysis: 633 Images

Discovered 633 images still needed Gemini analysis: 7 entirely missing, 626 with stale "reauthentication needed" errors from an expired OAuth session. Re-authenticated with `gcloud auth application-default login` and launched `photography_engine.py`. The engine has built-in retry with exponential backoff, and immediately started processing despite hitting Vertex AI rate limits (429 RESOURCE_EXHAUSTED). Current state: 8,439 good analyses out of 9,011.

---

### 08:45 — Show: Full Verification Pass

All 14 Show experiences verified as implemented and functional. Re-exported gallery data: 9,011 photos, 8,401 Gemini analyses, 1,676 face detections, 200 game rounds, 8,618 stream sequence entries. Every experience module (La Grille, Le Bento, La Similarite, La Derive, Les Couleurs, Le Terrain de Jeu, La Chambre Noire, Le Flot, Les Visages, La Boussole, L'Observatoire, La Carte, La Machine a Ecrire, Le Pendule) has a real implementation with proper CSS design system integration. The 2,077-line style.css covers all experiences with Apple HIG tokens, dark mode, immersive views, and accessibility (reduced motion). Gallery served locally via `serve_gallery.py` on port 3000, with `/rendered/` proxy for local tier images.

---

### 11:00 — GCS Discovery: 135,518 Images Already Uploaded

Verified the GCS bucket `gs://myproject-public-assets/art/MADphotos/v/` — it's not empty at all. 72,113 original tier files (display/micro/mobile/thumb in jpeg+webp) and 63,100 enhanced tier files already uploaded. All publicly accessible via HTTPS. The DB's `gcs_uploads` table had 0 rows because these were uploaded outside of `gcs_sync.py` in a previous session.

---

### 11:15 — Show: Switched to GCS Public URLs

Updated `export_gallery_data.py` to emit GCS public URLs instead of local `/rendered/` paths. `photos.json` now contains full `https://storage.googleapis.com/...` URLs for all image tiers (thumb, micro, display, mobile) plus enhanced variants (e_thumb, e_display). This means Show can now work as a fully static site served from anywhere — no local proxy server needed. Re-exported all data: 9,011 photos with all 9,011 Gemini analyses (100%), 20.7 MB total. Gemini analysis completed during the session — from 8,401 to 9,011 successful analyses.

---

### 11:20 — State App: OS Dark Mode Auto-Detection + Content Update

All 7 State app pages (state, journal, instructions, drift, blind-test, mosaics, index) now auto-detect the OS color scheme preference via `window.matchMedia('(prefers-color-scheme: dark)')`. Previously dark mode only worked via manual toggle — if your Mac was in dark mode, the pages still showed light. Now they respect the system preference out of the box, with manual toggle still overriding via localStorage.

Also updated `render_instructions()` with current status: Gemini 100% (was 70%), OCR complete (was 47%), GCS has 135,518 files uploaded. Updated `docs/index.html` Show description to list all 14 experiences (was only 3). Regenerated all 6 HTML pages.

---

## 2026-02-07

### 14:00 — See: Union/Intersection Mode Toggles on All Gemini Dimensions

Extended the See (MADCurator) filter system from having Any/All mode only on Vibes to supporting it on every Gemini-analysis dimension: Grading, Style, Time, Setting, Weather, Scene, Emotion, Exposure, Depth, and Composition. Replaced the old single `vibeMode` property with a generalized `dimensionModes: [FilterDimension: QueryMode]` dictionary on FilterState. The Any/All toggle now appears on any dimension when 2+ values are selected. This makes multi-value filtering consistent across the entire sidebar.

### 14:05 — See: Weather, Scene, Emotion Filter Sections

Added three missing filter dimensions to the sidebar: Weather (from Gemini `weather` field), Scene (from Places365 `scene_1` classification), and Emotion (from facial emotion aggregation). Scene is a single-value match like Setting; Emotion is multi-value like Vibes, supporting union/intersection mode. Added `emotionList` computed property to PhotoItem for deduplication. All three dimensions have full faceted counting and chip group support.

### 14:10 — See: Inline Label Editing with DB Write-back

Made 9 Gemini analysis fields editable inline in the detail view: Grading, Exposure, Sharpness, Composition, Depth, Time, Setting, Weather, and Alt Text. Hovering over a value reveals a pencil icon; clicking it switches to an inline TextField. Enter saves to `gemini_analysis` table via a new whitelisted `updateGeminiField()` method (SQL injection safe — only allowed column names pass through). Escape cancels. After save, the full photo list reloads from DB and filters reapply, keeping the current photo selected.

### 14:15 — See: Vibe Add/Remove Editing

Vibes are now editable: hovering over a vibe pill shows an X button to remove it, and a "+" button at the end lets you type a new vibe. Both write back to the DB as a JSON array via `updateVibes()`. The sidebar facet counts refresh immediately after edits. Clean build confirmed — all 5 files modified (Models, Database, PhotoStore, FilterSidebar, DetailView), zero compilation errors.

### 14:30 — Code Audit: Scene Filter Bug Fixed

Full code inspection caught a bug: scene filter was only checking `scene1`, missing `scene2` and `scene3` matches. Fixed `matchesFilters()` to check all three scene classifications with union/intersection mode support. Added `facetScenes()` method that counts scene1/scene2/scene3 values. Also identified 8 pre-existing stale claims across project documents (emotion count off by 2, GCS table empty, variant types mismatch, script count 19 not 10, web file count off by 1).

### 14:45 — /sync-state: Custom Claude Code Agent

Created the first custom Claude Code skill at `.claude/skills/sync-state/`. Two files: `SKILL.md` (the reconciliation protocol — 5 phases: collect, compare, report, journal, regenerate) and `snapshot.py` (Python script that queries DB + filesystem and outputs JSON with all 50 reconcilable values). The snapshot covers: image/camera/signal/detection counts, AI variant types, table counts, Python script inventory, web experience list, Swift filter dimensions, editable field count. Designed to be run as `/sync-state` at the end of every session — compares snapshot actuals against MEMORY.md, generate_status_page.py, and docs/index.html, then patches all deltas.

### 11:30 — Repo Restructure: frontend/ + backend/

Major repository reorganization from "everything at root" to a clear `frontend/` + `backend/` layout. Executed in 6 phases:

**Phase 1-2: Frontend assets moved.** `web/` → `frontend/show/`, `docs/*.html` + `.nojekyll` + `hero-mosaic.jpg` → `frontend/state/`, `MADCurator/` → `frontend/see/`. Updated `firebase.json` (`public: "frontend/show"`), GitHub Pages deploy workflow (`path: frontend/state`), and `.gitignore`.

**Phase 3: Shell scripts.** `run_after_render.sh` → `scripts/after_render.sh`, `run_full_reprocess.sh` → `scripts/full_reprocess.sh`. Updated internal script paths to use `$PROJ/backend/` references.

**Phase 4: The big one — 19 Python scripts moved and renamed.** All scripts moved atomically to `backend/` with cleaner names: `mad_database.py` → `database.py`, `render_pipeline.py` → `render.py`, `photography_engine.py` → `gemini.py`, `imagen_engine.py` → `imagen.py`, `gcs_sync.py` → `upload.py`, `generate_status_page.py` → `dashboard.py`, `serve_gallery.py` → `serve_show.py`, etc. `database.py` now exports `PROJECT_ROOT = Path(__file__).resolve().parent.parent`, and all 12 scripts that import it use `db.PROJECT_ROOT` for path resolution. The 5 scripts with direct sqlite3 compute their own `PROJECT_ROOT`. Fixed the hardcoded absolute path in `vectors.py`. Updated all subprocess calls in `pipeline.py` and `completions.py` to use new script names.

**Phase 5: Verification.** All 5 tests pass: `completions.py --status` (imports + DB + lancedb), `dashboard.py` (generates 6 pages to `frontend/state/`), `export_gallery.py --pretty` (writes 27.7 MB to `frontend/show/data/`), `serve_show.py` (paths resolve correctly), Swift build (compiles successfully).

**Phase 6: Design tokens + docs.** Added spacing scale (4-64px), type scale (11-34px), and extended radius tokens to Show's `style.css`. Aligned State's CSS: renamed Apple colors to `--system-*` canonical names with legacy aliases, added `--text`, `--text-muted`, `--bg-elevated` semantic aliases alongside existing `--fg`/`--muted`/`--bg-secondary`. Updated MEMORY.md with new repo structure, README.md with directory tree and new script names, and dashboard.py instructions page.

Naming conventions: dropped `mad_` prefix, `_engine` suffix, `generate_` prefix, `_pipeline` suffix. Named after what it IS (gemini, imagen) or what it DOES (upload, enhance, render).

### 11:48 — Data Directory Consolidation: images/ + backend/models/

Moved all data assets from project root into organized subdirectories. `originals/`, `rendered/`, `ai_variants/`, `vectors.lance/` now live under `images/`. The SQLite database `mad_photos.db` (3.1 GB) also moved to `images/` — it's data about images. Model weights (`face_detection_yunet_2023mar.onnx`, `yolov8n.pt`, `.places365_resnet50.pth.tar`, `.places365_labels.txt`) moved to `backend/models/`. Processing state files (`.faces_processed.json`, `.objects_processed.json`) moved to `backend/`. Updated all 19 Python scripts, 2 shell scripts, 1 Swift source file, and `.gitignore`. Updated 97,898 `tiers.local_path` DB rows via `REPLACE()`. Updated the `/sync-state` skill (both `SKILL.md` and `snapshot.py`) to use new paths. The root is now clean: just `frontend/`, `backend/`, `scripts/`, `docs/`, `images/`, config files.

---

### 15:00 — See: Major Overhaul — Two Windows, Curation Toolbar, Performance

Complete overhaul of the native macOS curation app. Renamed MADCurator → See. 8 Swift files rewritten.

**Two-window architecture.** Split from a single HSplitView into two independent windows: Collection (sidebar + grid + toolbar) and Viewer (detail panel with hero image + metadata + curation controls). The Collection window uses `NavigationSplitView`, the Viewer opens automatically via `@Environment(\.openWindow)` when a photo is selected. Both windows share the same `PhotoStore` via `@EnvironmentObject`. This eliminated the jittering label layout caused by HSplitView resizing fights.

**Curation toolbar.** Replaced the macOS `.toolbar` (which spread items across the title bar with huge gaps) with a custom 36px `GridToolbar` view inside the content VStack. Contains: photo count, three curation filter pills (Picked/Rejected/Unflagged with colored icons, labels, and counts), a Reset button (only visible when filters active), sort picker dropdown, grid mode toggle (square/natural crop), and select mode toggle. All buttons have hover states via dedicated `CurationPill`, `HoverButton`, and `HoverIconButton` components.

**Sort system.** 8 sort options: Random (shuffle), Aesthetic (LAION score), Date, Exposure (Over/Balanced/Under rank), Saturation (palette HSB), Depth (complexity score), Brightness (palette HSB), Faces (count). Default is Random. Sort preference persists across sessions via UserDefaults.

**Select mode.** Enabled by default on launch. Clicking a photo in select mode toggles its selection (checkmark overlay, top-right). Clicking with select mode off opens the Viewer. Batch curate: select multiple photos, then pick or reject all at once. Select All button in toolbar.

**Keyboard shortcuts.** `p` pick (toggles kept↔pending), `r` reject (toggles rejected↔pending), `u` unflag (always sets pending), `e` toggle enhanced image, `i` toggle info panel, `←/→` navigate, `Escape` deselect/exit select mode, `y/n` accept/reject propagated locations. All shortcuts work in both Collection and Viewer windows.

**Performance.** Four optimizations: (1) `prepareCache()` pre-computes 12 expensive properties on PhotoItem at load time instead of JSON-parsing on every access. (2) `QuickCounts` struct pre-computed once for sidebar instead of filtering 9,000 photos per render. (3) Async thumbnail loading via `.task(id:)` with `Task.detached` for off-main-thread disk I/O and `NSCache` (2000 limit). (4) Curated photos disappear immediately from grid when they no longer match the active filter.

**Landing state.** App opens showing unflagged photos in random order. Preferences (sort, crop mode, info panel, curation filter) persist via UserDefaults and restore on next launch.

**App icon + lifecycle.** Pure black rounded-rectangle icon (1024px, radius 220px) generated via PIL, converted to .icns. Set at runtime via `NSApp.applicationIconImage` in AppDelegate. On quit: `savePreferences()` + `database.shutdown()` (WAL checkpoint + close). App terminates when last window closes.

---

### 16:30 — Show: New Experiences + Design System Redesign

Four new web experiences added to Show: **Les Confetti** (confetti.js), **Les Dominos** (domino.js), **NYU** (nyu.js), **Le Thème** (theme.js). All existing experiences redesigned with unified Apple HIG design system. Updated index.html with new navigation, style.css with comprehensive token system, app.js with unified launcher. Design system audit documentation generated (DESIGN_SYSTEM_AUDIT.md + design-system.html). Deployed to Firebase Hosting.

---

### 17:00 — Deploy

Committed all changes to GitHub (`b7b53f8`): 37 files, +6,866 / -3,702 lines. Deployed Show to Firebase Hosting at `https://madphotos-efbfb.web.app`. Updated journal, README, and regenerated State dashboard pages.

---

### 17:24 — Show: Launcher Redesign + Experience Polish

Simplified the Show launcher from verbose card-per-experience HTML to a streamlined layout. Removed inline card markup from `index.html` (134 lines cut), moved experience metadata into `app.js` for dynamic rendering. Header redesigned: split logo into `MAD` + `photos` spans for typographic styling, replaced tab nav with experience name display. Removed photo count from header.

Major experience refinements across 6 modules: `bento.js` (+224 lines — layout improvements), `confetti.js` (+447 lines — interaction overhaul), `faces.js` (+230 lines — emotion grid polish), `compass.js` (+75 lines — axis calibration), `grid.js` (+65 lines — filter/sort refinements). `style.css` consolidated from 810 lines of changes — removed redundant rules, tightened token usage. Created `/ship` deploy agent skill for automated journal + commit + push + Firebase deploy pipeline.

---

### 18:02 — Show: Adaptive UI Overhaul — Full Mobile/Touch Pass

Comprehensive mobile and touch audit of the entire Show web app, followed by fixes across 11 JS files and `style.css` (+564 lines changed).

**Touch/swipe support.** Added `touchstart`/`touchend` gesture handlers to 7 experiences: bento (swipe to cycle layouts), compass (swipe to shuffle), confetti (swipe to navigate vibes), game (vertical swipe to advance pairs), nyu deck+canvas (swipe to navigate), pendulum (swipe to choose side). Grid gets a two-tap mechanism — first tap reveals the overlay with tags, second tap opens lightbox. All touch listeners use `{passive: true}` to avoid scroll blocking.

**Hover guard.** Moved all 35+ `:hover` rules exclusively inside `@media (hover: hover) and (pointer: fine)` guard block. Original hover rules replaced with comment references. Prevents sticky-hover on touch devices.

**Viewport and safe areas.** Added `viewport-fit=cover` to meta tag. All 12 viewport-height containers now have `100dvh` fallback after `100vh` for iOS Safari URL bar. Body, header, and bottom bars (jeu-bar, nyu-nav) use `env(safe-area-inset-*)` for notched devices.

**Tap targets.** Every interactive element audited against 44x44px minimum. Fixed: theme-toggle, sort-size-btn, drift-breadcrumb-item, confetti-nav-btn, lightbox-close, bento-nav, nyu-nav-btn, confetti-bomb — all at 44px across all breakpoints including phone.

**Font floor.** Mobile `@media (max-width: 768px)` overrides small tokens: `--text-2xs`/`--text-xs`/`--text-caption` floored at 13px, `--text-sm` at 14px. Replaced 4 hardcoded `14px` font-size values with `var(--text-sm)` token.

**Responsive breakpoints.** 768px tablet: drift 2-col, bento full-width, compass stacked, confetti horizontal nav. 480px phone: drift 1-col, game vertical stack, compass single-column, faces horizontal-scroll filters, sort bar wrapped.

**Performance.** Added `contain: layout style paint` to `.nyu-mosaic-cell` and `.confetti-cell` for paint isolation during assembly animations. Replaced `.drift-score` `width` animation (layout property) with `transform: scaleX()` via CSS custom property (compositor-only). Fixed bento.js keydown listener leak (now removes before adding). Added `decoding='async'` to pendulum.js image preload.

**Accessibility.** `prefers-reduced-motion: reduce` covers all animations. `content-visibility: hidden` on inactive views. `-webkit-text-size-adjust: 100%` prevents iOS text inflation.

---

### 18:50 — Show: Lightbox Navigation, NYU Reel Arrows, Boom Glass Bomb, Faces Emoji Filters

Four feature passes across the Show app.

**Lightbox navigation.** The shared lightbox now supports prev/next navigation with arrow buttons, keyboard arrows, and touch swipe. `openLightbox(photo, photoList)` accepts an optional photo list for sequential browsing. NYU reel, grid, and overview all pass their photo arrays. Nav arrows auto-hide when at list boundaries or when opened without a list context. Capture-phase keydown ensures lightbox keys take priority over experience handlers.

**NYU reel overhaul.** Added glass nav arrows (prev/next) flanking the reel, a counter showing current position ("3 / 24"), keyboard arrow support in reel mode, and `scrollNyuReel()` with `scrollIntoView` for smooth programmatic navigation. `updateReelCounter()` tracks scroll position via `scrollend`/debounced `scroll` events. Nav arrows hidden on mobile where swipe is native.

**Boom glass bomb.** Moved the bomb button out of the left nav column into a `confetti-mosaic-wrap` container that wraps the mosaic grid. The bomb now sits on a 72px frosted glass disk (`backdrop-filter: blur(20px) saturate(1.4)`, semi-transparent `color-mix` background, `border: 1px solid var(--border)`, `box-shadow: var(--shadow-md)`) positioned at the bottom-left edge of the mosaic square with `transform: translateY(50%)` so it straddles the bottom edge.

**Faces emoji filters.** Replaced text labels (Happy, Sad, Angry, etc.) with emoji icons in the emotion filter bar. Face image cache now has a 200-entry LRU cap to prevent memory growth. Added batch queue cleanup on view switch.

**Header menu button.** Added a hamburger menu button to the header for direct sidebar access alongside the logo tap.

**State dashboard.** Signal inventory now renders all tags flat inline per group (no subcategory labels). Removed leaf categories: Color Cast, Temperature, Exposure, Depth Zones, Complexity, Aspect Ratio, Enhancement, Rotation.

**See app.** Added `ThumbnailLoader` actor with 8-slot concurrency limiter for cooperative thumbnail loading.

---

### 19:03 — Compass Edge-to-Edge, Faces Crop Fix, State React SPA Backend

**Compass redesign.** Removed all padding, border-radius, and gaps from the compass grid — images now bleed edge-to-edge across the full viewport. Center hero uses `object-fit: cover` instead of `contain` for a more immersive fill. Arm filter tightened from `style !== 'portrait'` to `aspect >= 1.2` for more reliably landscape-oriented photos. All breakpoints updated: phone layout goes single-column with `gap: 2px; padding: 0`.

**Faces quality filter.** Added confidence threshold (`conf >= 0.75`) and minimum area gate (`w * h >= 0.005`) to filter out low-quality and tiny face detections. Square crop logic hardened: size clamped to image dimensions, center position clamped so crop never extends past image bounds — fixes partial-face edge artifacts.

**State React SPA backend.** Dashboard API expanded with 5 endpoints: `/api/stats`, `/api/journal`, `/api/instructions`, `/api/mosaics`, `/api/cartoon`. `serve_show.py` now delegates all `/api/*` routes to dashboard.py functions, serves the Vite-built State SPA from `dist/` with client-side routing fallback, and handles `/api/similarity/:uuid` and `/api/drift/:uuid` vector search routes. State `index.html` replaced with React SPA entry point (Vite + TypeScript).

---

## 2026-02-07

### 19:43 — Show: Mobile UX Pass + Performance Audit & Fixes

Two passes: mobile interaction improvements, then a full performance audit with five fixes.

**Mobile UX.** Confetti bomb repositioned: desktop uses `position: absolute` anchored right of the mosaic wrapper, mobile switches to `position: fixed` bottom-center with safe-area inset. Sort bar moved from sticky-top to `position: fixed; bottom: 0` on mobile for thumb reach, with scrollable pill and visible text (`color: var(--text)` instead of dim). Bento dice button enlarged to 60px and centered at bottom on mobile (was 44px in corner). Couple game controls lifted from `space-4` to `space-6` off bottom edge.

**Performance audit.** Full 14-file audit identified 21 RED violations, 20 YELLOW risks, and 8 GREEN patterns. Five fixes implemented:

1. **Couleurs flex transition eliminated.** `.couleurs-band` was animating `flex` — triggers full layout of 24 siblings every frame. Replaced with `opacity`-only transition; flex changes snap instantly.

2. **will-change cleanup.** NYU mosaic (150 cells) and Confetti (64 cells) now reset `will-change: auto` after assembly completes, freeing ~30–50MB GPU memory. Confetti blow re-promotes layers before animating and cleans up after settle.

3. **box-shadow removed from transitions.** On `.drift-neighbor`, `.map-strip-card`, `.confetti-bomb`, `.confetti-nav-btn` — shadows now snap on hover instead of repainting every frame.

4. **Scripts deferred.** All 10 `<script>` tags in `index.html` now carry `defer`, unblocking HTML parsing while preserving execution order. Cache-busted to v=12.

5. **Tiered backdrop-filter.** Auto-detection in `app.js` sets `tier-a` (Safari, capable devices with ≥4 cores) or `tier-b` (Chrome Android, low-end). Tier-b replaces all `backdrop-filter: blur()` with solid semi-transparent backgrounds across header, menus, nav bars, overlays, and buttons. 13 elements covered in a single rule block at end of `style.css`.

---

### 20:59 — Show: Square + Caption experiences, Confetti radial nav, Bento diversity, Lightbox cleanup, Fullscreen toggle

Six feature areas in a single session, pushing from 9 to 11 Show experiences.

**New experience: Square.** Scrabble-board tile grid of square-cropped images (`square.js`, ~160 lines). 12 emoji-labeled category filters (Best, Rouge, Vert, Bleu, Mono, Serein, Intense, Doré, Animaux, Nature, Urbain, Nuit). Responsive tile count: 9 (phone), 16 (tablet), 25 (desktop). Each tile carries an aesthetic score badge. Shake button shuffles with a jiggle animation — CSS custom properties `--shake-x/y/r` per tile. Premium cells (corners + center) get a gold `color-mix` inset border. Assembly animation staggers tiles with `--sq-delay`.

**New experience: Caption.** Typographic tapestry (`caption.js`, ~170 lines). 200 photo captions flow as a dense justified text wall — each phrase is an inline `<span>` separated by thin interpuncts (`·`). Five size tiers from `text-xs` to `text-xl italic` based on aesthetic score. Variable opacity (0.3–1.0) creates depth. On hover, all siblings dim to 12% and a floating 180×130px preview image materializes above the cursor following mouse movement. Click opens lightbox. Touch: first tap highlights, second opens. Stagger-reveal on entry with 8ms delays.

**Confetti radial nav redesign.** Replaced the vertical left-column emoji nav (which overflowed iPad Pro 11" landscape) with a floating radial dial. Bomb sits at center of a 160px disk, emoji buttons orbit at 66px radius using `transform: rotate(N) translateX(R) rotate(-N)` to stay upright. Responsive: dial moves to bottom-center on mobile, shrinks to 140px/120px. Removed `.confetti-left`, `.confetti-nav`, `.confetti-nav-btn` — replaced with `.confetti-dial`, `.confetti-dial-btn`.

**Bento diversity fix.** `_fillBento()` pool expanded from top 300 to top 800 by aesthetic. Search window widened from 80 to 200 candidates. Selection now alternates between chromatic harmony (even picks) and vibe/scene diversity (odd picks) — bonus for scenes and vibes not yet represented. Result: each bento shows images from more varied contexts.

**Lightbox cleanup.** `.lightbox-meta` set to `display: none` — no caption, tags, or palette. Image max-height increased to 90vh (85dvh on mobile). One CSS rule, fully reversible.

**Fullscreen toggle.** Button added to header between logo and theme toggle — expand/collapse SVG icons toggle via `:root.is-fullscreen`. Uses Fullscreen API with webkit fallback. Hidden on iOS Safari where the API isn't supported. PWA meta tags (`apple-mobile-web-app-capable`, `black-translucent` status bar) enable standalone mode from home screen.

**Fixes.** Sort By color sort now uses precomputed `photo.hue` (from most-saturated palette color) instead of `hexToHue(palette[0])` which returned -1 for achromatic images. Sort bar text contrast improved: unselected buttons use `color: var(--text); opacity: 0.55` instead of `color: var(--text-dim)` for better readability on glass. About link corrected to `https://laeh.github.io/MADphotos/`. Export pipeline: `squarable: true` added to photo objects.

9 files changed (7 modified, 2 new). +503 / -112 lines.

---

### 22:03 — Cleanup: OCR completion, model status fix, pipeline hygiene, old HTML removal

Five housekeeping items that close out the signal pipeline and clean up migration debt.

**Facial Emotions model status fix.** The dashboard divided emotion count (1,676) by total images (9,011), showing 18.6% — but facial emotions only applies to images containing faces. Added per-model `of?: number` denominator to `DashboardPage.tsx`. Facial Emotions now uses `face_images_with` as its denominator, correctly showing 100%. Backend `dashboard.py` `models_complete` calculation updated to match: list of `(count, denominator)` pairs instead of simple count vs total.

**OCR sentinel bug fix.** EasyOCR phase in `signals_advanced.py` had a gap: images where all detected text regions scored below the 0.3 confidence threshold entered `if results:` but inserted nothing — no rows, no sentinel. These 1,205 images were silently skipped on every re-run. Fixed by tracking `inserted` count and inserting the sentinel row `(uuid, '', 0)` when `inserted == 0`. Ran full OCR on the remaining images (1,205 at 0.4/s, ~46 minutes). All 17/17 models now at 100%.

**Detection signal group.** Added a new "Detection" section to the State dashboard showing face count (1,676 images, 3,187 faces total), OCR text regions (10,818 across 9,011 images), object detections, and emotion analysis count.

**Pipeline runs cleanup.** Marked 29 orphaned "started" pipeline runs (0 processed, 0 failed) as "failed" in the DB. Updated `dashboard.py` query to filter out runs with `images_processed = 0 AND images_failed = 0`.

**Old HTML removal.** Deleted 7 pre-React static HTML pages (`state.html`, `journal.html`, `instructions.html`, `mosaics.html`, `cartoon.html`, `drift.html`, `blind-test.html`) plus `index.old.html` — all replaced by the React + Vite + Tailwind SPA. Updated `/ship` skill instructions to reference static data regeneration and Vite build steps.

---

## 2026-02-08

### 09:22 — Show: Cinema + Reveal + Pulse experiences, See async loading + zoom, State stats page

Three new Show experiences push from 10 to 13, each with rich themed sets and smart diversity sampling.

**New experience: Cinema.** Full-screen Ken Burns slideshow (`cinema.js`, ~310 lines). Two alternating layers crossfade with 1.5s opacity transitions. Six Ken Burns drift keyframes (`kb-1` through `kb-6`) randomly assigned per slide — slow zoom+pan over 8 seconds. 11 themed chapters (Golden Hour, Serene, Intense, Night, Portraits, Nature, Urban, Nostalgic, Ethereal, Dark, Vibrant) with chapter title cards that fade in center-screen for 2.5 seconds. Each chapter holds up to 12 diversity-sampled photos: filter by theme predicate, sort by aesthetic, take top N×3, shuffle, slice N. Auto-advances every 7 seconds with a thin progress bar. Space toggles pause (with flash indicator), arrows and click/swipe navigate. Timer registered via `registerTimer()` for cleanup.

**New experience: Reveal.** Clip-path morphing image transitions (`reveal.js`, ~329 lines), inspired by MADvids' Shape Reveal experiment. Seven geometric shapes, each paired with a themed image set: Circle→Serene, Diamond→Intense, Inset→Golden Hour, Star→Night, Split→Nostalgic, Hexagon→Nature, Blob→Ethereal. Each set holds ~14 photos. Incoming layer sits at z-index 2 with clip-path animated via `requestAnimationFrame` from 0→1 using easeOutCubic (`1 - (1-t)³`). Shape functions build CSS `clip-path` strings each frame — `circle()`, `polygon()`, `inset()`. The Blob shape adds organic wobble via `Math.sin(a*3 + now*0.004)`. Set label shows "Shape · Theme" with a 2.5s flash animation on set transitions.

**New experience: Pulse.** Breathing mosaic grid (`pulse.js`, ~226 lines). Responsive square grid: 10×10 desktop, 8×8 tablet, 6×6 phone. Each cell's `transform: scale()` and `opacity` modulated by a sine wave emanating from cursor position — `Math.sin(dist * 1.0 - now * 0.0018)`. Scale range 0.84–1.0, opacity 0.4–1.0. Wave origin follows mouse/touch, returns to center on leave. 12 category pills with French labels (Best, Rouge, Ambre, Vert, Azur, Violet, Doré, Nuit, Serein, Intense, Sombre, Nostalgique). Stagger-reveal from center outward with `--pulse-delay`, then `style.transition = 'none'` for rAF takeover. `pulseRunning` flag + `APP.currentView` check self-terminate the loop on view switch.

**CSS additions.** ~370 lines added to `style.css`. Cinema: shell, layers, 6 `@keyframes`, chapter overlay, progress bar, counter, pause flash. Reveal: two-layer z-index stack, `will-change: clip-path`, label flash animation, hint fade. Pulse: CSS grid with `--pulse-cols`, cell will-change, rack with pill buttons. Hover guards, dvh fallbacks, responsive overrides at 768px and 480px, reduced motion for all three.

**See: async loading + prefetch.** `PhotoStore.load()` moved to `Task.detached` with `MainActor.run` callback — the UI now shows a loading spinner instead of freezing on launch. Adjacent photo prefetch (`prefetchAdjacent()`) called on every `selectPhoto()`, `moveToNext()`, `moveToPrevious()`. New `ZoomableImageView.swift` (201 lines) adds pinch-to-zoom to the detail viewer. Crossfade transition (`.opacity`) on photo change with 0.2s easeInOut. Display cache added (limit 20) alongside existing thumb cache (limit 2000). `fullImagePath(for:)` accessor for full-resolution tier.

**State: Stats page.** New `StatsPage.tsx` (470 lines) — an infographic-style signal inventory page. Aesthetic histogram from `dashboard.py` (new `aesthetic_histogram` endpoint using `ROUND(score, 1)` bucketing). Fixed aesthetic query from `overall_score` to `score` column. Route `/stats` added to `App.tsx`, sidebar nav link added.

16 files changed (11 modified, 5 new). +755 / -27 lines.

---

### 10:15 — Drift experience, PWA, State data pipeline, auto-regeneration, See pinch-zoom grid

Four infrastructure improvements and a new Show experience — the first to use vector embeddings directly.

**New experience: Drift.** Visual similarity explorer (`drift.js`, ~254 lines rewritten to ~374). Pre-computed 8 nearest neighbors for all 9,011 images using combined DINOv2 (weight 0.6) + CLIP (weight 0.4) cosine similarity — chunked matrix multiply across L2-normalized vectors, computed in 3.8 seconds, stored as `drift_neighbors.json` (4.8 MB). The experience shows a center hero image surrounded by 8 neighbor cards with similarity percentages. Click any neighbor to drift to it; the hero crossfades while cards stagger-animate in with 60ms delays. Breadcrumb trail tracks the last 12 hops — click any dot to warp back. Keyboard: 1–8 select neighbors, Backspace goes back. Random button picks from the full collection. Starts with a random top-200 aesthetic image.

**PWA support.** Added `manifest.json` (standalone display, dark theme), `sw.js` (service worker with three-tier caching: cache-first for static assets, network-first for data files, cache-first with LRU eviction at 500 entries for GCS images), and generated 192px + 512px app icons. Index.html updated with manifest link, apple-touch-icon, theme-color meta, and SW registration script.

**State data pipeline.** Populated all 5 empty State dashboard JSON files by calling `dashboard.py` functions directly: `journal.json` (220K chars), `instructions.json` (18K), `mosaics.json` (14 entries), `cartoon.json` (74 pairs), `blind_test.json` (0 pairs — no enhanced tiers rendered yet). Stats.json regenerated with latest model completion data.

**Auto-regeneration.** Added `regenerate_exports()` to `completions.py` — when all 20 pipeline stages complete, it runs `export_gallery.py` then regenerates all 5 State data JSON files. Keeps Show and State in sync with the database automatically.

**See: pinch-to-zoom grid.** `ImageGrid.swift` converted from fixed column sizing to dynamic `@State thumbSize` driven by `MagnifyGesture()`. Pinch on trackpad smoothly resizes thumbnails between 60px and 400px. Grid recalculates columns via computed `[GridItem(.adaptive)]`.

**README.** Updated to 14 experiences, added PWA mention, corrected State description.

10 files changed (modified), 4 new files. +551 / -162 lines.

---

### 13:00 — Signals V2: 10 new CV models, 9 new DB tables, 155K+ new signal rows

The biggest signal extraction session yet. Goal: fix broken data, replace useless models, upgrade weak ones, and add every valuable local CV signal we've been missing.

**Data fixes.** Fixed 4,654 blob-corrupted `exposure_quality` values in `quality_scores` (numpy float32 bytes → proper REAL via `struct.unpack`). Populated `image_locations` from existing EXIF GPS data (1,820 rows).

**New table: `aesthetic_scores_v2`** — Replaced the useless NIMA aesthetic scores (avg 9.9/10, zero discrimination) with a three-model ensemble: TOPIQ-NR (perceptual quality), MUSIQ-AVA (learned aesthetics), and LAION CLIP aesthetic predictor. Composite score: mean 36.8, range 16.7–48.3, real spread. 9,011 images scored.

**New table: `face_identities`** — InsightFace ArcFace embeddings (512d) extracted for 2,264 faces across 1,676 images. DBSCAN clustering (eps=0.6, cosine metric) identified 84 distinct identity clusters. Enables "show me all photos of person X" queries.

**New table: `segmentation_masks`** — SAM 2.1 (hiera-tiny) automatic mask generation on MPS. Segment count, largest segment percentage, figure-ground ratio, edge complexity, mean segment area, top-10 segments as JSON. 9,011 images processed. Required float64→float32 casting for MPS compatibility.

**New table: `open_detections`** — Grounding DINO (tiny, 172M) open-vocabulary object detection with a curated 20-category prompt (person, car, bicycle, sign, graffiti, shadow, reflection, silhouette, umbrella, building, staircase, fire escape, mural, neon, tree, bridge, fence, window, door, lamp). 108,861 detections across 8,981 images. Far richer than YOLOv8n's closed vocabulary.

**New table: `foreground_masks`** — rembg (u2net, ONNX CPU) foreground isolation. Foreground/background percentages, edge sharpness, centroid position, bounding box. Required standalone script (`_rembg_standalone.py`) to avoid PyTorch MPS float64 incompatibility. 9,011 images.

**New table: `image_tags`** — CLIP zero-shot classification against 80 curated labels. Pipe-separated tags with confidence scores. 9,011 images tagged.

**New table: `pose_detections`** — YOLOv8n-pose for images containing people. 17 COCO keypoints per person with confidence scores and bounding boxes. 3,595 pose detections.

**New table: `saliency_maps`** — OpenCV spectral residual saliency. Peak attention coordinates, spread (entropy), center bias, rule-of-thirds grid (3×3), quadrant distribution. 9,011 images, computed in seconds.

**Upgraded: `depth_estimation`** — Depth Anything v2 Small → Large (ViT-L, 335M params). All 9,011 images reprocessed with the larger model for better accuracy. Same schema, better quality.

**In progress: `florence_captions`** — Florence-2-base generating three-tier captions (short, detailed, more detailed) per image. 1,068/9,276 complete at 0.4 img/s on MPS. Running in background.

**MPS compatibility fixes.** PyTorch 2.8.0 on Apple Silicon cannot handle float64 tensors on MPS. Three separate workarounds: (1) SAM — cast float64 inputs to float32 before MPS transfer, keep size tensors on CPU; (2) rembg — standalone script in clean Python process avoids torch MPS initialization; (3) Florence-2 — `num_beams=1, use_cache=False` to work around transformers 4.57+ `prepare_inputs_for_generation` breakage.

**State dashboard.** Updated `DashboardPage.tsx` to display v2 signals — 7 new model cards (models 18–24) with blue V2 badges, V2 Signals section showing all new tables with row counts, tag clouds for image_tags, open_detections labels, and aesthetic_v2 score distribution.

**Backend integration.** Added 9 new CREATE TABLE statements to `database.py`. Updated `pipeline.py` SIGNAL_TABLES for `--check` coverage. Updated `completions.py` for status reporting. Updated `dashboard.py` `get_stats()` with v2 signal queries.

| Signal | Images | Rows | Method |
|--------|--------|------|--------|
| aesthetic_scores_v2 | 9,011 | 9,011 | TOPIQ + MUSIQ + LAION |
| depth_estimation (Large) | 9,011 | 9,011 | Depth Anything v2 Large |
| face_identities | 1,676 | 2,264 | InsightFace ArcFace + DBSCAN |
| segmentation_masks | 9,011 | 9,011 | SAM 2.1 hiera-tiny |
| open_detections | 8,981 | 108,861 | Grounding DINO tiny |
| foreground_masks | 9,011 | 9,011 | rembg u2net |
| image_tags | 9,011 | 9,011 | CLIP zero-shot |
| pose_detections | — | 3,595 | YOLOv8n-pose |
| saliency_maps | 9,011 | 9,011 | OpenCV spectral residual |
| image_locations | 1,820 | 1,820 | EXIF GPS extraction |
| florence_captions | 1,068 | 1,068 | Florence-2-base (running) |
| **Total new** | — | **~165K** | — |

17 files modified, 6 new files. +1,353 / -158 lines (tracked). ~2,500 lines new scripts (untracked).

## 2026-02-09

### 11:21 — Stats Infographic Page + Analysis Pages Fix + Layout Fixes

**New: `/stats` infographic page.** Built a full Stats page for State dashboard with 13 pure-CSS chart sections — no chart library, all CSS bars/histograms/swatches. Visualizations: aesthetic score histogram (log-scale to handle 7,046 images at 10.0), camera fleet horizontal bars, top styles, scenes, vibes, emotions, time of day (segmented bar), depth complexity, grading, exposure, composition, objects in frame, and dominant color palette (swatches sized by count). Hero stat row at top, two-column layout for smaller charts, scroll-reveal animation via IntersectionObserver, percentage labels on all bars. Added route in `App.tsx` and nav item in `Sidebar.tsx`.

**Fixed: 3 analysis API endpoints.** Signal Inspector, Embedding Audit, and Collection Coverage pages (built by another agent) were failing because `generate_signal_inspector_data()`, `generate_embedding_audit_data()`, and `generate_collection_coverage_data()` in `dashboard.py` referenced nonexistent DB columns. Fixed 7 column name mismatches: `caption`→`alt_text`, `scene`→`scene_1` (from `scene_classification`), `hex_color`→`hex`, `pct`→`percentage`, `blip_caption`→`caption`. All three endpoints now return valid JSON.

**Fixed: sidebar scrolling on iPad.** Sidebar was scrolling with the page on tablets. Root cause: `.app-layout` used `min-height: 100vh` which let the flex container grow. Fixed by wrapping main content in `.main-scroll` div with independent `overflow-y: auto`, constraining `.app-layout` to `height: 100dvh; overflow: hidden`. Mobile breakpoint reverts to natural scrolling.

**Backend fix: aesthetic scores.** Fixed column name `overall_score`→`score` in `get_stats()` which was returning 0 for aesthetic average. Added `aesthetic_histogram` query for the Stats page distribution chart.

Files modified: `backend/dashboard.py`, `frontend/state/src/pages/StatsPage.tsx` (new), `frontend/state/src/index.css`, `frontend/state/src/App.tsx`, `frontend/state/src/components/layout/Sidebar.tsx`, `frontend/state/src/components/layout/Layout.tsx`.

### 11:48 — Signal Inspector: Full Signal Coverage + Model Attribution *("For all the labels you should have a mini pill that says the model they come from")*

The Signal Inspector page was only showing ~12 of the 30+ signal tables in the DB, and had no indication of which AI model produced each signal. This was the wake-up call that pages need to stay in sync with the actual database schema — especially when new signals are added by other agents.

**Backend overhaul (`dashboard.py`).** `generate_signal_inspector_data()` now queries ALL signal tables for each of the 300 sampled images. Added 14 new queries: `aesthetic_scores_v2` (TOPIQ+MUSIQ+LAION composite), `quality_scores` (technical+CLIP combined), `florence_captions` (Florence-2 short/detailed), `image_tags` (CLIP zero-shot, pipe-delimited not JSON — that was a bug), `open_detections` (Grounding DINO, 108K rows), `face_identities` (ArcFace identity labels), `foreground_masks` (u2net foreground/background percentages), `segmentation_masks` (SAM 2.1 segment count), `pose_detections` (YOLOv8-pose), `saliency_maps` (OpenCV spectral residual peak/spread), `image_locations` (EXIF GPS with location names), `image_hashes` (blur/sharpness/entropy), `image_analysis` (brightness/dynamic range/noise/color temp), `border_crops` (OpenCV edge detection).

**Frontend overhaul (`SignalInspectorPage.tsx`).** Every signal chip now shows a model attribution pill — a small semi-transparent badge inside the chip showing the source model (e.g., `kitchen` `Places365`, `neon` `CLIP`, `2 faces` `RetinaFace`). The Chip component was redesigned from `Chip({ label, type })` to `Chip({ label, model, color })`. The detail modal now shows 4 sections (Identity, Content, Perception, Technical) with model attribution on every row. Cards in the grid show 13+ signal types instead of 7.

**System instructions updated.** Added "Critical Rules" section to MEMORY.md: (1) ALWAYS check actual DB schema before writing SQL — run `PRAGMA table_info()` to verify column names exist, (2) ALWAYS check all signal tables when building signal pages, (3) ALWAYS attribute the model source on displayed signals, (4) `image_tags.tags` is pipe-delimited not JSON. Updated the Signal Pipeline table from 14 to 30+ entries with row counts and key columns. Updated the `/ship` skill with Signal Inspector review checklist.

The lesson: when one agent adds new signals to the DB, ALL downstream consumers (dashboard pages, export scripts, See app filters) need to be updated. This was codified as a rule so it won't happen again.

### 12:00 — New See app to let user flag good-looking images when square cropped

**Intent.** Evaluate all 9,011 images for how they look when square-cropped. The `square_crop` flag determines which images can be used in square layouts across Show experiences (grids, bento, social cards). Rather than adding complexity to the full See app, build a dedicated, minimal app optimized for one task.

> Built See Square (`frontend/see-square/`), a standalone macOS SwiftUI app (SPM, macOS 14+, sqlite3). Single-purpose UI: random grid of square-cropped thumbnails, multi-select, batch flag. New `square_crop` column on `images` table (NULL=pending, 1=good, 0=bad) with auto-migration. Lean DB layer with 3 JOINs (vs 11 in full See). Filter pills (Good/Pending/Bad), sort by Random/Quality/Camera/Date, pinch-to-zoom grid (3–10 columns). Keyboard shortcuts: P=good, R=bad, U=clear, Cmd+A=select all, Esc=deselect. ThumbnailLoader actor with 8-slot concurrency, NSCache (2000 items). 4 Swift files, zero dependencies.

---

### 13:36 — Parallel Florence workers, deploy pipeline fixes, live progress tracker *("Can't you have several process for florence")*

Florence-2 was captioning at 0.4 img/s on a single MPS process — 5+ hours for 9,011 images. The user asked why CPU wasn't busy.

**Parallel Florence-2 workers.** Created `_florence_worker.py`, a standalone Florence-2 captioning script that takes `--worker N --total-workers M` to partition pending UUIDs by modulo. Each worker loads its own model and processes independently. First attempt: 3 MPS workers — MPS contention dropped each to 0.22/s (worse than 1×0.4). Second: 2 MPS + 4 CPU — DB lock contention stalled most workers because each was writing per-image. Fix: batched writes with `executemany()` — accumulate 50 results in memory, flush in one short transaction. Final config: 2 MPS workers (0.29/s each) + 4 CPU workers (0.05/s each) = 0.79/s combined. CPU utilization went from 65% of one core to 908% across 16 cores. Florence-2 is heavily GPU-oriented — CPU inference is 6× slower, but free throughput when GPU is saturated.

**Deploy pipeline (`/ship` skill) updates.** Five gaps found from the live deploy: (1) Firebase config lives at project root, not `frontend/show/` — `firebase deploy` must run from root; (2) `photos.json` regeneration via `export_gallery.py` was missing from the skill; (3) GitHub Pages needs explicit `npx gh-pages -d dist`, not just push-and-pray; (4) GCS metadata sync via `upload.py --version metadata` added as optional step; (5) hardcoded "17 models" references updated to dynamic.

**V2 signals in photos.json.** Updated `export_gallery.py` with 10 new loaders: `load_aesthetic_v2()`, `load_tags()`, `load_saliency()`, `load_foreground()`, `load_open_detections()`, `load_poses()`, `load_segments()`, `load_florence()`, `load_identities()`, `load_locations()`. Each uses compact keys (e.g., `fg` for foreground_pct, `px`/`py` for saliency peak). Photos.json regenerated: 25.4 MB with all V2 signals. Coverage: aesthetic_v2 9,011, tags 7,080, saliency 9,011, foreground 9,011, open_labels 8,981, segments 9,011, florence 3,800+ (in progress), identities 700, location 1,820.

**Live progress tracker.** Created `_progress.sh` — a terminal dashboard that monitors all running signal extraction processes. Uses `tput home` for flicker-free updates (overwrites in place instead of clearing). Shows: overall Florence progress bar, per-worker bars with `[MPS]`/`[CPU]` labels, rate, ETA, CPU%. Auto-detects florence_worker, signals_v2, vectors_v2, and rembg processes. Opens in a new Terminal window via `open -a Terminal`.

The lesson: SQLite + multiple writers = pain. WAL mode helps readers but only one writer can hold the lock. Batching writes (accumulate in memory, flush with `executemany` every N images) is the pattern for multi-process pipelines.
