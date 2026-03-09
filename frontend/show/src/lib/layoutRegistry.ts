/**
 * layoutRegistry.ts — Shared layout definitions for Bento and other fixed-screen views.
 *
 * Finite-ratio system: UNIT_RATIO = 1 (square units).
 * Desktop: 5×3 grid (15 units). Mobile: 3×6 grid (18 units).
 * Only 7 allowed ratios: 1/2, 2/3, 3/4, 1, 4/3, 3/2, 2/1.
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

/** Portrait cell (ratio < 1: rs > cs) */
function P(r: number, c: number, rs: number, cs: number): BentoCell {
  return { r, c, rs, cs, orient: 'P' }
}

/** Landscape/square cell (ratio >= 1: cs >= rs) */
function L(r: number, c: number, rs: number, cs: number): BentoCell {
  return { r, c, rs, cs, orient: 'L' }
}

/* ── Desktop layouts (5×3 grid, 15 units, 3–11 images) ── */

export const DESKTOP_LAYOUTS: BentoLayout[] = [
  /* D1: Hero — big 3:2 top-left, portrait, strip bottom — 8 tiles */
  {
    id: 'D1', cols: 5, rows: 3, count: 8, device: 'desktop',
    cells: [
      L(1, 1, 2, 3), P(1, 4, 2, 1), L(1, 5, 1, 1),
      L(2, 5, 1, 1),
      L(3, 1, 1, 1), L(3, 2, 1, 2), L(3, 4, 1, 1), L(3, 5, 1, 1),
    ],
  },
  /* D2: Balanced — two squares + portrait top, wides bottom — 6 tiles */
  {
    id: 'D2', cols: 5, rows: 3, count: 6, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1), L(1, 4, 2, 2),
      L(3, 1, 1, 2), L(3, 3, 1, 1), L(3, 4, 1, 2),
    ],
  },
  /* D3: Gallery — portrait anchor left, mixed right — 9 tiles */
  {
    id: 'D3', cols: 5, rows: 3, count: 9, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 2, 2), L(1, 4, 1, 2),
      P(2, 4, 2, 1), L(2, 5, 1, 1),
      L(3, 1, 1, 1), L(3, 2, 1, 1), L(3, 3, 1, 1), L(3, 5, 1, 1),
    ],
  },
  /* D4: Bold — two big blocks top, wide strip bottom — 5 tiles */
  {
    id: 'D4', cols: 5, rows: 3, count: 5, device: 'desktop',
    cells: [
      L(1, 1, 2, 3), L(1, 4, 2, 2),
      L(3, 1, 1, 2), L(3, 3, 1, 2), L(3, 5, 1, 1),
    ],
  },
  /* D5: Portrait wall — alternating portraits + squares — 10 tiles */
  {
    id: 'D5', cols: 5, rows: 3, count: 10, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 1, 1), P(1, 3, 2, 1), L(1, 4, 1, 1), P(1, 5, 2, 1),
      L(2, 2, 1, 1), L(2, 4, 1, 1),
      L(3, 1, 1, 2), L(3, 3, 1, 1), L(3, 4, 1, 2),
    ],
  },
  /* D6: Showcase — square + wide 3:2 top, strip bottom — 6 tiles */
  {
    id: 'D6', cols: 5, rows: 3, count: 6, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), L(1, 3, 2, 3),
      L(3, 1, 1, 1), L(3, 2, 1, 1), L(3, 3, 1, 2), L(3, 5, 1, 1),
    ],
  },
  /* D7: Mosaic — many small tiles, visual complexity — 11 tiles */
  {
    id: 'D7', cols: 5, rows: 3, count: 11, device: 'desktop',
    cells: [
      L(1, 1, 1, 2), P(1, 3, 2, 1), L(1, 4, 1, 1), L(1, 5, 1, 1),
      L(2, 1, 1, 1), L(2, 2, 1, 1), L(2, 4, 1, 2),
      L(3, 1, 1, 1), L(3, 2, 1, 1), L(3, 3, 1, 1), L(3, 4, 1, 2),
    ],
  },
  /* D8: Cinema — massive 3×3 square hero — 5 tiles */
  {
    id: 'D8', cols: 5, rows: 3, count: 5, device: 'desktop',
    cells: [
      L(1, 1, 3, 3), P(1, 4, 2, 1), L(1, 5, 1, 1),
      L(2, 5, 1, 1),
      L(3, 4, 1, 2),
    ],
  },
  /* D9: Asymmetric — 3:2 hero + portrait + varied bottom — 7 tiles */
  {
    id: 'D9', cols: 5, rows: 3, count: 7, device: 'desktop',
    cells: [
      L(1, 1, 2, 3), P(1, 4, 2, 1), L(1, 5, 1, 1),
      L(2, 5, 1, 1),
      L(3, 1, 1, 2), L(3, 3, 1, 1), L(3, 4, 1, 2),
    ],
  },
  /* D10: Widescreen — massive 4:3 hero + side column — 3 tiles */
  {
    id: 'D10', cols: 5, rows: 3, count: 3, device: 'desktop',
    cells: [
      L(1, 1, 3, 4), P(1, 5, 2, 1), L(3, 5, 1, 1),
    ],
  },
  /* D11: Diptych — big hero + portrait sidebar — 2 tiles, MIXED */
  {
    id: 'D11', cols: 4, rows: 2, count: 2, device: 'desktop',
    cells: [L(1, 1, 2, 3), P(1, 4, 2, 1)],
  },
  /* D12: Diptych reversed — portrait + hero — 2 tiles, MIXED */
  {
    id: 'D12', cols: 4, rows: 2, count: 2, device: 'desktop',
    cells: [P(1, 1, 2, 1), L(1, 2, 2, 3)],
  },
  /* D13: Asymmetric quad — hero + 3 smalls — 4 tiles, MIXED */
  {
    id: 'D13', cols: 4, rows: 2, count: 4, device: 'desktop',
    cells: [L(1, 1, 2, 2), L(1, 3, 1, 1), L(1, 4, 1, 1), L(2, 3, 1, 2)],
  },
  /* D14: Feature quad — portrait + wide + 2 squares — 4 tiles, MIXED */
  {
    id: 'D14', cols: 4, rows: 2, count: 4, device: 'desktop',
    cells: [P(1, 1, 2, 1), L(1, 2, 2, 2), L(1, 4, 1, 1), L(2, 4, 1, 1)],
  },
  /* DS1: Solo */
  { id: 'DS1', cols: 1, rows: 1, count: 1, device: 'desktop', cells: [L(1,1,1,1)] },
  /* DS2: Pair */
  { id: 'DS2', cols: 2, rows: 1, count: 2, device: 'desktop', cells: [L(1,1,1,1), L(1,2,1,1)] },
  /* DS3: Trio — ALL SAME SIZE */
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

