# prepare_show — The Curator Agent

## Mission

Pre-compute everything the Show frontend needs so views load instantly instead of rebuilding heavy data structures on every mount. Translates BentoView's 25 curators, BoomView's 56 set definitions, and GameView's 18 pair strategies from TypeScript to Python.

## Lifecycle

```
Audit → Score → Index → Curate → Summary
```

1. **Audit** — Report signal coverage, orientation split, pick count. No files written. (`audit.py`)
2. **Score** — Pre-compute `visual_impact()` and `crop_fitness()` for all picks → `show_scores.json`. (`score.py`)
3. **Index** — Build color buckets, subject words, semantic pops, categorical indices → `show_index.json`. (`index.py`)
4. **Curate** — Build bento compositions, boom sets, game pairs → `show_bentos.json`, `show_boom.json`, `show_pairs.json`. (`curate.py`)
5. **Summary** — Print file sizes and entry counts.

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Constants: paths, output files, BENTO_UNIT_RATIO |
| `run.py` | CLI orchestrator — 5 phases, per-phase flags, fingerprint check |
| `audit.py` | Phase 1: signal coverage report |
| `score.py` | Phase 2: visual_impact + crop_fitness → show_scores.json |
| `index.py` | Phase 3: color buckets, subject words, indices → show_index.json |
| `curate.py` | Phase 4: bento compositions, boom sets, game pairs |

## CLI

```bash
python3 -m backend.prepare_show.run              # full pipeline
python3 -m backend.prepare_show.run --audit      # phase 1: coverage report
python3 -m backend.prepare_show.run --score      # phase 2: scores only
python3 -m backend.prepare_show.run --index      # phase 3: indices only
python3 -m backend.prepare_show.run --curate     # phase 4: experiences only
python3 -m backend.prepare_show.run --dry        # preview without writing
python3 -m backend.prepare_show.run --force      # regenerate even if fresh
```

## Output Files

All written to `frontend/show/public/data/`:

| File | Contents | Size |
|------|----------|------|
| `show_scores.json` | `{scores: {uuid: {vi, cf}}}` — visual impact + crop fitness | ~150 KB |
| `show_index.json` | Color buckets, subject words, semantic pops, categorical indices | ~500 KB |
| `show_bentos.json` | 80 pre-built bento compositions with layout + cell assignments | ~80 KB |
| `show_boom.json` | Diversity-sampled boom sets from 56 definitions | ~60 KB |
| `show_pairs.json` | Deduplicated game pairs from 18 strategies | ~60 KB |

## Design Decisions

1. **Reads `photos.json`, not DB** — all signals already merged by export_gallery.py
2. **Stores only photo IDs** — frontend already has full photo data, keeps files small
3. **Fingerprint-gated** — hashes photos.json mtime+size, skips if unchanged (use `--force` to override)
4. **No frontend changes in V1** — files are generated and deployed, frontend integration is separate

## Source Translation

| Python | TypeScript Source |
|--------|-------------------|
| `score.py` → `visual_impact()` | `BentoView.tsx:88` → `visualImpact()` |
| `score.py` → `crop_fitness()` | `BentoView.tsx:107` → `cropFitness()` |
| `curate.py` → `_fill_cells()` | `BentoView.tsx:149` → `fillCells()` |
| `curate.py` → 25 `curate_*()` | `BentoView.tsx:214-922` → 25 curator functions |
| `curate.py` → `BOOM_DEFS` | `BoomView.tsx:67-159` → 56 set definitions |
| `curate.py` → `_diverse_sample()` | `BoomView.tsx:226-320` → `diverseSample()` |
| `curate.py` → 21 `_strat_*()` | `GameView.tsx:69-896` → 18 strategies |
| `curate.py` → layouts | `layoutRegistry.ts` → DESKTOP_LAYOUTS + MOBILE_LAYOUTS |
