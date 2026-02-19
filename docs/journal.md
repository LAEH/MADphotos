# Journal de Bord — MADphotos

> 9,011 photographs. 24 AI models. 6 interactive experiences. One database.

---

## 2026-02-19

**Srcset / multi-resolution images.** All photo `<img>` elements now get `srcset` with 3 resolution tiers (thumb 480w, mobile 1280w, display 2048w) and `sizes` hints tuned per view context. Browser picks the optimal resolution based on viewport + DPR instead of relying solely on JS `optimalTier()` heuristic. Variant photos (single URL) gracefully skip srcset. Progressive blur-up loading preserved — srcset applied after the swap so micro placeholder phase is unaffected.

**"MUCH better Bento sets."** Complete rewrite of the Bento curation engine. The old curators picked random photos with basic hue matching. New system uses visual intelligence:

- **Smart cell assignment**: Large cells (2×2) get high-impact photos (faces, high contrast, focused saliency). Small cells get atmospheric textures. `fillCells()` now sorts cells by size and assigns best-scored photos to largest cells first.
- **8 curators** (up from 5): Hero Story (hero + thematic court), Temperature Harmony (all warm or all cool), Depth Journey (shallow/deep contrast), Mono Accent (B&W + vivid color pop), Archetype Exhibition (composition archetypes), plus improved Color Story, Mood Board, Scene Story.
- **`visualImpact()` scoring**: aesthetic + face_count + contrast + saliency focus + depth_complexity + gc_weight. Every photo gets ranked for "who deserves the big cell."
- **Gemma composition signals** wired through entire data pipeline: visual_weight, energy_direction, archetype, color_temp now available on 342 photos. Used by curators for archetype grouping and impact scoring.
- **Generate count picker**: 10/20/40/80 selector replaces fixed count-20 button. Server accepts dynamic count via POST body.

**60fps performance overhaul.** Tokenized all animations, fixed every RED flag from comprehensive audit:

- **Compositor-only animations**: Converted float-drift keyframes from `top`/`left`/`right` → `transform: translate()`. Progress bars from `width` → `transform: scaleX()`. All hover effects from `background`/`color`/`filter` → `opacity`/`transform`.
- **Motion tokens**: `--duration-fast`, `--duration-normal`, `--duration-reveal`, `--img-appear-*` ensure identical image loading across all views.
- **3-tier performance**: tier-a (full fidelity), tier-b (no backdrop-filter), tier-c (no transitions). Refined detection: slow network → tier-c, old WebKit needs cores≥4 OR mem≥4 for tier-a.
- **CSS containment**: Added `contain: layout style paint` to heavy containers (bento-tile, scroll-row, all-wrap, jeu-card).
- **`content-visibility: auto`** on ScrollView rows — skips rendering off-screen rows.
- **CLS prevention**: `width`/`height` attributes + `aspect-ratio` on ProgressiveImg.
- **Cursor rAF epsilon exit**: Stops animation frame loop when delta < 0.5px.
- **Border crop fix**: `clip-path: inset()` instead of `transform: scale()` — no more conflict with CSS animations.

**"Generated images are getting better!"** Full overhaul of the style transfer pipeline. 536 images reviewed, 36.2% overall acceptance rate, up from 0-4% on initial styles. Key changes:

- **15 curated styles** with Apple Developer color palette (Red, Orange, Green, Mint, Teal, Cyan, Blue, Indigo, Purple, Pink). Each style gets specific Apple color assignments that match its mood.
- **Replaced failing styles**: ghibli (0%) → linocut, moebius (0%) → woodcut, pixar (10%) → scraperboard. Top performers: sumi-e 80%, bold ink 71%, gonzo 47%, batman 44%.
- **Post-processing pipeline**: border detection + Lanczos resize to match source dimensions exactly. Aggressive border trimmer compares edge strips vs center content.
- **Batch generation mode**: progress spinner in UI, polls `/api/generated/progress` every 3s, reveals all new pairs at once when batch completes.
- **Renamed** style-transfer → "Generated" everywhere (route, sidebar, API endpoints). Removed blind-test.
- **Moved** `genimages/` module into `backend/genimages/`.
- **New signals**: Launched Gemma composition signal extraction (visual_weight, energy_direction, archetype, ideal_ratio, color_temp) for better Bento grid layout.