/* ── Mobile layouts (3×6 grid, 18 units, 5–8 images) ── */

export const MOBILE_LAYOUTS: BentoLayout[] = [
  /* M1: Blocks — alternating sq+portrait rows — 6 tiles */
  {
    id: 'M1', cols: 3, rows: 6, count: 6, device: 'mobile',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1),
      P(3, 1, 2, 1), L(3, 2, 2, 2),
      L(5, 1, 2, 2), P(5, 3, 2, 1),
    ],
  },
  /* M2: Zigzag — portrait+sq alternating — 6 tiles */
  {
    id: 'M2', cols: 3, rows: 6, count: 6, device: 'mobile',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 2, 2),
      L(3, 1, 2, 2), P(3, 3, 2, 1),
      P(5, 1, 2, 1), L(5, 2, 2, 2),
    ],
  },
  /* M3: Mixed — sq+p, 3 portraits, p+sq — 7 tiles */
  {
    id: 'M3', cols: 3, rows: 6, count: 7, device: 'mobile',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1),
      P(3, 1, 2, 1), P(3, 2, 2, 1), P(3, 3, 2, 1),
      P(5, 1, 2, 1), L(5, 2, 2, 2),
    ],
  },
  /* M4: Rhythm — sq+p, p+singles+p, sq+p — 8 tiles */
  {
    id: 'M4', cols: 3, rows: 6, count: 8, device: 'mobile',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1),
      P(3, 1, 2, 1), L(3, 2, 1, 1), P(3, 3, 2, 1),
      L(4, 2, 1, 1),
      L(5, 1, 2, 2), P(5, 3, 2, 1),
    ],
  },
  /* M5: Drama — full-width 3:2 top, blocks below — 5 tiles */
  {
    id: 'M5', cols: 3, rows: 6, count: 5, device: 'mobile',
    cells: [
      L(1, 1, 2, 3),
      P(3, 1, 2, 1), L(3, 2, 2, 2),
      L(5, 1, 2, 2), P(5, 3, 2, 1),
    ],
  },
  /* M6: Feature — tall 2:3 portrait left, stack right, landscape bottom — 7 tiles */
  {
    id: 'M6', cols: 3, rows: 6, count: 7, device: 'mobile',
    cells: [
      P(1, 1, 3, 2), P(1, 3, 2, 1),
      L(3, 3, 1, 1),
      L(4, 1, 2, 2), P(4, 3, 2, 1),
      L(6, 1, 1, 2), L(6, 3, 1, 1),
    ],
  },
  /* M7: Portrait trio + alternating blocks — 7 tiles */
  {
    id: 'M7', cols: 3, rows: 6, count: 7, device: 'mobile',
    cells: [
      P(1, 1, 2, 1), P(1, 2, 2, 1), P(1, 3, 2, 1),
      L(3, 1, 2, 2), P(3, 3, 2, 1),
      P(5, 1, 2, 1), L(5, 2, 2, 2),
    ],
  },
  /* M8: Diptych — full-width hero + portrait pair — 2 tiles, MIXED */
  {
    id: 'M8', cols: 3, rows: 4, count: 2, device: 'mobile',
    cells: [L(1, 1, 2, 3), P(3, 1, 2, 3)],
  },
  /* M9: Triptych — full-width hero + two squares — 3 tiles, MIXED */
  {
    id: 'M9', cols: 2, rows: 4, count: 3, device: 'mobile',
    cells: [L(1, 1, 2, 2), L(3, 1, 2, 1), L(3, 2, 2, 1)],
  },
  /* M10: Portrait + landscape pair — 3 tiles, MIXED */
  {
    id: 'M10', cols: 3, rows: 4, count: 3, device: 'mobile',
    cells: [P(1, 1, 2, 1), L(1, 2, 2, 2), L(3, 1, 2, 3)],
  },
  /* M11: Asymmetric quad — big hero + 3 smalls — 4 tiles, MIXED */
  {
    id: 'M11', cols: 3, rows: 4, count: 4, device: 'mobile',
    cells: [L(1, 1, 2, 3), P(3, 1, 2, 1), L(3, 2, 1, 2), L(4, 2, 1, 2)],
  },
  /* M12: Feature quad — portrait left + 3 right — 4 tiles, MIXED */
  {
    id: 'M12', cols: 3, rows: 4, count: 4, device: 'mobile',
    cells: [P(1, 1, 4, 1), L(1, 2, 2, 2), L(3, 2, 1, 2), L(4, 2, 1, 2)],
  },
  /* MS1: Solo */
  { id: 'MS1', cols: 1, rows: 1, count: 1, device: 'mobile', cells: [L(1,1,1,1)] },
  /* MS2: Stack */
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
 *  All children must produce allowed ratios.
 *  Each pattern is a function (r, c) → BentoCell[] */
