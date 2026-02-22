# Signal Extraction Pipeline

All signal extraction scripts for MADphotos. These scripts analyze images and store results in `images/mad_photos.db`.

## Pipeline Order

Run in this order for new images (or use `completions.py` to auto-detect and fill gaps):

| Order | Script | Models | DB Tables | Notes |
|-------|--------|--------|-----------|-------|
| 1 | `signals.py` | YuNet, YOLOv8, OpenCV | `exif_metadata`, `dominant_colors`, `face_detections`, `object_detections`, `image_hashes` | Fast, CPU-only |
| 2 | `pixel_analysis.py` | NumPy/Pillow stats | `image_analysis` | 31 pixel metrics, parallelized |
| 3 | `signals_advanced.py` | LAION aesthetic, Depth Anything, Places365, EasyOCR, BLIP, DeepFace | `aesthetic_scores`, `depth_estimation`, `scene_classification`, `style_classification`, `ocr_detections`, `image_captions`, `facial_emotions` | One model at a time, GPU |
| 4 | `signals_v2.py` | TOPIQ+MUSIQ, Florence-2, SAM 2.1, Grounding DINO, RAM++, rembg, pose, saliency | `aesthetic_scores_v2`, `florence_captions`, `segmentation_masks`, `open_detections`, `image_tags`, `foreground_masks`, `pose_detections`, `saliency_maps` | 12 phases, GPU |
| 5 | `vectors.py` | DINOv2-base, SigLIP-base, CLIP | LanceDB `image_vectors` | V1 embeddings |
| 6 | `vectors_v2.py` | DINOv2-Large, SigLIP2-SO400M, CLIP | LanceDB `image_vectors_v2` | V2 embeddings |
| 7 | `quality_scores.py` | OpenCV + CLIP | `quality_scores` | Technical + semantic quality |
| 8 | `run_gemma_analysis.py` | madphotos-critic (Ollama gemma3:27b) | `gemma_analysis` | Requires Ollama running |
| 9 | `gemini.py` | Gemini 2.5 Pro (API) | `gemini_analysis` | Cloud API, rate limited |
| 10 | `border_crop.py` | OpenCV edge detection | `border_crops` | Analog film scans only |
| 11 | `populate_unified.py` | None (aggregation) | `unified_labels`, `unified_texts` | Cross-model consensus |
| 12 | `completions.py` | None (orchestrator) | Reads all tables | Master status + auto-fix |

## Worker Scripts

- `_florence_worker.py` -- Standalone parallel Florence-2 captioning worker
- `_rembg_standalone.py` -- Standalone rembg foreground extraction (avoids MPS float64 issue)

## Legacy (superseded)

In `legacy/`:
- `run_gemma_picks.py` -- Replaced by `run_gemma_analysis.py`
- `run_gemma_composition.py` -- Replaced by `run_gemma_analysis.py`
- `run_gemma_deep.py` -- Replaced by `run_gemma_analysis.py`

## Running the Full Pipeline

```bash
# Check status of all stages
python3 backend/image_signals/completions.py --status

# Auto-detect and fix gaps (starts missing processes)
python3 backend/image_signals/completions.py

# Watch mode -- re-check every 60s until 100%
python3 backend/image_signals/completions.py --watch
```

## Adding a New Signal

1. Create a new script in this directory
2. Create a DB table (via `CREATE TABLE IF NOT EXISTS` in the script)
3. Register the stage in `completions.py` (add to `STAGES` list and `TABLE_MAP`)
4. Update this README
