# backend/bento/ — Finite-Ratio Bento Layout System

## The Ratio System

**UNIT_RATIO = 1 (square units)**

Exactly 7 allowed aspect ratios. No other cell shapes permitted.

| Ratio | w:h | rs × cs          | Orient | Crop Key |
|-------|-----|-------------------|--------|----------|
| 1/2   | 1:2 | 2×1               | P      | 2:3      |
| 2/3   | 2:3 | 3×2               | P      | 2:3      |
| 3/4   | 3:4 | 4×3               | P      | 2:3      |
| 1     | 1:1 | 1×1, 2×2, 3×3    | L      | 1:1      |
| 4/3   | 4:3 | 3×4               | L      | 3:2      |
| 3/2   | 3:2 | 2×3               | L      | 3:2      |
| 2/1   | 2:1 | 1×2               | L      | 16:9     |

**Cell ratio formula:** `(cs × UNIT_RATIO) / rs = cs / rs`

## Grid Dimensions

- **Desktop:** 5×3 grid (15 units). Ratio 5/3 ≈ 1.667 → units nearly square on 16:9 screens.
- **Mobile:** 3×6 grid (18 units). Ratio 3/6 = 0.5 → units nearly square on 9:16 screens.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Constants: UNIT_RATIO, ALLOWED_RATIOS, ALLOWED_SPANS, CROP_KEY_MAP |
| `ratios.py` | `cell_ratio()`, `ratio_to_crop_key()`, `is_valid_cell()`, `orient_for_cell()` |
| `layouts.py` | All layout definitions — desktop, mobile, starters, small |
| `assign.py` | `fill_cells()`, `orient_pools()`, `crop_fitness()` |
| `validate.py` | `validate_layout()`, `validate_all()`, CLI tool |

## Adding New Layouts

1. Define the layout in `layouts.py` using `P()` and `L()` helpers
2. Every cell must use spans from `ALLOWED_SPANS`
3. Total cell area must equal `cols × rows`
4. No overlaps — each grid position covered by exactly one cell
5. Run `python3 -m backend.bento.validate` to verify

## How Assignment Works

`fill_cells(cells, pools, used_ids, score_fn)`:

1. Sort cells by area (largest first) — big tiles get best photos
2. For each cell, find the best photo from the matching orientation pool
3. Score = `score_fn(photo) + crop_fitness(photo, ratio_key)`
4. Fall back to opposite orientation pool if primary is empty
5. Second pass fills any remaining empty slots

## Integration

- **prepare_show:** Imports layouts + assignment from this module
- **Frontend (layoutRegistry.ts):** Mirrors these layout definitions in TypeScript
- **cropUtils.ts:** Uses UNIT_RATIO=1 and maps the 7 ratios to crop keys