type SplitPattern = (r: number, c: number) => BentoCell[]

const SPLIT_PATTERNS: Record<string, SplitPattern[]> = {
  // 2×2 (ratio 1) → children with allowed ratios
  '2x2': [
    (r, c) => [L(r, c, 1, 1), L(r, c+1, 1, 1), L(r+1, c, 1, 1), L(r+1, c+1, 1, 1)],  // 4 squares
    (r, c) => [P(r, c, 2, 1), P(r, c+1, 2, 1)],                                          // 2 portraits (1/2)
    (r, c) => [L(r, c, 1, 2), L(r+1, c, 1, 2)],                                          // 2 wides (2/1)
  ],
  // 2×3 (ratio 3/2) → children
  '2x3': [
    (r, c) => [L(r, c, 2, 2), P(r, c+2, 2, 1)],     // square + portrait
    (r, c) => [P(r, c, 2, 1), L(r, c+1, 2, 2)],      // portrait + square
  ],
  // 3×2 (ratio 2/3) → children
  '3x2': [
    (r, c) => [L(r, c, 2, 2), L(r+2, c, 1, 2)],      // square + wide
    (r, c) => [L(r, c, 1, 2), L(r+1, c, 2, 2)],       // wide + square
  ],
  // 2×1 (ratio 1/2) → 2 squares
  '2x1': [
    (r, c) => [L(r, c, 1, 1), L(r+1, c, 1, 1)],
  ],
  // 1×2 (ratio 2/1) → 2 squares
  '1x2': [
    (r, c) => [L(r, c, 1, 1), L(r, c+1, 1, 1)],
  ],
  // 3×3 (ratio 1) → children
  '3x3': [
    (r, c) => [L(r, c, 2, 2), P(r, c+2, 2, 1), L(r+2, c, 1, 2), L(r+2, c+2, 1, 1)],  // sq + portrait + wide + sq
    (r, c) => [L(r, c, 2, 3), L(r+2, c, 1, 2), L(r+2, c+2, 1, 1)],                      // 3:2 + wide + sq
    (r, c) => [P(r, c, 3, 2), L(r, c+2, 1, 1), L(r+1, c+2, 1, 1), L(r+2, c+2, 1, 1)], // 2:3 portrait + 3 squares
  ],
  // 3×4 (ratio 4/3) → children
  '3x4': [
    (r, c) => [P(r, c, 3, 2), P(r, c+2, 3, 2)],                                          // two 2:3 portraits
    (r, c) => [L(r, c, 2, 2), L(r, c+2, 2, 2), L(r+2, c, 1, 2), L(r+2, c+2, 1, 2)],   // 2 squares + 2 wides
  ],
  // 4×3 (ratio 3/4) → children
  '4x3': [
    (r, c) => [L(r, c, 2, 3), L(r+2, c, 2, 3)],                                          // two 3:2 landscapes
  ],
}

