# suggest_image_enhancement — Enhancement Agent

## Mission

Get the user to **vote accept** on proposed enhancements to their photographs. Each enhancement is a non-destructive transformation (border crop, exposure correction, rotation fix, Gemma-suggested crop) that improves the image. Accepted enhancements get deployed as the new "enhanced" tier in the Show app.

## Lifecycle

```
Propose → Preview → Present → Vote → Deploy
```

1. **Propose** — Analyze signals from the DB (border_crops, enhancement_plans, gemma_analysis) to identify images that would benefit from specific transformations. Generate a batch of ~30 proposals. (`propose.py`)
2. **Preview** — Render before/after previews so the user can see exactly what would change. (`preview.py`)
3. **Present** — Serve proposals through the System app's Enhancement page for user review. (`serve_show.py` endpoints, System frontend)
4. **Vote** — User accepts, rejects, or gives feedback on each proposal. Votes inform future batch composition. (`db.py`)
5. **Deploy** — Accepted proposals get: transformation applied to display-tier source, rendered to all tiers (display/mobile/thumb/micro in JPEG+WebP), uploaded to GCS, DB updated. (`deploy.py`)

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Shared constants: paths (DB, rendered dirs, preview dir), enhancement types, batch size |
| `propose.py` | `generate_batch()` — the brain. Collects signals, learns from review history (acceptance rates per type), composes diverse batches of ~30 proposals with preview rendering |
| `preview.py` | `render_border_crop()`, `render_gemma_crop()`, `render_rotation()`, `render_combined()`, `save_preview()` — applies transformations and saves preview images |
| `db.py` | All DB operations: `ensure_tables()`, `create_proposal()`, `update_proposal()`, `get_batch_proposals()`, `get_stats()`, `get_learning_stats()`, `get_accepted_undeployed()`, `mark_deployed()` |
| `deploy.py` | Post-accept pipeline: apply transformation, render all tiers (display/mobile/thumb/micro), upload to GCS, mark deployed in DB |

## Enhancement Scripts (tools)

| File | Purpose |
|------|---------|
| `enhance_v1.py` | V1 enhancement engine — per-channel corrections based on `enhancement_plans` table |
| `enhance_v2.py` | V2 enhancement engine — depth/scene/style/vibe/face-aware adjustments from `enhancement_plans_v2` |
| `enhance_exposure.py` | Exposure-specific corrections for underexposed photos |

## Enhancement Types

| Type | Signal Source | What It Does |
|------|--------------|--------------|
| `border_crop` | `border_crops` table | Removes detected borders (letterboxing, film rebates, scanner artifacts) |
| `exposure` | `enhancement_plans` / `enhancement_plans_v2` | Corrects under/over-exposure with per-channel adjustments |
| `gemma_crop` | `gemma_analysis` table | Applies Gemma-suggested crops (1:1, 2:3, 3:2, 16:9) to improve composition |
| `rotation` | `gemma_analysis` table | Fixes horizon/vertical alignment issues |

## DB Tables

- **`enhance_batches`** — One row per batch. Columns: `id`, `status` (`active`/`completed`), `created_at`, `completed_at`
- **`enhance_proposals`** — One row per proposed enhancement. Columns: `id`, `batch_id`, `image_uuid`, `type`, `params_json`, `status` (`pending`/`accepted`/`rejected`/`feedback`), `preview_path`, `feedback`, `reviewed_at`, `deployed_at`
- Source signal tables: `border_crops`, `enhancement_plans`, `enhancement_plans_v2`, `gemma_analysis`

## Iterative Learning

The agent learns from every vote:

- `get_learning_stats()` returns acceptance rates per enhancement type
- `propose.py` uses these rates to compose batches: types with higher acceptance rates get more slots
- Types with consistently low acceptance rates get fewer proposals per batch
- The user's feedback text (optional) is stored for future reference

## Deploy Pipeline

When a batch is fully reviewed (all proposals voted on):
1. System auto-detects completion
2. `deploy.py` runs for each accepted proposal:
   - Apply transformation to display-tier JPEG source
   - Render 4 tiers: display (2048px), mobile (1280px), thumb (480px), micro (64px)
   - Each tier in both JPEG and WebP
   - Sharpen mobile and thumb tiers
   - Upload all files to GCS (`gs://myproject-public-assets/art/MADphotos/v/enhanced/`)
   - Mark proposal as deployed in DB
3. `export_gallery.py` regenerates `photos.json` so Show app picks up enhanced versions
4. `dashboard.py` regenerates System data

## System App Integration

The System app's Enhancement page shows:
- Current batch of proposals with before/after previews
- Accept/reject/feedback voting buttons
- Per-type acceptance rate stats (learning dashboard)
- Accepted history with deploy status
- Generate new batch button

API endpoints in `serve_show.py`:
- `GET /api/enhance/batch` — current active batch with proposals
- `GET /api/enhance/stats` — per-type statistics and rates
- `GET /api/enhance/accepted` — all accepted proposals with deploy status
- `POST /api/enhance/vote` — record accept/reject/feedback, auto-deploy on batch completion
- `POST /api/enhance/deploy` — manual deploy trigger
- `POST /api/enhance/generate` — generate a new batch of proposals

## Rendering Details

Preview images are saved to `images/rendered/enhance_previews/{uuid}_{type}.jpg`.

Deploy tiers use these configs:
- **display**: 2048px long edge, JPEG q88, WebP q82, progressive
- **mobile**: 1280px, JPEG q85, WebP q80, progressive, unsharp mask
- **thumb**: 480px, JPEG q82, WebP q78, unsharp mask
- **micro**: 64px, JPEG q70, WebP q68

Enhanced images are stored in `images/rendered/enhanced/` and `images/rendered/enhanced_exposure/jpeg/`.
