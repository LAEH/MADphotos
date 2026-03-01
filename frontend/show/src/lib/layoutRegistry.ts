/**
 * layoutRegistry.ts — Shared layout definitions for Bento and other fixed-screen views.
 * Extracted from BentoView.tsx. Houses all grid layouts, dynamic generators,
 * density computation, and the bento-bug fix (hasMixedSizes).
 */

import { BENTO_UNIT_RATIO } from './cropUtils'
import { randomFrom } from './utils'
import type { BentoCell } from './cropUtils'
import type { Photo } from '../types/photo'

/* ===== Layout type ===== */

export interface BentoLayout {
  id: string
  cols: number
  rows: number
  count: number
  cells: BentoCell[]
  device: 'desktop' | 'mobile'
}

/* ===== Cell helpers ===== */

/** Portrait cell (1 col × 2 rows → ratio 0.667 with 4:3 unit) */
function P(r: number, c: number, rs: number, cs: number): BentoCell {
  return { r, c, rs, cs, orient: 'P' }
}

/** Landscape cell (1×1 → ratio 1.333, or 2×2 → ratio 1.333) */
function L(r: number, c: number, rs: number, cs: number): BentoCell {
  return { r, c, rs, cs, orient: 'L' }
}

/* ── Desktop layouts (5×4 grid, ratio ≈ 1.667, 8–11 images) ── */