/** Split a multi-span cell into interesting sub-cells.
 *  All children use allowed ratios.
 *  Returns a new cells array with the target cell replaced by its children. */
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
    // Generic fallback: split into halves
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

/** Desktop starter layouts (5×3 grid, 3-8 big tiles) */
export const DESKTOP_STARTER_LAYOUTS: BentoLayout[] = [
  /* DST1: sq + wide 3:2, strip bottom — 5 tiles */
  {
    id: 'DST1', cols: 5, rows: 3, count: 5, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), L(1, 3, 2, 3),
      L(3, 1, 1, 2), L(3, 3, 1, 2), L(3, 5, 1, 1),
    ],
  },
  /* DST2: wide 3:2 + sq, strip bottom — 5 tiles */
  {
    id: 'DST2', cols: 5, rows: 3, count: 5, device: 'desktop',
    cells: [
      L(1, 1, 2, 3), L(1, 4, 2, 2),
      L(3, 1, 1, 2), L(3, 3, 1, 2), L(3, 5, 1, 1),
    ],
  },
  /* DST3: massive 3×3 square hero, side column — 5 tiles */
  {
    id: 'DST3', cols: 5, rows: 3, count: 5, device: 'desktop',
    cells: [
      L(1, 1, 3, 3), P(1, 4, 2, 1), L(1, 5, 1, 1),
      L(2, 5, 1, 1),
      L(3, 4, 1, 2),
    ],
  },
  /* DST4: sq + portrait + sq, strip bottom — 6 tiles */
  {
    id: 'DST4', cols: 5, rows: 3, count: 6, device: 'desktop',
    cells: [
      L(1, 1, 2, 2), P(1, 3, 2, 1), L(1, 4, 2, 2),
      L(3, 1, 1, 2), L(3, 3, 1, 2), L(3, 5, 1, 1),
    ],
  },
  /* DST5: 4:3 hero + side portrait + square — 3 tiles */
  {
    id: 'DST5', cols: 5, rows: 3, count: 3, device: 'desktop',
    cells: [
      L(1, 1, 3, 4), P(1, 5, 2, 1), L(3, 5, 1, 1),
    ],
  },
  /* DST6: portraits + square top, wides bottom — 8 tiles */
  {
    id: 'DST6', cols: 5, rows: 3, count: 8, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), L(1, 2, 2, 2), P(1, 4, 2, 1),
      L(1, 5, 1, 1), L(2, 5, 1, 1),
      L(3, 1, 1, 2), L(3, 3, 1, 2), L(3, 5, 1, 1),
    ],
  },
]

/** Mobile starter layouts (3×6 grid, big splittable tiles) */
export const MOBILE_STARTER_LAYOUTS: BentoLayout[] = [
  MOBILE_LAYOUTS[0], // M1: 6 tiles — blocks
  MOBILE_LAYOUTS[1], // M2: 6 tiles — zigzag
  MOBILE_LAYOUTS[4], // M5: 5 tiles — drama
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