**"The style transfer review page needs to be minimalist."** Stripped everything down to essentials: two images side-by-side at the original's exact aspect ratio, aligned to top. A=accept, R=reject. Emoji cursors (reject=bored, accept=heart-eyes). Single row of chip buttons. Session-based export tracking.

**"The Status page is stupid. Order it by mission."** Reorganized from data-dump to narrative: Overview → Experiences (what each Show view does and which models power it) → Intelligence (24 models grid) → Curation (picks + votes) → Infrastructure. Cut from 831 to 280 lines.

**"Instructions page is outdated."** Refreshed stats, sharpened wording, added variant pipeline section.

**"I need to create new locations in the tagger."** Added text input + button to create custom locations on the fly.

**"Remove the cartoon page."** Removed CartoonPage route and sidebar link.

---

## 2026-02-18

**"I want to review unpicked images and add them to picks."** Built new Unpicked review page in System with image browser and pick/skip controls.

**"I need to tag photos with locations."** Built Location Tagger page — shows each untagged pick with location buttons (NYC, Paris, China, Unknown). Keyboard shortcuts 1-9 for locations, S to skip. Writes to `image_locations` table.

**"The style transfer needs better prompts — match the style to the image."** Diversified style transfer from generic prompts to image-specific ones. Added Archer and Corto Maltese styles. Each image gets 5 diverse styles with image-specific color palettes and wider strength range.

**"Organize the System sidebar better."** Created Signals section (All, Gemma, Mosaics) and Curation section (Unpicked, Location, Generated). Added Signal Inspector page with per-image signal display and model attribution. Cleaned up stale files.

Redesigned bento tile ratios for better visual balance.

---

## 2026-02-17

**"The Colors view needs to respect image ratios."** Redesigned ColorsView as a ratio-aware bento grid — photos grouped by hue with natural aspect ratios preserved instead of forced squares.

**"Add a clean fullscreen preview."** Added fullscreen image preview to ColorsView matching Boom's immersive style. Fixed Couple lightbox navigation.

---

## 2026-02-16

**"Migrate everything to React."** The entire Show app — 14 vanilla JS experience files and a 6,280-line `style.css` — replaced with React 18 + TypeScript + Vite 6 + Tailwind v4 + Zustand. 6 focused views built from scratch (Colors, Bento, Couple, Boom, Caption, ISIT). Component architecture with Shell, FloatingNav, SideMenu, Lightbox, ProgressiveImg. Performance tier system (a/b/c). Service worker with 3-tier image cache. PWA support.

Added full AI/ML pipeline documentation to CLAUDE.md. Built neural style transfer script (VGG19 + PyTorch) with 5 curated art references.

---

## 2026-02-13

**"Use Gemma's per-image cartoon style suggestions instead of one generic prompt."** Built `gemma_cartoon` variant type that reads each photo's Gemma 3 analysis for style recommendations (Ghibli, Watercolor, Pixar, etc.) and tailors the Imagen 3 prompt accordingly. 2,250 picks ready at ~$0.04/image.

**"Rename Confetti to Boom."** Full codebase rename. Simplified UI: removed radial emoji nav with 14 orbiting buttons, replaced with single bomb button. ISIT-style 3-row grid layout.

---

## 2026-02-11

**"All Show experiences should display only the curated picks."** Filtered all views to show only the ~1,246 curated picks. Full 9K collection stashed for Tinder curation.

**"Can you remove the white or black frame in analog?"** Detected 90 film scan borders across 1,126 analog photos. Applied CSS `transform: scale()` + `clip-path: inset()` — zero re-rendering, pure CSS crop.