export const DESKTOP_LAYOUTS: BentoLayout[] = [
  /* D1: Balanced — 5×4, 8 images, 3P 5L */
  {
    id: 'D1', cols: 5, rows: 4, count: 8, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1), L(1, 4, 2, 2),
      P(3, 1, 2, 1), L(3, 2, 2, 2), P(3, 4, 2, 1),
      L(3, 5, 1, 1), L(4, 5, 1, 1),
    ],
  },
  /* D2: Gallery — 5×4, 11 images, 3P 8L */
  {
    id: 'D2', cols: 5, rows: 4, count: 11, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 2, 2), L(1, 4, 1, 1), P(1, 5, 2, 1),
      L(2, 4, 1, 1),
      L(3, 1, 2, 2), P(3, 3, 2, 1), L(3, 4, 1, 1), L(3, 5, 1, 1),
      L(4, 4, 1, 1), L(4, 5, 1, 1),
    ],
  },
  /* D3: Columns — 5×4, 11 images, 3P 8L */
  {
    id: 'D3', cols: 5, rows: 4, count: 11, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 2, 2), P(1, 4, 2, 1), L(1, 5, 1, 1),
      L(2, 5, 1, 1),
      P(3, 1, 2, 1), L(3, 2, 1, 1), L(3, 3, 1, 1), L(3, 4, 2, 2),
      L(4, 2, 1, 1), L(4, 3, 1, 1),
    ],
  },
  /* D4: Feature — 5×4, 9 images, 2P 7L */
  {
    id: 'D4', cols: 5, rows: 4, count: 9, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), L(1, 3, 1, 1), P(1, 4, 2, 1), L(1, 5, 1, 1),
      P(2, 3, 2, 1), L(2, 5, 1, 1),
      L(3, 1, 2, 2), L(3, 4, 2, 2), L(4, 3, 1, 1),
    ],
  },
  /* D5: Mosaic — 5×4, 10 images, 4P 6L */
  {
    id: 'D5', cols: 5, rows: 4, count: 10, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 2, 2), P(1, 4, 2, 1), L(1, 5, 1, 1),
      L(2, 5, 1, 1),
      L(3, 1, 1, 1), P(3, 2, 2, 1), L(3, 3, 2, 2), P(3, 5, 2, 1),
      L(4, 1, 1, 1),
    ],
  },
  /* D6: Quilt — 5×4, 16 images, 4P 12L — no large cells */
  {
    id: 'D6', cols: 5, rows: 4, count: 16, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), P(1, 2, 2, 1), L(1, 3, 1, 1), L(1, 4, 1, 1), L(1, 5, 1, 1),
                                       L(2, 3, 1, 1), L(2, 4, 1, 1), L(2, 5, 1, 1),
      L(3, 1, 1, 1), L(3, 2, 1, 1), P(3, 3, 2, 1), P(3, 4, 2, 1), L(3, 5, 1, 1),
      L(4, 1, 1, 1), L(4, 2, 1, 1),                                  L(4, 5, 1, 1),
    ],
  },
  /* D7: Portrait Wall — 5×4, 14 images, 6P 8L — portrait-heavy, no large cells */
  {
    id: 'D7', cols: 5, rows: 4, count: 14, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 1, 1), P(1, 3, 2, 1), L(1, 4, 1, 1), P(1, 5, 2, 1),
                       L(2, 2, 1, 1),                  L(2, 4, 1, 1),
      P(3, 1, 2, 1), L(3, 2, 1, 1), P(3, 3, 2, 1), L(3, 4, 1, 1), P(3, 5, 2, 1),
                       L(4, 2, 1, 1),                  L(4, 4, 1, 1),
    ],
  },
  /* D8: Rhythm — 5×4, 16 images, 4P 12L — alternating columns, no large cells */
  {
    id: 'D8', cols: 5, rows: 4, count: 16, device: 'desktop',
    cells: [
      L(1, 1, 1, 1), P(1, 2, 2, 1), L(1, 3, 1, 1), P(1, 4, 2, 1), L(1, 5, 1, 1),
      L(2, 1, 1, 1),                  L(2, 3, 1, 1),                  L(2, 5, 1, 1),
      L(3, 1, 1, 1), P(3, 2, 2, 1), L(3, 3, 1, 1), P(3, 4, 2, 1), L(3, 5, 1, 1),
      L(4, 1, 1, 1),                  L(4, 3, 1, 1),                  L(4, 5, 1, 1),
    ],
  },
  /* D9: Panoramic — 5×3, 11 images, 2P 9L — wider, shorter grid */
  {
    id: 'D9', cols: 5, rows: 3, count: 11, device: 'desktop',
    cells: [
      L(1, 1, 1, 1), L(1, 2, 1, 1), P(1, 3, 2, 1), L(1, 4, 1, 1), L(1, 5, 1, 1),
      L(2, 1, 1, 1), L(2, 2, 1, 1),                  L(2, 4, 1, 1), P(2, 5, 2, 1),
      L(3, 1, 1, 1), L(3, 2, 1, 1), L(3, 3, 1, 1), L(3, 4, 1, 1),
    ],
  },
  /* D10: Dense Grid — 4×4, 12 images, 4P 8L — compact square grid, no large cells */
  {
    id: 'D10', cols: 4, rows: 4, count: 12, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 1, 1), L(1, 3, 1, 1), P(1, 4, 2, 1),
                       L(2, 2, 1, 1), L(2, 3, 1, 1),
      L(3, 1, 1, 1), P(3, 2, 2, 1), P(3, 3, 2, 1), L(3, 4, 1, 1),
      L(4, 1, 1, 1),                                  L(4, 4, 1, 1),
    ],
  },
  /* DS1: Solo — 1 image */
  { id: 'DS1', cols: 1, rows: 1, count: 1, device: 'desktop', cells: [L(1,1,1,1)] },
  /* DS2: Pair — 2 side by side */
  { id: 'DS2', cols: 2, rows: 1, count: 2, device: 'desktop', cells: [L(1,1,1,1), L(1,2,1,1)] },
  /* DS3: Trio strip — ALL SAME SIZE */
  { id: 'DS3', cols: 3, rows: 1, count: 3, device: 'desktop', cells: [L(1,1,1,1), L(1,2,1,1), L(1,3,1,1)] },
  /* DS4: Quad — 2×2 — ALL SAME SIZE */
  { id: 'DS4', cols: 2, rows: 2, count: 4, device: 'desktop', cells: [L(1,1,1,1), L(1,2,1,1), L(2,1,1,1), L(2,2,1,1)] },
  /* DS6: Quilt — 3×2 — ALL SAME SIZE */
  {
    id: 'DS6', cols: 3, rows: 2, count: 6, device: 'desktop',
    cells: [L(1,1,1,1), L(1,2,1,1), L(1,3,1,1), L(2,1,1,1), L(2,2,1,1), L(2,3,1,1)],
  },
  /* DS6p: Portraits — 3×2 with 2P — MIXED SIZES */
  {
    id: 'DS6p', cols: 3, rows: 2, count: 4, device: 'desktop',
    cells: [P(1,1,2,1), L(1,2,1,1), P(1,3,2,1), L(2,2,1,1)],
  },
]

