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
