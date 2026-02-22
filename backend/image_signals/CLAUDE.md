# image_signals — Per-Image Signal Agent

## Mission

Own every image's signals. Inspect, extract, validate, heal, and evolve the signal layer — one image at a time. This agent ensures every photograph in the archive has complete, consistent, well-formatted metadata from every available model. When signals are missing, it triggers inference. When signals are stale, it re-extracts. When new models become available, it proposes and runs them.

This agent operates at the **image level** — it cares about a single image having all its signals. It does NOT create sets, samples, or collections (that's a future agent's job).

## Responsibilities

### 1. Inspect
- Check DB health: all 33+ signal tables populated for every image
- Validate signal consistency (e.g., face_detections and facial_emotions should cover the same images)
- Detect malformed data (BLOB corruption, NULL where shouldn't be, invalid JSON)
- `completions.py --status` gives the full picture

### 2. Fill Gaps
- Detect missing signals per image and trigger the right model
- Run local models (GPU): aesthetics, depth, scene, style, OCR, captions, faces, objects, segments, pose, saliency, vectors
- Run cloud models (API): Gemini for semantic analysis, Gemma for creative analysis
- Run programmatic extractors: EXIF, pixel stats, quality scores, border detection, unified labels/texts

### 3. Orchestrate
- `completions.py` is the master orchestrator — knows all 24+ pipeline stages
- Can auto-start missing processes, watch until 100% complete
- Respects model dependencies (e.g., unified_labels depends on captions + detections)

### 4. Evolve
- Take user suggestions for new signals to extract
- Propose next-best-action: "these 200 images lack Gemma composition data"
- When new models appear, add a new script + DB table + register in completions
- Track what's been tried and what worked

## Key Files

| File | Purpose |
|------|---------|
| `completions.py` | **Master orchestrator.** Checks all 24+ pipeline stages, auto-starts missing, watch mode. The first script to run. |
| `signals.py` | V0 basics: EXIF, dominant colors, face detection, object detection, image hashes |
| `pixel_analysis.py` | 31 pixel-level metrics: brightness, dynamic range, noise, color temp, shadows, highlights |
| `signals_advanced.py` | V1 GPU models: LAION aesthetic, Depth Anything, Places365, EasyOCR, BLIP, DeepFace |
| `signals_v2.py` | V2 GPU models (12 phases): TOPIQ+MUSIQ, Florence-2, SAM 2.1, Grounding DINO, RAM++, rembg, pose, saliency |
| `vectors.py` | V1 embeddings: DINOv2-base (768d), SigLIP-base (768d), CLIP ViT-B/32 (512d) |
| `vectors_v2.py` | V2 embeddings: DINOv2-Large (1024d), SigLIP2-SO400M (1152d), CLIP ViT-B/32 (512d) |
| `quality_scores.py` | Technical + CLIP semantic quality scoring |
| `gemini.py` | Gemini 2.5 Pro cloud analysis: exposure, composition, grading, vibes, semantic pops |
| `run_gemma_analysis.py` | Gemma 27B local analysis: description, stories, crops, composition, cartoon style |
| `border_crop.py` | OpenCV edge detection for analog film scan borders |
| `populate_unified.py` | Cross-model consensus: unified_labels, unified_texts |
| `run_gemma_forever.sh` | Auto-restarting Gemma wrapper for overnight runs |
| `gemma_monitor.py` | Terminal dashboard: progress, rate, ETA for Gemma runs |

### Worker Scripts (subprocess helpers)
| File | Purpose |
|------|---------|
| `_florence_worker.py` | Standalone parallel Florence-2 captioning (avoids GPU memory fragmentation) |
| `_rembg_standalone.py` | Standalone rembg foreground extraction (avoids MPS float64 issue) |

### Legacy (in `legacy/`)
| File | Replaced By |
|------|-------------|
| `run_gemma_picks.py` | `run_gemma_analysis.py` |
| `run_gemma_composition.py` | `run_gemma_analysis.py` |
| `run_gemma_deep.py` | `run_gemma_analysis.py` |

## Pipeline Order

For new images, run in this order (or use `completions.py` to auto-detect gaps):

1. `signals.py` — EXIF, colors, faces, objects, hashes (CPU)
2. `pixel_analysis.py` — 31 pixel metrics (CPU, parallelized)
3. `signals_advanced.py` — V1 GPU models (aesthetic, depth, scene, style, OCR, captions, emotions)
4. `signals_v2.py` — V2 GPU models (12 phases)
5. `vectors.py` — V1 embeddings → LanceDB
6. `vectors_v2.py` — V2 embeddings → LanceDB
7. `quality_scores.py` — Technical + semantic quality
8. `run_gemma_analysis.py` — Gemma 27B creative analysis (requires Ollama)
9. `gemini.py` — Gemini 2.5 Pro cloud analysis (API, rate limited)
10. `border_crop.py` — Film scan border detection
11. `populate_unified.py` — Cross-model aggregation
12. `completions.py` — Master status check

## DB Tables Owned

This agent writes to ALL signal tables:
`exif_metadata`, `dominant_colors`, `face_detections`, `facial_emotions`, `face_identities`, `object_detections`, `open_detections`, `ocr_detections`, `image_hashes`, `image_analysis`, `aesthetic_scores`, `aesthetic_scores_v2`, `quality_scores`, `depth_estimation`, `scene_classification`, `style_classification`, `image_captions`, `florence_captions`, `image_tags`, `segmentation_masks`, `foreground_masks`, `pose_detections`, `saliency_maps`, `border_crops`, `image_locations`, `enhancement_plans`, `enhancement_plans_v2`, `gemini_analysis`, `gemma_analysis`, `unified_labels`, `unified_texts`

**`gemma_analysis`** is the canonical Gemma table (replaces legacy `gemma_picks` + `gemma_composition`). 5 columns are Gemini-redundant and **no longer generated** for new rows: `setting`, `time_of_day`, `weather`, `grading_style`, `faces_count`. Existing data preserved for ~2,415 rows already processed. Legacy tables (`gemma_picks`, `gemma_composition`) are preserved in DB but not written to.

Vector tables in LanceDB (`images/vectors.lance`): `image_vectors`, `image_vectors_v2`

## Adding a New Signal

1. Create a new script in this directory
2. Create a DB table via `CREATE TABLE IF NOT EXISTS` in the script
3. Register the stage in `completions.py` (`STAGES` list + `TABLE_MAP`)
4. Update this CLAUDE.md and `README.md`
5. Run for all 9,011 images
6. Update `export_gallery.py` if the signal should flow to Show app

## Running

```bash
# Check all pipeline stages
python3 backend/image_signals/completions.py --status

# Auto-detect and fix gaps
python3 backend/image_signals/completions.py

# Watch mode — re-check every 60s until 100%
python3 backend/image_signals/completions.py --watch

# Gemma overnight (auto-restarts on crash)
nohup bash backend/image_signals/run_gemma_forever.sh 3 &
```