/* ── Mobile layouts (3×4 grid, bigger tiles, 4–6 images) ── */

export const MOBILE_LAYOUTS: BentoLayout[] = [
  /* M1: Hero — 3×4, 5 images. Big hero top-left, portrait right, 3 portraits bottom */
  {
    id: 'M1', cols: 3, rows: 4, count: 5, device: 'mobile',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1),
      P(3, 1, 2, 1), P(3, 2, 2, 1), P(3, 3, 2, 1),
    ],
  },
  /* M2: Blocks — 3×4, 4 images. Diagonal big blocks */
  {
    id: 'M2', cols: 3, rows: 4, count: 4, device: 'mobile',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 2, 2),
      L(3, 1, 2, 2), P(3, 3, 2, 1),
    ],
  },
  /* M3: Feature — 3×4, 5 images. Full-width banner top, portrait pair + squares bottom */
  {
    id: 'M3', cols: 3, rows: 4, count: 5, device: 'mobile',
    cells: [
      L(1, 1, 2, 3),
      P(3, 1, 2, 1), L(3, 2, 1, 1), P(3, 3, 2, 1),
      L(4, 2, 1, 1),
    ],
  },
  /* M4: Rhythm — 3×4, 6 images. Mixed sizes for visual variety */
  {
    id: 'M4', cols: 3, rows: 4, count: 6, device: 'mobile',
    cells: [
      L(1, 1, 1, 2), P(1, 3, 2, 1),
      L(2, 1, 1, 1), L(2, 2, 1, 1),
      P(3, 1, 2, 1), L(3, 2, 2, 2),
    ],
  },
  /* M5: Vertical — 3×4, 5 images. Full-height portrait left, stack right */
  {
    id: 'M5', cols: 3, rows: 4, count: 5, device: 'mobile',
    cells: [
      P(1, 1, 4, 1), L(1, 2, 2, 2),
      L(3, 2, 1, 1), L(3, 3, 1, 1),
      L(4, 2, 1, 2),
    ],
  },
  /* M6: Mosaic — 3×6, 6 images. All big tiles, alternating hero blocks */
  {
    id: 'M6', cols: 3, rows: 6, count: 6, device: 'mobile',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1),
      P(3, 1, 2, 1), L(3, 2, 2, 2),
      L(5, 1, 2, 2), P(5, 3, 2, 1),
    ],
  },
  /* M7: Column — 3×6, 7 images. 2 hero blocks + 3 portraits bottom */
  {
    id: 'M7', cols: 3, rows: 6, count: 7, device: 'mobile',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1),
      P(3, 1, 2, 1), L(3, 2, 2, 2),
      P(5, 1, 2, 1), P(5, 2, 2, 1), P(5, 3, 2, 1),
    ],
  },
  /* M8: Wall — 3×6, 9 images. 3 rows of portrait trios */
  {
    id: 'M8', cols: 3, rows: 6, count: 9, device: 'mobile',
    cells: [
      P(1, 1, 2, 1), P(1, 2, 2, 1), P(1, 3, 2, 1),
      P(3, 1, 2, 1), P(3, 2, 2, 1), P(3, 3, 2, 1),
      P(5, 1, 2, 1), P(5, 2, 2, 1), P(5, 3, 2, 1),
    ],
  },
  /* MS1: Solo */
  { id: 'MS1', cols: 1, rows: 1, count: 1, device: 'mobile', cells: [L(1,1,1,1)] },
  /* MS2: Stack — 2 stacked */
  { id: 'MS2', cols: 1, rows: 2, count: 2, device: 'mobile', cells: [L(1,1,1,1), L(2,1,1,1)] },
  /* MS3: Triple stack — ALL SAME SIZE */
  { id: 'MS3', cols: 1, rows: 3, count: 3, device: 'mobile', cells: [L(1,1,1,1), L(2,1,1,1), L(3,1,1,1)] },
  /* MS4: Quad — 2×2 — ALL SAME SIZE */
  { id: 'MS4', cols: 2, rows: 2, count: 4, device: 'mobile', cells: [L(1,1,1,1), L(1,2,1,1), L(2,1,1,1), L(2,2,1,1)] },
  /* MS6: Grid — 2×3 — ALL SAME SIZE */
  {
    id: 'MS6', cols: 2, rows: 3, count: 6, device: 'mobile',
    cells: [L(1,1,1,1), L(1,2,1,1), L(2,1,1,1), L(2,2,1,1), L(3,1,1,1), L(3,2,1,1)],
  },
]