**"You should not crop portrait images to landscape."** Fixed Couple game: portrait pairs now display at native `2/3` ratio side by side.

**"Deduplicate votes across devices."** Built `voted.json` unifying iPad + Mac tinder votes so the same photo isn't shown twice on different devices.

**"Rename State to System with cleaner hierarchy."** Renamed `/state/` → `/system/`. New route structure: status, journal, instructions, experiments/, db/. StatusPage replaced DashboardPage with 3-section layout (Ingestion, Verified, Predicted).

**"Fix the image performance."** Fixed critical SW bug where GCS images bypassed the cache entirely. Built 3-tier cache (micro/thumb/image), blur-up placeholder loading, DPR-aware tier selection, browser-specific decode queue (2-6 concurrent), minimap micro optimization, memory cleanup on view switch.

---

## 2026-02-10

**"I don't like the performance on my iPad Pro."** Full 60fps audit across all 9 views. Fixed `transition: all` on game cards, full-viewport background repaint, pointermove storms, main-thread blocking in `buildAllPairs()`. Removed permanent `will-change` from 100+ elements. Upgraded to 3-tier perf (a/b/c). Fixed 5 views for iPhone safe areas. Removed 4 inactive views.

**"Start with sync script."** Built `firestore_sync.py` — pulls 5 Firestore collections into SQLite. Auto-scheduled via launchd every 6h. Added feedback section to State dashboard with live vote data.

**"Implement the picks rewrite."** Replaced the slideshow default view with a tinder-style card swipe for second-round curation. Swipe right = keep, left = remove from picks. Minimap filmstrip with color-coded history.

**"When I hover on the right, green overlay + icon, click to pick."** Replaced separate vote buttons with hover zones — hovering left/right halves of the photo reveals reject/accept overlays. Applied to both Tinder and Picks views.

**"On iPad with my keyboard trackpad I don't see overlays."** Split device detection into 3 independent flags (isMobile, hasTouch, hasHover). Used `(any-hover: hover)` to detect iPad trackpad. Fixed iPadOS sticky hover with JS class toggling instead of CSS `:hover`.

**"Much improve performance and loading."** Thumb-first strategy — cards show 480px thumb instantly, upgrade to full-res in background. Right-sized tiers for iPad (mobile tier instead of display).

---

## 2026-02-09

