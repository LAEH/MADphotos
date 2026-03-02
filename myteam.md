# MADphotos — Agent Team

Six agents form the pipeline: extract intelligence from every image, curate the best material, prepare experiences, and ship to screens.

---

## image_signals — The Intelligence Layer

Runs 24+ models against every photograph — local open-source models for vision tasks (faces, objects, depth, aesthetics, style, scenes, OCR, captions, colors) plus Gemini API for high-level semantic analysis and Gemma 27B via Ollama for compositional signals. Every signal feeds downstream experiences.

**Say:** `signals`

---

## suggest_image_enhancement — The Improver

Analyzes every image for non-destructive improvements — exposure correction, color balance, shadow recovery. Proposes changes without touching originals. Human votes accept or reject each suggestion.

**Say:** `enhance`

---

## suggest_image_variant — The Artist

Generates AI art variants from photographs using neural style transfer (Van Gogh, Klimt, Seurat, Monet, Munch), Imagen 3 cartoons, and mflux stylization. Learns which styles work best for different image types.

**Say:** `variants`

---

## prepare_show — The Curator

Pre-computes everything the Show app needs to run. Bento compositions with chromatic harmony, boom photo sets, game pairs for the guessing experience, visual scores combining 24+ signals, and lookup indices. Turns raw data into curated experiences.

**Say:** `prepare`

---

## update_and_deploy — The Shipper

10-phase verified deployment pipeline. Preflight safety checks, Firestore sync, gallery export, data regeneration, Vite production builds, Firebase deploy, URL health verification, and postflight cleanup. Nothing ships unless every check passes.

**Say:** `deploy`

---

## MADphotos_ignition — The Launcher

Dev environment startup. Checks git state, port availability, dependencies, database health, and Ollama status. Launches all three servers (serve_show, Show vite, System vite), verifies health, and prints ready URLs.

**Say:** `ignition` | **Stop everything:** `shutdown` | **Health check:** `status`