/* ===== Density ===== */

export const BENTO_DENSITY_STEPS = [2, 4, 6, 8, 12, 16, 24, 36, 48, 64]
export const BENTO_DEFAULT_DENSITY_IDX = 3 // 8 images

/* ===== Mixed-size detection (bento bug fix) ===== */

/** Returns true if layout has ≥2 different cell size classes (rs×cs combos).
 *  Used to filter out all-same-size layouts (DS3, DS4, DS6, MS3, MS4, MS6)
 *  from bento mode, where visual variety is the whole point. */
export function hasMixedSizes(layout: BentoLayout): boolean {
  const sizes = new Set<string>()
  for (const cell of layout.cells) {
    sizes.add(`${cell.rs}x${cell.cs}`)
  }
  return sizes.size >= 2
}

/* ===== Dynamic layout generation ===== */

export function uniformBentoGrid(count: number, device: 'desktop' | 'mobile'): BentoLayout {
  if (count <= 0) count = 1
  if (count <= 3) {
    if (count === 1) return { id: 'UG1', cols: 1, rows: 1, count: 1, device, cells: [L(1,1,1,1)] }
    if (count === 2) {
      return device === 'desktop'
        ? { id: 'UG2', cols: 3, rows: 2, count: 3, device, cells: [L(1,1,2,2), P(1,3,2,1)] }
        : { id: 'UG2', cols: 2, rows: 2, count: 3, device, cells: [P(1,1,2,1), L(1,2,1,1), L(2,2,1,1)] }
    }
    if (count === 3) {
      return device === 'desktop'
        ? { id: 'UG3', cols: 4, rows: 2, count: 4, device, cells: [P(1,1,2,1), L(1,2,2,2), P(1,4,2,1)] }
        : { id: 'UG3', cols: 2, rows: 3, count: 4, device, cells: [L(1,1,1,1), P(1,2,2,1), L(2,1,1,1), L(3,1,1,1)] }
    }
  }
  const targetRatio = device === 'desktop' ? 1.25 : 0.5
  // Mobile: force 3 cols minimum for count >= 6, rows always in pairs for portrait cells
  const minCols = (device === 'mobile' && count >= 6) ? 3 : 2
  let bestCols = minCols, bestRows = 2, bestScore = Infinity
  for (let c = minCols; c <= 10; c++) {
    let r = Math.ceil(count / c)
    if (r < 2) continue
    // Mobile: round rows up to even so portrait cells (2-row) tile cleanly
    if (device === 'mobile' && r % 2 !== 0) r++
    const waste = c * r - count
    const ratio = c / r
    const score = waste + Math.abs(ratio - targetRatio) * 5
    if (score < bestScore) { bestCols = c; bestRows = r; bestScore = score }
  }
  if (bestRows < 2) { bestRows = 2; bestCols = Math.max(minCols, Math.ceil(count / 2)) }
  const cells: BentoCell[] = []
  const grid: boolean[][] = Array.from({ length: bestRows }, () => Array(bestCols).fill(false))
  const totalSlots = bestCols * bestRows
  const portraitTarget = Math.max(1, Math.floor(totalSlots * 0.2))
  let portraitCount = 0
  const interval = Math.floor(totalSlots / (portraitTarget + 1))
  let slot = 0
  for (let r = 0; r < bestRows; r++) {
    for (let c = 0; c < bestCols; c++) {
      if (grid[r][c]) continue
      slot++
      const wantPortrait = portraitCount < portraitTarget && slot % interval === 0
        && r + 1 < bestRows && !grid[r + 1][c]
      if (wantPortrait) {
        grid[r][c] = true
        grid[r + 1][c] = true
        cells.push(P(r + 1, c + 1, 2, 1))
        portraitCount++
      } else {
        grid[r][c] = true
        cells.push(L(r + 1, c + 1, 1, 1))
      }
    }
  }
  return { id: `UG${cells.length}`, cols: bestCols, rows: bestRows, count: cells.length, device, cells }
}