**"Run all the new V2 signals."** Massive signal extraction session — 10 new CV models, 9 new DB tables, 165K+ new rows:
- Aesthetic v2 (TOPIQ+MUSIQ+LAION) replacing useless NIMA scores (real spread: 16.7–48.3 vs NIMA's everything-is-9.9)
- Face identities via ArcFace → 84 identity clusters
- SAM 2.1 segmentation, Grounding DINO open-vocab detection (108K detections)
- rembg foreground masks, CLIP zero-shot tags, YOLOv8n-pose, OpenCV saliency
- Depth Anything v2 upgraded Small → Large. Florence-2 3-tier captions.

**"Can't you have several processes for Florence?"** Built parallel worker system: 2 MPS + 4 CPU = 0.79/s combined (was 0.4/s single). Batched DB writes to avoid SQLite lock contention. All 9,011 complete in ~5.7h.

**"Do a thorough review to update all."** Full pipeline audit. Regenerated all data files. Vectors v2 (DINOv2-Large + SigLIP2-SO400M) complete. 33 tables, 24 models, everything deployed.

**"Add a DB page that explains it all."** Built Database page — every table, column, model source, coverage, and how they connect. Auto-introspects live DB.

Built Signal Inspector with per-signal model attribution pills. See Square standalone app for square-crop evaluation. Stats infographic page with 13 CSS charts.

---

## 2026-02-08

**"Build more Show experiences."** Three new views: Cinema (Ken Burns slideshow with 11 themed chapters), Reveal (clip-path morphing transitions with 7 geometric shapes), Pulse (breathing mosaic grid with sine-wave animation following cursor). Pushing to 13 total experiences.

**"See should load faster."** Moved `PhotoStore.load()` to async with loading spinner. Added adjacent photo prefetch. Pinch-to-zoom grid via MagnifyGesture (60–400px thumbnails).

Built Drift experience with pre-computed nearest neighbors (DINOv2+CLIP). Added PWA support. Stats infographic page for State.

---

## 2026-02-07

**"Build me a pretty minimal black and white web page."** → Evolved into a full light-first design system with dark mode, AI-alive animations (shimmer, gradient, pulse), and Apple system color palette across all 15 JS modules and State dashboard.

**"What can you work on next?"** Built master orchestrator `completions.py` — checks all 20 pipeline stages, auto-starts missing work, regenerates dashboard after each cycle. No more silent process deaths overnight.

**"I want the same left menu on every page."** Unified sidebar across all 7 pages. Collapsible with localStorage persistence.

Completed Gemini re-analysis (633 remaining → all 9,011 done). Discovered 135,518 images already on GCS. Switched Show to GCS public URLs — fully static, no local proxy needed.

**See (MADCurator) major overhaul:** two-window architecture (Collection + Viewer), curation toolbar with 8 sort options, select mode for batch curation, keyboard shortcuts. Async thumbnail loading with NSCache.

**Repo restructure** — `frontend/` + `backend/` layout. 19 scripts moved and renamed. Data consolidated under `images/`.

**Mobile UX pass** — swipe handlers on 7 experiences, hover guards, viewport safe areas, 44px tap targets, 3-tier perf system. Fixed 21 RED performance violations.

---

## 2026-02-06

**"Create a native app so it is faster, Apple style/rigor."** Built MADCurator — SwiftUI macOS app with faceted search (union/intersection), SQLite direct access, keyboard-driven curation (K/R/arrows), 2000-thumbnail NSCache. Later upgraded to 55 data fields per image, location intelligence, 18 filter dimensions.

**"Build me a web gallery with three ways to see the photos."** Started with 3 experiences (Grille, Dérive, Couleurs), ended the day with 14. Each one a different way to explore photos through their signals: color palette, semantic similarity, connection game, Ken Burns flow, face wall, compass navigation, text search, aesthetic pendulum.

**"This looks like it is from DNG wrongly transformed."** Fixed purple cast on 3,841 DNG files — Display P3 → sRGB color space conversion at decode time.

**"Run programmatic image analysis."** Built pixel-level analysis: 20 metrics per image (luminance, WB deviation, contrast, noise, saturation). Revealed camera-specific patterns — M8 warm shift, Monochrom pristine, G12 worst WB.

**"I want it all."** Ran enhancement engine on all 9,011 photographs. 282 seconds, zero errors. Camera-aware corrections: M8 WB 47% correction, Monochrom untouched, G12 aggressive 64%, MP gentle 30% preserving film warmth.

Signal extraction complete: EXIF, dominant colors, faces (5,686), objects (14,931), perceptual hashes. Apple HIG design system with dark/light themes. GCS versioned image hosting. Dashboard responsive for GitHub Pages.

---

## 2026-02-05

**"Build me a pipeline."** Day one. Registered 9,011 photographs from a decade of shooting across 5 cameras (Leica M8, Monochrom, MP, DJI Osmo Pro, Canon G12). Built 6-tier rendering pyramid (micro 64px → full 3840px) — 54,066 files, ~52 GB.

**"Now the interesting part."** Wired Gemini 2.5 Pro for structured photo analysis (vibes, composition, exposure, editing instructions) and Imagen 3 for 4 variant types (gemini_edit, pro_edit, nano_feel, cartoon). Two-stage architecture: enhance first with Gemini-guided edits, then build style variants on the enhanced image.

**"The edits are not that good."** First 100 Imagen edits had persistent white balance issues. Built blind test (3 methods side by side, click your favorite). 3-way tie with 30% skip rate. Key decision: curate first, enhance after. Don't waste effort improving images with no potential.

Built live dashboard for pipeline monitoring. Created this journal.
