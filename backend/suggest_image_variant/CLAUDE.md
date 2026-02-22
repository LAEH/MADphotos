# suggest_image_variant — Style Transfer Agent

## Mission

Get the user to **vote accept** on AI-generated style variants of their photographs. Every decision in this agent — which styles to try, which images to pick, how to present results — serves that goal. A rejected variant is wasted API cost. An accepted variant becomes a new image in the Show app.

## Lifecycle

```
Research → Select → Generate → Present → Vote → Deploy
```

1. **Research** — Discover and define new artistic styles. Study acceptance patterns. Identify what the user likes and why. (`config.py`, `select.py`)
2. **Select** — Pick 2 styles per image using affinity scoring + performance memory + explore/exploit balance. (`select.py`, `config.py`)
3. **Generate** — Call Imagen 3 EDIT_MODE_STYLE (or future engines: mflux, neural style transfer, other APIs) to produce variants. (`generate.py`, `run.py`)
4. **Present** — Serve generated variants through the System app's Generated page for user review. (`serve_show.py` endpoints, System frontend)
5. **Vote** — User accepts or rejects each variant. Votes are recorded in `ai_variants` table. (`serve_show.py`, System frontend)
6. **Deploy** — Accepted variants get: border-trimmed, rendered to all tiers (display/mobile/thumb/micro in JPEG+WebP), uploaded to GCS, DB updated, photos.json regenerated so Show app displays them. (`deploy.py`, `trim_variant_borders.py`)

## Key Files

| File | Purpose |
|------|---------|
| `config.py` | All 23+ style definitions (prompt, family, affinities), performance thresholds, constants |
| `select.py` | `pick_styles()` — the brain. Affinity scoring, performance memory from DB review history, 80/20 explore/exploit, dead-style exclusion |
| `generate.py` | `generate_variant()` — calls Imagen 3, saves to disk, upserts DB. Handles retries, rate limits, safety filters |
| `run.py` | CLI orchestrator. `--generate`, `--deploy`, `--scorecard`, `--dry`. Loads rates, picks styles, generates, auto-scorecards |
| `deploy.py` | Post-accept pipeline: copy to `ai_variants/`, render tiers, upload GCS, backfill `style_key` column |
| `prompt.py` | Prompt construction helpers |
| `neural_style.py` | VGG19 neural style transfer (alternative engine to Imagen) |
| `STYLES.md` | Auto-generated performance scorecard — acceptance rates per style |
| `style_references/` | 5 public-domain art references for neural style transfer |
| `output/` | Timestamped experiment directories with generated images |

## Legacy Files (reference only)

| File | Note |
|------|------|
| `smart_variants_v1.py` | First-gen Imagen pipeline (before run.py orchestrator) |
| `smart_variants_v2.py` | V2 with dark/light variants (before run.py orchestrator) |
| `test_images.py` | Early test harness using style_prompts_test.json from Gemma |
| `style_prompts.py` | Gemma-based prompt generation (superseded by config.py style definitions) |
| `style_prompts_test.json` | Gemma-generated prompts (322K, historical reference) |

## DB Tables

- **`ai_variants`** — One row per generated variant. Key columns: `variant_id`, `image_uuid`, `variant_type` (`smart_style`), `style_key`, `prompt`, `generation_status` (`success`/`filtered`/`failed`), `review_status` (`accepted`/`rejected`/NULL), `model`, `generation_time_ms`, `border_*`, `trimmed`
- **`dominant_colors`** — Used by deploy to extract variant palette
- **`tiers`** — Rendered tier paths (populated by deploy)

## Performance Memory System

The agent learns from every vote:

- `get_style_rates()` queries historical accept/reject counts per `style_key`
- Styles with ≥8 reviews get a performance modifier: `(rate - 0.45) * 10.0`
- Styles with <3 reviews get an exploration bonus (+2.0)
- Styles with <10% rate AND ≥15 reviews are **dead** — auto-excluded (score = -999)
- The `--scorecard` command generates `STYLES.md` with current rates and status buckets (Star/Solid/Weak/Poor/Dead/New)

## Explore/Exploit

Slot 1: Always the highest-scoring style for the image.
Slot 2: 80% exploit (next-best from a different family), 20% explore (random undertested style with <5 reviews from a different family).

This ensures proven winners dominate while new styles get fair trial runs.

## Style Families

Styles are grouped into families (e.g., `japanese`, `western_illustration`, `graphic`, `fine_art`, `expressionist`, `pop_culture`). The agent never picks two styles from the same family for one image — diversity is enforced.

## Adding a New Style

1. Add to `STYLES` dict in `config.py`: key, prompt, family, affinities (scene/style/vibe/object/depth/camera bonuses)
2. Run `--dry --count 20` to verify it gets selected for appropriate images
3. Run `--generate --count 10` to produce first variants
4. Review in System app — the performance system will learn from votes
5. After 8+ reviews, the system auto-adjusts its selection weight

## Engines

Currently: **Imagen 3** (`imagen-3.0-capability-001`) via Vertex AI, EDIT_MODE_STYLE, guidance=75.
Alternative: **Neural Style Transfer** (VGG19, `neural_style.py`) — 5 art styles, runs locally on MPS.
Future: mflux (local Flux diffusion), other cloud APIs.

## System App Integration

The System app's Generated page (`frontend/system/src/pages/GeneratedPage.tsx`) shows:
- Generated variants grouped by image
- Accept/reject voting buttons
- Generation progress (polling `_handle_generated_progress`)
- Style distribution stats

API endpoints in `serve_show.py`:
- `GET /api/generated/progress` — current generation run status
- `POST /api/generated/vote` — record accept/reject
- `POST /api/generated/deploy` — trigger deploy pipeline