/** Uniform grid — all tiles identical size (1×1 landscape cells). */
export function uniformSameRatioGrid(count: number, device: 'desktop' | 'mobile'): BentoLayout {
  if (count <= 0) count = 1
  const minCols = device === 'desktop' ? 2 : 1
  const maxRows = device === 'desktop' ? 8 : 10
  let bestCols = minCols, bestRows = 1, bestScore = Infinity
  for (let c = minCols; c <= 10; c++) {
    const r = Math.ceil(count / c)
    if (r > maxRows) continue
    const waste = c * r - count
    const ratio = (c * BENTO_UNIT_RATIO) / r
    const targetRatio = device === 'desktop' ? 1.6 : 0.7
    const score = waste * 2 + Math.abs(ratio - targetRatio) * 5
    if (score < bestScore) { bestCols = c; bestRows = r; bestScore = score }
  }
  let perfectCols = 0, perfectRows = 0, perfectScore = Infinity
  for (let c = minCols; c <= 10; c++) {
    if (count % c !== 0) continue
    const r = count / c
    if (r > maxRows || r < 1) continue
    const ratio = (c * BENTO_UNIT_RATIO) / r
    const targetRatio = device === 'desktop' ? 1.6 : 0.7
    const score = Math.abs(ratio - targetRatio) * 5
    if (score < perfectScore) { perfectCols = c; perfectRows = r; perfectScore = score }
  }
  if (perfectCols > 0) { bestCols = perfectCols; bestRows = perfectRows }
  const gridCount = bestCols * bestRows
  const cells: BentoCell[] = []
  for (let i = 0; i < gridCount; i++) {
    const r = Math.floor(i / bestCols) + 1
    const c = (i % bestCols) + 1
    cells.push(L(r, c, 1, 1))
  }
  return { id: `SG${gridCount}`, cols: bestCols, rows: bestRows, count: gridCount, device, cells }
}

/** Pick a layout for the target count. When requireMixed is true,
 *  filters out all-same-size layouts (fixes the bento bug where
 *  DS3/DS4/DS6/MS3/MS4/MS6 produced boring same-size grids).
 *  Small counts (≤4) skip the mixed-size check — same-size is fine there. */
export function pickLayoutForCount(
  targetCount: number,
  device: 'desktop' | 'mobile',
  requireMixed = false,
): BentoLayout {
  const layouts = device === 'desktop' ? DESKTOP_LAYOUTS : MOBILE_LAYOUTS
  // Only require mixed sizes for counts > 4 (small counts are fine same-size)
  const needMixed = requireMixed && targetCount > 4

  // 1. Try exact match first
  let exact = layouts.filter(l => l.device === device && l.count === targetCount)
  if (needMixed) exact = exact.filter(hasMixedSizes)
  if (exact.length > 0) return randomFrom(exact)

  // 2. Try close matches within tolerance
  const tolerance = Math.max(2, Math.ceil(targetCount * 0.3))
  let close = layouts.filter(l => l.device === device && Math.abs(l.count - targetCount) <= tolerance && l.count !== targetCount)
  if (needMixed) close = close.filter(hasMixedSizes)
  if (close.length > 0) {
    // Prefer closest count
    close.sort((a, b) => Math.abs(a.count - targetCount) - Math.abs(b.count - targetCount))
    const bestDist = Math.abs(close[0].count - targetCount)
    const bestMatches = close.filter(l => Math.abs(l.count - targetCount) === bestDist)
    return randomFrom(bestMatches)
  }

  // 3. Fallback to dynamic bento grid (always has mixed sizes)
  return uniformBentoGrid(targetCount, device)
}

/* ===== Valid density computation ===== */

export type DisplayMode = 'bento' | 'uniform'

/** Returns only the density values where a beautiful layout exists.
 *  Capped at photoCount. */
export function computeValidDensities(
  displayMode: DisplayMode,
  device: 'desktop' | 'mobile',
  photoCount: number,
): number[] {
  if (displayMode === 'uniform') {
    // Counts that tile perfectly with zero waste (min 2 — bento is about combination)
    const valid = [2, 3, 4, 6, 8, 9, 12, 16, 20, 25, 36, 48, 64]
    return valid.filter(n => n <= photoCount)
  }

  // Bento mode: find counts where at least one mixed-size layout exists
  const layouts = device === 'desktop' ? DESKTOP_LAYOUTS : MOBILE_LAYOUTS
  const mixedCounts = new Set<number>()
  for (const l of layouts) {
    if (hasMixedSizes(l)) mixedCounts.add(l.count)
  }
  if (device === 'desktop') {
    // Desktop: dynamic layouts at larger counts
    for (const n of [4, 6, 8, 10, 12, 16, 20, 24, 36, 48, 64]) {
      mixedCounts.add(n)
    }
  } else {
    // Mobile: cap at 9 — more than that is too dense for a phone screen
    for (const n of [4, 5, 6, 7, 8, 9]) {
      mixedCounts.add(n)
    }
  }
  // Include 2 (pair always works)
  mixedCounts.add(2)

  const result = [...mixedCounts].filter(n => n <= photoCount).sort((a, b) => a - b)
  return result
}

/* ===== Split helpers ===== */

/** Returns true if a cell spans more than 1×1 (can be split into smaller tiles) */
export function isSplittable(cell: BentoCell): boolean {
  return cell.rs > 1 || cell.cs > 1
}

/** Predefined split patterns for each cell shape.
 *  Each pattern is a function (r, c) → BentoCell[] that fills the same rectangle
 *  with interesting sub-layouts instead of boring all-1×1 grids. */
type SplitPattern = (r: number, c: number) => BentoCell[]

const SPLIT_PATTERNS: Record<string, SplitPattern[]> = {
  // 2×2 → 3 or 4 children (never all 1×1)
  '2x2': [
    (r, c) => [L(r, c, 1, 2), L(r+1, c, 1, 1), L(r+1, c+1, 1, 1)],    // wide top + 2 squares
    (r, c) => [L(r, c, 1, 1), L(r, c+1, 1, 1), L(r+1, c, 1, 2)],       // 2 squares + wide bottom
    (r, c) => [P(r, c, 2, 1), L(r, c+1, 1, 1), L(r+1, c+1, 1, 1)],     // portrait left + 2 squares
    (r, c) => [L(r, c, 1, 1), P(r, c+1, 2, 1), L(r+1, c, 1, 1)],       // square + portrait right + square
  ],
  // 2×3 → 2 or 3 children
  '2x3': [
    (r, c) => [L(r, c, 2, 2), P(r, c+2, 2, 1)],                          // big square + portrait
    (r, c) => [P(r, c, 2, 1), L(r, c+1, 2, 2)],                          // portrait + big square
    (r, c) => [L(r, c, 1, 2), P(r, c+2, 2, 1), L(r+1, c, 1, 2)],       // 2 wide + portrait
    (r, c) => [L(r, c, 1, 3), L(r+1, c, 1, 1), L(r+1, c+1, 1, 2)],     // banner top + square + wide bottom
  ],
  // 2×1 → 2 children (only option)
  '2x1': [
    (r, c) => [L(r, c, 1, 1), L(r+1, c, 1, 1)],
  ],
  // 1×2 → 2 children (only option)
  '1x2': [
    (r, c) => [L(r, c, 1, 1), L(r, c+1, 1, 1)],
  ],
  // 1×3 → 2 or 3 children
  '1x3': [
    (r, c) => [L(r, c, 1, 2), L(r, c+2, 1, 1)],                          // wide + square
    (r, c) => [L(r, c, 1, 1), L(r, c+1, 1, 2)],                          // square + wide
  ],
  // 4×1 → 2 children
  '4x1': [
    (r, c) => [P(r, c, 2, 1), P(r+2, c, 2, 1)],                          // 2 portraits stacked
  ],
  // 2×2 (square) already covered above
  // 2×4, 3×2, etc — generic fallback
}

/** Split a multi-span cell into interesting sub-cells (not just 1×1).
 *  Returns a new cells array with the target cell replaced by its children.
 *  The first child occupies the original top-left position (keeps the original photo). */
export function splitCell(cells: BentoCell[], index: number): BentoCell[] {
  const cell = cells[index]
  if (!cell || !isSplittable(cell)) return cells

  const key = `${cell.rs}x${cell.cs}`
  const patterns = SPLIT_PATTERNS[key]

  let children: BentoCell[]
  if (patterns && patterns.length > 0) {
    const pattern = randomFrom(patterns)
    children = pattern(cell.r, cell.c)
  } else {
    // Generic fallback: split into halves (never all 1×1 for large cells)
    children = genericSplit(cell)
  }

  const result = [...cells]
  result.splice(index, 1, ...children)
  return result
}

/** Generic fallback split — halves the cell along its longer dimension */
function genericSplit(cell: BentoCell): BentoCell[] {
  const { r, c, rs, cs } = cell
  if (rs >= cs && rs >= 2) {
    // Split horizontally
    const topH = Math.ceil(rs / 2)
    const botH = rs - topH
    return [
      L(r, c, topH, cs),
      L(r + topH, c, botH, cs),
    ]
  } else if (cs >= 2) {
    // Split vertically
    const leftW = Math.ceil(cs / 2)
    const rightW = cs - leftW
    return [
      L(r, c, rs, leftW),
      L(r, c + leftW, rs, rightW),
    ]
  }
  return [L(r, c, 1, 1)]
}

/* ===== Starter layouts — low density, big splittable tiles ===== */

/** Desktop starter layouts (5×4 grid, 4-7 big tiles) — variety is king */
export const DESKTOP_STARTER_LAYOUTS: BentoLayout[] = [
  /* DST1: 6 tiles — hero + portrait + square top; square + portrait + wide bottom */
  {
    id: 'DST1', cols: 5, rows: 4, count: 6, device: 'desktop',
    cells: [
      L(1, 1, 2, 3), P(1, 4, 2, 1), L(1, 5, 2, 1),
      L(3, 1, 2, 2), P(3, 3, 2, 1), L(3, 4, 2, 2),
    ],
  },
  /* DST2: 5 tiles — 2 wide top + 3 bottom */
  {
    id: 'DST2', cols: 5, rows: 4, count: 5, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), L(1, 3, 2, 3),
      L(3, 1, 2, 2), P(3, 3, 2, 1), L(3, 4, 2, 2),
    ],
  },
  /* DST3: 6 tiles — 3 pairs of 2×2 and portraits */
  {
    id: 'DST3', cols: 5, rows: 4, count: 6, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1), L(1, 4, 2, 2),
      P(3, 1, 2, 1), L(3, 2, 2, 2), L(3, 4, 2, 2),
    ],
  },
  /* DST4: 5 tiles — massive hero + full-height portrait + 2 stacked + wide bottom */
  {
    id: 'DST4', cols: 5, rows: 4, count: 5, device: 'desktop',
    cells: [
      L(1, 1, 2, 3), P(1, 4, 4, 1), L(1, 5, 2, 1),
      L(3, 1, 2, 3),                  L(3, 5, 2, 1),
    ],
  },
  /* DST5: 4 tiles — 2 massive blocks top + 2 massive blocks bottom (dramatic) */
  {
    id: 'DST5', cols: 5, rows: 4, count: 4, device: 'desktop',
    cells: [
      L(1, 1, 2, 3), L(1, 4, 2, 2),
      L(3, 1, 2, 2), L(3, 3, 2, 3),
    ],
  },
  /* DST6: 6 tiles — tall portrait anchor left, 4 blocks right */
  {
    id: 'DST6', cols: 5, rows: 4, count: 6, device: 'desktop',
    cells: [
      P(1, 1, 4, 1), L(1, 2, 2, 2), L(1, 4, 2, 2),
                      L(3, 2, 2, 2), L(3, 4, 2, 2),
    ],
  },
  /* DST7: 5 tiles — wide top, portrait + wide bottom */
  {
    id: 'DST7', cols: 5, rows: 4, count: 5, device: 'desktop',
    cells: [
      L(1, 1, 2, 3), L(1, 4, 2, 2),
      L(3, 1, 2, 2), P(3, 3, 2, 1), L(3, 4, 2, 2),
    ],
  },
  /* DST8: 6 tiles — alternating wide/narrow columns */
  {
    id: 'DST8', cols: 5, rows: 4, count: 6, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1), L(1, 4, 2, 2),
      L(3, 1, 2, 3),                  L(3, 4, 2, 2),
    ],
  },
  /* DST9: 4 tiles — bold quadrants */
  {
    id: 'DST9', cols: 5, rows: 4, count: 4, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), L(1, 3, 2, 3),
      L(3, 1, 2, 3), L(3, 4, 2, 2),
    ],
  },
  /* DST10: 7 tiles — dense top, open bottom */
  {
    id: 'DST10', cols: 5, rows: 4, count: 7, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1), P(1, 4, 2, 1), L(1, 5, 2, 1),
      L(3, 1, 2, 2),                  L(3, 3, 2, 3),
    ],
  },
]

/** Mobile starter layouts — reuse M1-M5 (all have large splittable cells) */
export const MOBILE_STARTER_LAYOUTS: BentoLayout[] = [
  MOBILE_LAYOUTS[0], // M1: 5 tiles
  MOBILE_LAYOUTS[1], // M2: 4 tiles
  MOBILE_LAYOUTS[2], // M3: 5 tiles
  MOBILE_LAYOUTS[4], // M5: 5 tiles
]

/* ===== Image type filter ===== */

export type ImageTypeFilter = 'photo' | 'mixed' | 'generated'

/** Filter photos by image type: originals, AI variants, or both. */
export function filterByImageType(photos: Photo[], filter: ImageTypeFilter): Photo[] {
  if (filter === 'mixed') return photos
  if (filter === 'photo') return photos.filter(p => !p.parent)
  // 'generated' — only AI variants
  return photos.filter(p => !!p.parent)
}
