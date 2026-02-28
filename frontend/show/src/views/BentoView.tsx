import { useState, useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { getObjectPosition, BENTO_UNIT_RATIO } from '../lib/cropUtils'
import { randomFrom } from '../lib/utils'
import { fireAndForget } from '../lib/firebase'
import { ViewBottom } from '../components/ui/ViewBottom'
import type { Photo } from '../types/photo'
import type { BentoCell } from '../lib/cropUtils'
import './BentoView.css'

/* ===== Layout definitions ===== */

interface BentoLayout {
  id: string
  cols: number
  rows: number
  count: number
  cells: BentoCell[]
  device: 'desktop' | 'mobile'
}

/** Portrait cell (1 col × 2 rows → ratio 0.667 with 4:3 unit) */
function P(r: number, c: number, rs: number, cs: number): BentoCell {
  return { r, c, rs, cs, orient: 'P' }
}

/** Landscape cell (1×1 → ratio 1.333, or 2×2 → ratio 1.333) */
function L(r: number, c: number, rs: number, cs: number): BentoCell {
  return { r, c, rs, cs, orient: 'L' }
}

/*
 * Layout system uses 4:3 unit ratio (BENTO_UNIT_RATIO = 4/3).
 * Cell aspect ratios:
 *   L 1×1 = 1.333 (≈3:2 landscape, 11% off — barely crops)
 *   P 1×2 = 0.667 (= 2:3 portrait, perfect match)
 *   L 2×2 = 1.333 (large landscape, same ratio)
 * Container ratio = cols × UNIT_RATIO / rows
 */

/* ── Desktop layouts (5×4 grid, ratio ≈ 1.667, 8–11 images) ── */

const DESKTOP_LAYOUTS: BentoLayout[] = [
  /* D1: Balanced — 5×4, 8 images, 3P 5L */
  {
    id: 'D1', cols: 5, rows: 4, count: 8, device: 'desktop',
    cells: [
      L(1, 1, 2, 2),  // large landscape top-left
      P(1, 3, 2, 1),  // portrait center
      L(1, 4, 2, 2),  // large landscape top-right
      P(3, 1, 2, 1),  // portrait bottom-left
      L(3, 2, 2, 2),  // large landscape center
      P(3, 4, 2, 1),  // portrait bottom-right
      L(3, 5, 1, 1),  // landscape
      L(4, 5, 1, 1),  // landscape
    ],
  },
  /* D2: Gallery — 5×4, 11 images, 3P 8L */
  {
    id: 'D2', cols: 5, rows: 4, count: 11, device: 'desktop',
    cells: [
      P(1, 1, 2, 1),  // portrait left
      L(1, 2, 2, 2),  // large landscape top-center
      L(1, 4, 1, 1),  // landscape
      P(1, 5, 2, 1),  // portrait right
      L(2, 4, 1, 1),  // landscape
      L(3, 1, 2, 2),  // large landscape bottom-left
      P(3, 3, 2, 1),  // portrait center
      L(3, 4, 1, 1),  // landscape
      L(3, 5, 1, 1),  // landscape
      L(4, 4, 1, 1),  // landscape
      L(4, 5, 1, 1),  // landscape
    ],
  },
  /* D3: Columns — 5×4, 11 images, 3P 8L */
  {
    id: 'D3', cols: 5, rows: 4, count: 11, device: 'desktop',
    cells: [
      P(1, 1, 2, 1),  // portrait col1 top
      L(1, 2, 2, 2),  // large landscape top-center
      P(1, 4, 2, 1),  // portrait col4 top
      L(1, 5, 1, 1),  // landscape top-right
      L(2, 5, 1, 1),  // landscape mid-right
      P(3, 1, 2, 1),  // portrait col1 bottom
      L(3, 2, 1, 1),  // landscape
      L(3, 3, 1, 1),  // landscape
      L(3, 4, 2, 2),  // large landscape bottom-right
      L(4, 2, 1, 1),  // landscape
      L(4, 3, 1, 1),  // landscape
    ],
  },
  /* D4: Feature — 5×4, 9 images, 2P 7L */
  {
    id: 'D4', cols: 5, rows: 4, count: 9, device: 'desktop',
    cells: [
      L(1, 1, 2, 2),  // large landscape top-left
      L(1, 3, 1, 1),  // landscape
      P(1, 4, 2, 1),  // portrait
      L(1, 5, 1, 1),  // landscape
      P(2, 3, 2, 1),  // portrait mid
      L(2, 5, 1, 1),  // landscape
      L(3, 1, 2, 2),  // large landscape bottom-left
      L(3, 4, 2, 2),  // large landscape bottom-right
      L(4, 3, 1, 1),  // landscape bottom-center
    ],
  },
  /* D5: Mosaic — 5×4, 10 images, 4P 6L */
  {
    id: 'D5', cols: 5, rows: 4, count: 10, device: 'desktop',
    cells: [
      P(1, 1, 2, 1),  // portrait top-left
      L(1, 2, 2, 2),  // large landscape top-center
      P(1, 4, 2, 1),  // portrait top-right
      L(1, 5, 1, 1),  // landscape
      L(2, 5, 1, 1),  // landscape
      L(3, 1, 1, 1),  // landscape bottom-left
      P(3, 2, 2, 1),  // portrait bottom
      L(3, 3, 2, 2),  // large landscape bottom-center
      P(3, 5, 2, 1),  // portrait bottom-right
      L(4, 1, 1, 1),  // landscape
    ],
  },
  /* D6: Quilt — 5×4, 16 images, 4P 12L — no large cells */
  {
    id: 'D6', cols: 5, rows: 4, count: 16, device: 'desktop',
    cells: [
      P(1, 1, 2, 1), P(1, 2, 2, 1), L(1, 3, 1, 1), L(1, 4, 1, 1), L(1, 5, 1, 1),
                                      L(2, 3, 1, 1), L(2, 4, 1, 1), L(2, 5, 1, 1),
      L(3, 1, 1, 1), L(3, 2, 1, 1), P(3, 3, 2, 1), P(3, 4, 2, 1), L(3, 5, 1, 1),
      L(4, 1, 1, 1), L(4, 2, 1, 1),                                 L(4, 5, 1, 1),
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
  /* DS3: Trio strip */
  { id: 'DS3', cols: 3, rows: 1, count: 3, device: 'desktop', cells: [L(1,1,1,1), L(1,2,1,1), L(1,3,1,1)] },
  /* DS4: Quad — 2×2 */
  { id: 'DS4', cols: 2, rows: 2, count: 4, device: 'desktop', cells: [L(1,1,1,1), L(1,2,1,1), L(2,1,1,1), L(2,2,1,1)] },
  /* DS6: Quilt — 3×2 */
  {
    id: 'DS6', cols: 3, rows: 2, count: 6, device: 'desktop',
    cells: [L(1,1,1,1), L(1,2,1,1), L(1,3,1,1), L(2,1,1,1), L(2,2,1,1), L(2,3,1,1)],
  },
  /* DS6p: Portraits — 3×2 with 2P */
  {
    id: 'DS6p', cols: 3, rows: 2, count: 4, device: 'desktop',
    cells: [P(1,1,2,1), L(1,2,1,1), P(1,3,2,1), L(2,2,1,1)],
  },
]

/* ── Mobile layouts (3×6 grid, ratio ≈ 0.667, 8–9 images) ── */

const MOBILE_LAYOUTS: BentoLayout[] = [
  /* M1: Stack — 3×6, 9 images, 3P 6L */
  {
    id: 'M1', cols: 3, rows: 6, count: 9, device: 'mobile',
    cells: [
      L(1, 1, 2, 2),  // large landscape top-left
      P(1, 3, 2, 1),  // portrait top-right
      P(3, 1, 2, 1),  // portrait mid-left
      L(3, 2, 2, 2),  // large landscape mid-right
      L(5, 1, 1, 1),  // landscape
      P(5, 2, 2, 1),  // portrait bottom-center
      L(5, 3, 1, 1),  // landscape
      L(6, 1, 1, 1),  // landscape
      L(6, 3, 1, 1),  // landscape
    ],
  },
  /* M2: Tower — 3×6, 8 images, 4P 4L */
  {
    id: 'M2', cols: 3, rows: 6, count: 8, device: 'mobile',
    cells: [
      P(1, 1, 2, 1),  // portrait top-left
      L(1, 2, 2, 2),  // large landscape top-right
      L(3, 1, 2, 2),  // large landscape mid-left
      P(3, 3, 2, 1),  // portrait mid-right
      P(5, 1, 2, 1),  // portrait bottom-left
      L(5, 2, 1, 1),  // landscape
      P(5, 3, 2, 1),  // portrait bottom-right
      L(6, 2, 1, 1),  // landscape
    ],
  },
  /* M3: Cascade — 3×6, 9 images, 3P 6L */
  {
    id: 'M3', cols: 3, rows: 6, count: 9, device: 'mobile',
    cells: [
      L(1, 1, 1, 1),  // landscape top-left
      P(1, 2, 2, 1),  // portrait top-center
      L(1, 3, 1, 1),  // landscape top-right
      P(2, 1, 2, 1),  // portrait left
      L(2, 3, 1, 1),  // landscape
      L(3, 2, 2, 2),  // large landscape center
      P(4, 1, 2, 1),  // portrait bottom-left
      L(5, 2, 2, 2),  // large landscape bottom-right
      L(6, 1, 1, 1),  // landscape bottom-left
    ],
  },
  /* M4: Scroll — 3×6, 9 images, 3P 6L */
  {
    id: 'M4', cols: 3, rows: 6, count: 9, device: 'mobile',
    cells: [
      L(1, 1, 2, 2),  // large landscape top-left
      P(1, 3, 2, 1),  // portrait top-right
      P(3, 1, 2, 1),  // portrait mid-left
      L(3, 2, 1, 1),  // landscape
      P(3, 3, 2, 1),  // portrait mid-right
      L(4, 2, 1, 1),  // landscape
      L(5, 1, 1, 1),  // landscape
      L(5, 2, 2, 2),  // large landscape bottom-right
      L(6, 1, 1, 1),  // landscape bottom-left
    ],
  },
  /* M5: Dense — 3×6, 9 images, 3P 6L */
  {
    id: 'M5', cols: 3, rows: 6, count: 9, device: 'mobile',
    cells: [
      P(1, 1, 2, 1),  // portrait top-left
      L(1, 2, 2, 2),  // large landscape top-right
      L(3, 1, 1, 1),  // landscape
      P(3, 2, 2, 1),  // portrait mid-center
      L(3, 3, 1, 1),  // landscape
      P(4, 1, 2, 1),  // portrait mid-left
      L(4, 3, 1, 1),  // landscape
      L(5, 2, 2, 2),  // large landscape bottom-right
      L(6, 1, 1, 1),  // landscape bottom-left
    ],
  },
  /* MS1: Solo */
  { id: 'MS1', cols: 1, rows: 1, count: 1, device: 'mobile', cells: [L(1,1,1,1)] },
  /* MS2: Stack — 2 stacked */
  { id: 'MS2', cols: 1, rows: 2, count: 2, device: 'mobile', cells: [L(1,1,1,1), L(2,1,1,1)] },
  /* MS3: Triple stack */
  { id: 'MS3', cols: 1, rows: 3, count: 3, device: 'mobile', cells: [L(1,1,1,1), L(2,1,1,1), L(3,1,1,1)] },
  /* MS4: Quad — 2×2 */
  { id: 'MS4', cols: 2, rows: 2, count: 4, device: 'mobile', cells: [L(1,1,1,1), L(1,2,1,1), L(2,1,1,1), L(2,2,1,1)] },
  /* MS6: Grid — 2×3 */
  {
    id: 'MS6', cols: 2, rows: 3, count: 6, device: 'mobile',
    cells: [L(1,1,1,1), L(1,2,1,1), L(2,1,1,1), L(2,2,1,1), L(3,1,1,1), L(3,2,1,1)],
  },
]

const CROSSFADE_INTERVAL = 20_000

/* ===== Density ===== */

const BENTO_DENSITY_STEPS = [1, 2, 4, 6, 8, 12, 16, 24, 36, 48, 64]
const BENTO_DEFAULT_DENSITY_IDX = 4 // 8 images

/* ===== Color bucketing ===== */

const BENTO_NUM_BUCKETS = 24

interface BentoColorBucket {
  hueStart: number
  hueEnd: number
  color: string
  photos: Photo[]
}

function buildBentoColorBuckets(photos: Photo[]): BentoColorBucket[] {
  const bucketSize = 360 / BENTO_NUM_BUCKETS
  const buckets: BentoColorBucket[] = []
  for (let i = 0; i < BENTO_NUM_BUCKETS; i++) {
    const hueStart = i * bucketSize
    const hueMid = hueStart + bucketSize / 2
    buckets.push({ hueStart, hueEnd: hueStart + bucketSize, color: `hsl(${hueMid}, 65%, 50%)`, photos: [] })
  }
  const grayPhotos: Photo[] = []
  for (const photo of photos) {
    if (!photo.thumb) continue
    if (photo.has_border) continue
    const palette = photo.palette
    if (palette && palette.length > 0 && palette.every(hex => {
      if (!hex || hex.length < 7) return true
      const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16)
      return (Math.max(r, g, b) - Math.min(r, g, b)) < 30
    })) { grayPhotos.push(photo); continue }
    const hue = photo.hue || 0
    const idx = Math.min(Math.floor(hue / bucketSize), BENTO_NUM_BUCKETS - 1)
    buckets[idx].photos.push(photo)
  }
  if (grayPhotos.length > 0) {
    buckets.push({ hueStart: -1, hueEnd: -1, color: '#8e8e93', photos: grayPhotos })
  }
  return buckets
}

/* ===== Dynamic layout generation ===== */

function uniformBentoGrid(count: number, device: 'desktop' | 'mobile'): BentoLayout {
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
  let bestCols = 1, bestRows = 1, bestScore = Infinity
  for (let c = 2; c <= 10; c++) {
    const r = Math.ceil(count / c)
    if (r < 2) continue // need at least 2 rows for portraits
    const waste = c * r - count
    const ratio = c / r
    const score = waste + Math.abs(ratio - targetRatio) * 5
    if (score < bestScore) { bestCols = c; bestRows = r; bestScore = score }
  }
  if (bestRows < 2) { bestRows = 2; bestCols = Math.max(2, Math.ceil(count / 2)) }
  // Fill EVERY grid position — no gaps allowed.
  // First pass: place portraits every Nth cell, fill rest with landscape.
  const cells: BentoCell[] = []
  const grid: boolean[][] = Array.from({ length: bestRows }, () => Array(bestCols).fill(false))
  const totalSlots = bestCols * bestRows
  const portraitTarget = Math.max(1, Math.floor(totalSlots * 0.2)) // ~20% portraits
  let portraitCount = 0
  // Place portraits at regular intervals in the grid
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

/** Uniform grid — all tiles identical size (1×1 landscape cells). No exceptions.
 *  Desktop: min 2 cols, max 8 rows. Mobile: min 1 col, max 10 rows.  */
function uniformSameRatioGrid(count: number, device: 'desktop' | 'mobile'): BentoLayout {
  if (count <= 0) count = 1
  const minCols = device === 'desktop' ? 2 : 1
  const maxRows = device === 'desktop' ? 8 : 10
  let bestCols = minCols, bestRows = 1, bestScore = Infinity
  for (let c = minCols; c <= 10; c++) {
    const r = Math.ceil(count / c)
    if (r > maxRows) continue
    const waste = c * r - count
    const ratio = (c * BENTO_UNIT_RATIO) / r // account for 4:3 unit cells
    const targetRatio = device === 'desktop' ? 1.6 : 0.7
    const score = waste * 2 + Math.abs(ratio - targetRatio) * 5
    if (score < bestScore) { bestCols = c; bestRows = r; bestScore = score }
  }
  // Only accept grids that exactly fit count (zero waste)
  // Re-search with waste=0 constraint
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
  // Use perfect fit if found, otherwise use best (may have waste — caller must fill)
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

function pickLayoutForCount(targetCount: number, device: 'desktop' | 'mobile'): BentoLayout {
  const layouts = device === 'desktop' ? DESKTOP_LAYOUTS : MOBILE_LAYOUTS
  const tolerance = Math.max(2, Math.ceil(targetCount * 0.3))
  const matching = layouts.filter(l => l.device === device && Math.abs(l.count - targetCount) <= tolerance)
  if (matching.length > 0) return randomFrom(matching)
  return uniformBentoGrid(targetCount, device)
}

/* ===== Fullscreen SVG icon ===== */
const FullscreenIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3" />
  </svg>
)

/* ===== Device detection ===== */

function isDesktop(): boolean {
  return window.innerWidth >= window.innerHeight
}

/* ===== Photo Intelligence — derived scoring for smart layout ===== */

/** Hue distance (0-180) */
function hueDist(a: number, b: number): number {
  const d = Math.abs(a - b)
  return d > 180 ? 360 - d : d
}

/** Visual impact score — determines which photos deserve the big cells.
 *  Uses aesthetic_v2 (real spread: 16-48) instead of useless aesthetic (99% score 10/10).
 *  High score = dramatic, attention-grabbing, hero material.
 *  Low score = supporting cast, texture, atmosphere. */
function visualImpact(p: Photo): number {
  // aesthetic_v2: range ~17-48, mean ~37, std ~5. Normalize to 0-10 range.
  const av2 = (p as unknown as Record<string, unknown>).aesthetic_v2 as number | undefined
  let s = av2 != null ? ((av2 - 17) / 3.1) : ((p.aesthetic || 5) * 1.5)
  if ((p.face_count || 0) > 0) s += 3
  if ((p.contrast || 50) > 70) s += 1.5
  if ((p.depth_complexity || 0) > 3) s += 1
  if (p.saliency && p.saliency.spread < 0.3) s += 1.5
  if (p.gc_weight) s += (p.gc_weight - 5) * 0.5
  if (p.mono) s += 0.5
  if (p.gemma_sharpness === 'sharp') s += 1
  else if (p.gemma_sharpness === 'motion_blur') s += 0.3
  if (p.gemma_exposure === 'balanced') s += 0.5
  if (p.gc_energy && p.gc_energy !== 'static') s += 0.5
  return s
}

/** How well a photo's gemma crop fits a target cell aspect ratio.
 *  Higher coverage = more of the subject is visible in that crop = better fit. */
function cropFitness(p: Photo, cell: BentoCell): number {
  if (!p.gemma_crops) return 0
  const ratio = (cell.cs * BENTO_UNIT_RATIO) / cell.rs
  let key: string
  if (ratio >= 1.6) key = '16:9'
  else if (ratio >= 1.2) key = '3:2'
  else if (ratio <= 0.85) key = '2:3'
  else key = '1:1'
  const crop = p.gemma_crops[key]
  if (!crop) return 0
  // coverage 0-100: higher = subject fills the frame at this crop
  return (crop.coverage - 50) * 0.06 // ±3 points from neutral
}

/** Classify color temperature from composition data or hue analysis */
function colorWarmth(p: Photo): 'warm' | 'cool' | 'neutral' | 'mono' {
  if (p.mono) return 'mono'
  if (p.gc_temp) {
    if (p.gc_temp === 'warm' || p.gc_temp === 'molten') return 'warm'
    if (p.gc_temp === 'cool' || p.gc_temp === 'glacial') return 'cool'
    if (p.gc_temp === 'monochrome') return 'mono'
    return 'neutral'
  }
  const h = p.hue || 0
  if (h < 50 || h > 310) return 'warm'
  if (h > 160 && h < 260) return 'cool'
  return 'neutral'
}

/** Split photos into orientation pools */
function orientPools(photos: Photo[]) {
  return {
    P: photos.filter(p => p.orientation === 'portrait'),
    L: photos.filter(p => p.orientation === 'landscape' || p.orientation === 'square'),
  }
}

/**
 * Smart cell assignment — heroes to large cells, supporters to small cells.
 * This is the key insight: large cells (2×2) need visually dominant photos,
 * while small cells (1×1) work best with textures and atmospheric shots.
 */
function fillCells(
  cells: BentoCell[], pools: { P: Photo[]; L: Photo[] },
  usedIds: Set<string>, scoreFn: (p: Photo) => number,
): Photo[] {
  // Sort cells by size (large cells first) to assign heroes to big cells
  const indexedCells = cells.map((cell, i) => ({ cell, i, size: cell.rs * cell.cs }))
  const sortedCells = [...indexedCells].sort((a, b) => b.size - a.size)

  // Score photos per-cell: base score + crop fitness for this specific cell
  const result: (Photo | undefined)[] = new Array(cells.length)
  const claimed = new Set<string>()

  for (const { cell, i } of sortedCells) {
    const primary = cell.orient === 'P' ? pools.P : pools.L
    const fallback = cell.orient === 'P' ? pools.L : pools.P

    // Score candidates with crop fitness bonus for this cell
    let best: Photo | undefined
    let bestScore = -Infinity
    for (const p of primary) {
      if (usedIds.has(p.id) || claimed.has(p.id)) continue
      const s = scoreFn(p) + cropFitness(p, cell)
      if (s > bestScore) { bestScore = s; best = p }
    }
    if (!best) {
      for (const p of fallback) {
        if (usedIds.has(p.id) || claimed.has(p.id)) continue
        const s = scoreFn(p) + cropFitness(p, cell)
        if (s > bestScore) { bestScore = s; best = p }
      }
    }
    if (best) {
      result[i] = best
      claimed.add(best.id)
      usedIds.add(best.id)
    }
  }

  // Second pass: fill any remaining empty slots from ALL unclaimed photos (ignore orientation)
  const allRemaining = [...pools.P, ...pools.L]
  for (let i = 0; i < result.length; i++) {
    if (result[i]) continue
    let best: Photo | undefined
    let bestScore = -Infinity
    for (const p of allRemaining) {
      if (usedIds.has(p.id) || claimed.has(p.id)) continue
      const s = scoreFn(p)
      if (s > bestScore) { bestScore = s; best = p }
    }
    if (best) {
      result[i] = best
      claimed.add(best.id)
      usedIds.add(best.id)
    }
  }

  return result.filter(Boolean) as Photo[]
}

/* ===== Curators — each produces a themed, visually coherent bento set ===== */

/*
 * CURATOR: Hero Story — pick the strongest photo as hero, build a court around it
 * that shares mood but contrasts in weight (hero is loud, court is quieter)
 */
function curateHeroStory(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4)
  if (photos.length < cells.length) return []

  // Pick a random hero from the top 20% by visual impact
  const scored = [...photos].sort((a, b) => visualImpact(b) - visualImpact(a))
  const topN = Math.max(5, Math.floor(scored.length * 0.2))
  const hero = scored[Math.floor(Math.random() * topN)]
  const heroVibes = new Set(hero.vibes || [])
  const heroHue = hero.hue || 0

  const pools = orientPools(photos)
  const usedIds = new Set<string>()

  // Score: hero gets massive boost → lands in biggest cell.
  // Court scored by thematic fit + lower visual weight.
  return fillCells(cells, pools, usedIds, (p) => {
    if (p.id === hero.id) return 999 // guarantee hero gets the biggest cell
    let s = (p.aesthetic || 5)
    // Shared vibes = thematic coherence
    const shared = (p.vibes || []).filter(v => heroVibes.has(v)).length
    s += shared * 4
    // Color harmony: analogous or complementary
    const hd = hueDist(p.hue || 0, heroHue)
    if (hd < 40) s += 5
    else if (hd > 140) s += 3
    // Same scene / time / grading for cohesion
    if (p.scene === hero.scene && hero.scene) s += 3
    if (p.time === hero.time && hero.time) s += 2
    if (p.grading === hero.grading && hero.grading) s += 2
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Temperature Harmony — all warm OR all cool photos
 * Creates a cohesive temperature palette that feels intentional
 */
function curateTemperatureHarmony(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4)

  // Count warm vs cool
  const warm = photos.filter(p => colorWarmth(p) === 'warm')
  const cool = photos.filter(p => colorWarmth(p) === 'cool')

  // Pick the larger pool, or random if close
  let pool: Photo[]
  let temp: 'warm' | 'cool'
  if (warm.length > cool.length * 1.5) {
    pool = warm; temp = 'warm'
  } else if (cool.length > warm.length * 1.5) {
    pool = cool; temp = 'cool'
  } else {
    temp = Math.random() > 0.5 ? 'warm' : 'cool'
    pool = temp === 'warm' ? warm : cool
  }

  if (pool.length < cells.length) return []

  const pools = orientPools(pool)
  const usedIds = new Set<string>()

  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Tighter temperature = better
    if (p.gc_temp) {
      if (temp === 'warm' && (p.gc_temp === 'warm' || p.gc_temp === 'molten')) s += 3
      if (temp === 'cool' && (p.gc_temp === 'cool' || p.gc_temp === 'glacial')) s += 3
    }
    // Hue cohesion within the temperature
    const targetHue = temp === 'warm' ? 30 : 210
    s += (60 - hueDist(p.hue || 0, targetHue)) / 6
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Depth Journey — mix shallow depth (portraits, close-ups) with deep landscapes
 * Creates visual rhythm: intimate → expansive → intimate
 */
function curateDepthJourney(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4 && p.depth_complexity != null
  )
  if (photos.length < cells.length) return []

  // Shallow = faces, objects, close-up (low depth_complexity)
  // Deep = landscapes, architecture (high depth_complexity)
  const shallow = photos.filter(p => (p.depth_complexity || 0) < 3)
  const deep = photos.filter(p => (p.depth_complexity || 0) >= 3)

  if (shallow.length < 2 || deep.length < 2) return []

  // Alternate: heroes from deep (dramatic landscapes), supporters from shallow (intimate)
  const mixed = [...photos]
  const pools = orientPools(mixed)
  const usedIds = new Set<string>()

  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Deep photos get bonus for large cells (high score), shallow for small
    const dc = p.depth_complexity || 2
    s += dc * 0.5 // deep = higher score → bigger cells
    // Hue variety bonus (diverse palette)
    s += Math.random() * 8
    return s
  })
}

/*
 * CURATOR: Monochrome Accent — mostly B&W with 1-2 vivid color accents
 * The color photos pop dramatically against the monochrome backdrop
 */
function curateMonoAccent(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const monoPhotos = allPhotos.filter(p => p.thumb && p.display && !p.parent && p.mono && (p.aesthetic || 0) > 4)
  const colorPhotos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && !p.mono && (p.aesthetic || 0) > 5 &&
    (p.contrast || 50) > 60
  )

  if (monoPhotos.length < cells.length - 2 || colorPhotos.length < 1) return []

  // Pick 1-2 vivid color accent photos (high contrast, high saturation)
  const accentCount = cells.length <= 6 ? 1 : 2
  const sortedColor = [...colorPhotos].sort((a, b) => visualImpact(b) - visualImpact(a))
  const accents = sortedColor.slice(0, accentCount)

  // Fill rest with monochrome
  const mixed = [...accents, ...monoPhotos]
  const pools = orientPools(mixed)
  const usedIds = new Set<string>()

  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Color accents should land in large cells
    if (!p.mono) s += 10
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Color Story — tight hue range, coherent palette
 * Improved: better hue targeting, visual impact scoring, quality floor
 */
function curateColorStory(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && !p.mono && (p.aesthetic || 0) > 4)

  // Pick a hue that has the most photos (not random — find a good cluster)
  const hueBuckets: Photo[][] = Array.from({ length: 12 }, () => [])
  for (const p of photos) {
    const idx = Math.min(Math.floor((p.hue || 0) / 30), 11)
    hueBuckets[idx].push(p)
  }

  // Find the richest 3 consecutive buckets (90-degree range)
  let bestStart = 0, bestCount = 0
  for (let i = 0; i < 12; i++) {
    const count = hueBuckets[i].length + hueBuckets[(i + 1) % 12].length + hueBuckets[(i + 2) % 12].length
    if (count > bestCount) { bestCount = count; bestStart = i }
  }

  const targetHue = (bestStart * 30 + 45) % 360
  const inRange = photos.filter(p => hueDist(p.hue || 0, targetHue) < 45)
  if (inRange.length < cells.length) return []

  const pools = orientPools(inRange)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    s += (45 - hueDist(p.hue || 0, targetHue)) / 4 // tighter hue = better
    if (p.parent) s -= 3
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Mood Board — pick a vibe, find matching photos
 * Improved: requires 2+ shared vibes for stronger coherence,
 * uses visual impact for hero assignment
 */
function curateMoodBoard(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && !p.parent && p.vibes && p.vibes.length > 0)
  if (photos.length === 0) return []

  const vibeCounts = new Map<string, number>()
  for (const p of photos) {
    for (const v of p.vibes!) {
      vibeCounts.set(v, (vibeCounts.get(v) || 0) + 1)
    }
  }

  // Pick a vibe that has enough photos
  const goodVibes = [...vibeCounts.entries()]
    .filter(([, count]) => count >= cells.length * 1.5) // need surplus for quality
    .map(([vibe]) => vibe)
  if (goodVibes.length === 0) return []

  const targetVibe = randomFrom(goodVibes)
  const matching = photos.filter(p => p.vibes!.includes(targetVibe))

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // More shared vibes = stronger thematic fit
    const shared = p.vibes!.filter(v => vibeCounts.get(v)! >= 5).length
    s += shared * 3
    // Color cohesion within the mood
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Scene Story — photos from the same scene type
 * Improved: visual impact scoring, hue harmony within scene
 */
function curateSceneStory(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && !p.parent && p.scene)
  if (photos.length === 0) return []

  const sceneCounts = new Map<string, number>()
  for (const p of photos) {
    sceneCounts.set(p.scene!, (sceneCounts.get(p.scene!) || 0) + 1)
  }

  const goodScenes = [...sceneCounts.entries()]
    .filter(([, count]) => count >= cells.length * 1.5)
    .map(([scene]) => scene)
  if (goodScenes.length === 0) return []

  const targetScene = randomFrom(goodScenes)
  const matching = photos.filter(p => p.scene === targetScene)

  // Find the dominant hue within this scene for color harmony
  const hues = matching.map(p => p.hue || 0)
  const avgHue = hues.reduce((s, h) => s + h, 0) / hues.length

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Color harmony within scene
    s += (60 - hueDist(p.hue || 0, avgHue)) / 6
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Archetype Exhibition — group by composition archetype
 * Only fires when composition data is available
 */
function curateArchetypeExhibition(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && p.gc_archetype && (p.aesthetic || 0) > 4
  )
  if (photos.length < cells.length) return []

  const archCounts = new Map<string, number>()
  for (const p of photos) {
    archCounts.set(p.gc_archetype!, (archCounts.get(p.gc_archetype!) || 0) + 1)
  }

  const goodArchs = [...archCounts.entries()]
    .filter(([, count]) => count >= cells.length)
    .map(([arch]) => arch)
  if (goodArchs.length === 0) return []

  const targetArch = randomFrom(goodArchs)
  const matching = photos.filter(p => p.gc_archetype === targetArch)

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Within archetype, prefer diverse energy directions
    return s + Math.random() * 3
  })
}

/*
 * CURATOR: Camera Story — character of a camera body
 * Groups photos by camera model, scores by visual impact + hue diversity
 */
function curateCameraStory(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && !p.parent && p.camera && (p.aesthetic || 0) > 4)
  if (photos.length === 0) return []

  const camCounts = new Map<string, number>()
  for (const p of photos) {
    camCounts.set(p.camera!, (camCounts.get(p.camera!) || 0) + 1)
  }

  const minCount = Math.ceil(cells.length * 1.5)
  const goodCams = [...camCounts.entries()]
    .filter(([, count]) => count >= minCount)
    .map(([cam]) => cam)
  if (goodCams.length === 0) return []

  const targetCam = randomFrom(goodCams)
  const matching = photos.filter(p => p.camera === targetCam)

  const hues = matching.filter(p => p.hue != null).map(p => p.hue!)
  const avgHue = hues.length > 0 ? hues.reduce((s, h) => s + h, 0) / hues.length : 180

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Reward hue diversity — photos far from average hue add visual interest
    s += hueDist(p.hue || 0, avgHue) / 20
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Night Vision — dark & dramatic shots
 * Filters by night time or low brightness, scores by visual impact + contrast
 */
function curateNightVision(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4 &&
    (p.time === 'night' || (p.brightness != null && p.brightness < 50))
  )
  if (photos.length < cells.length) return []

  const pools = orientPools(photos)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // High contrast photos get bonus for large cells
    if ((p.contrast || 50) > 60) s += 3
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Golden Hour — warm light photography
 * Filters by golden hour time, scores by visual impact + warm hue bonus
 */
function curateGoldenHour(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4 &&
    p.time === 'golden hour'
  )
  if (photos.length < cells.length) return []

  const pools = orientPools(photos)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Warm hues (orange/yellow range) get bonus
    const h = p.hue || 0
    if (h > 15 && h < 60) s += 4
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Face Gallery — people-focused layouts
 * Filters by face_count > 0, scores by visual impact + face count (groups → large cells)
 */
function curateFaceGallery(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4 &&
    (p.face_count || 0) > 0
  )
  if (photos.length < cells.length) return []

  const pools = orientPools(photos)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // More faces → bigger cells
    s += (p.face_count || 0) * 2
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Style Contrast — film vs digital mix
 * Pools analog photos with digital (street/documentary), analog gets large-cell boost
 */
function curateStyleContrast(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const analog = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4 && p.style === 'analog'
  )
  const digital = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4 &&
    (p.style === 'street' || p.style === 'documentary')
  )

  if (analog.length < 2 || digital.length < 2) return []
  if (analog.length + digital.length < cells.length) return []

  const mixed = [...analog, ...digital]
  const pools = orientPools(mixed)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Analog photos get boost to land in large cells
    if (p.style === 'analog') s += 5
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Brightness Gradient — dark to light sweep
 * Sorts by brightness, maps brightness to cell position scoring
 */
function curateBrightnessGradient(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && (p.aesthetic || 0) > 4 && p.brightness != null
  )
  if (photos.length < cells.length) return []

  // Sort by brightness, take a spread from dark to light
  const sorted = [...photos].sort((a, b) => (a.brightness || 0) - (b.brightness || 0))
  const step = Math.max(1, Math.floor(sorted.length / (cells.length * 2)))
  const sampled = sorted.filter((_, i) => i % step === 0).slice(0, cells.length * 3)

  if (sampled.length < cells.length) return []

  const pools = orientPools(sampled)
  const usedIds = new Set<string>()

  // Score: dark photos get high scores (land in first/large cells), light photos lower
  const maxBright = Math.max(...sampled.map(p => p.brightness || 0))
  const minBright = Math.min(...sampled.map(p => p.brightness || 0))
  const range = maxBright - minBright || 1

  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Dark photos → large cells (higher score), light → small cells
    s += ((maxBright - (p.brightness || 0)) / range) * 6
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Energy Flow — group by visual energy direction
 * Creates rhythm: diagonal photos together, or static vs dynamic contrast
 */
function curateEnergyFlow(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && p.gc_energy && (p.aesthetic || 0) > 4
  )
  if (photos.length < cells.length) return []

  const energyCounts = new Map<string, number>()
  for (const p of photos) {
    energyCounts.set(p.gc_energy!, (energyCounts.get(p.gc_energy!) || 0) + 1)
  }

  // Pick a directional energy that has enough photos
  const dynamic = ['diagonal_down', 'diagonal_up', 'left_to_right', 'right_to_left', 'center_out']
  const goodEnergies = [...energyCounts.entries()]
    .filter(([e, count]) => dynamic.includes(e) && count >= cells.length)
    .map(([e]) => e)
  if (goodEnergies.length === 0) return []

  const targetEnergy = randomFrom(goodEnergies)
  const matching = photos.filter(p => p.gc_energy === targetEnergy)

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Reward photos with strong composition weight for hero cells
    if (p.gc_weight && p.gc_weight >= 7) s += 3
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Semantic Pops — group photos that share striking color-object combos
 * Uses Gemma's semantic_pops (color + object + impact tuples)
 */
function curateSemanticPops(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && p.gemma_pops && p.gemma_pops.length > 0 && (p.aesthetic || 0) > 4
  )
  if (photos.length < cells.length) return []

  // Find the most common pop colors
  const popColors = new Map<string, Photo[]>()
  for (const p of photos) {
    for (const pop of p.gemma_pops!) {
      const c = pop.color.toLowerCase()
      if (!popColors.has(c)) popColors.set(c, [])
      popColors.get(c)!.push(p)
    }
  }

  const goodColors = [...popColors.entries()]
    .filter(([, group]) => group.length >= cells.length)
    .map(([color]) => color)
  if (goodColors.length === 0) return []

  const targetColor = randomFrom(goodColors)
  const matching = popColors.get(targetColor)!
  // Deduplicate
  const seen = new Set<string>()
  const unique = matching.filter(p => { if (seen.has(p.id)) return false; seen.add(p.id); return true })

  if (unique.length < cells.length) return []

  const pools = orientPools(unique)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Reward photos where the pop has high impact
    const pop = p.gemma_pops!.find(pp => pp.color.toLowerCase() === targetColor)
    if (pop && (pop.impact === 'high' || pop.impact === 'dominant')) s += 4
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Print Worthy — Gemma's best picks for print
 * Only showcases photos Gemma deemed print-worthy: strong composition, technical quality
 */
function curatePrintWorthy(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && p.print_worthy && (p.aesthetic || 0) > 4
  )
  if (photos.length < cells.length) return []

  const pools = orientPools(photos)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Sharp + balanced exposure = museum quality
    if (p.gemma_sharpness === 'sharp') s += 3
    if (p.gemma_exposure === 'balanced') s += 2
    if (p.gc_weight && p.gc_weight >= 8) s += 3
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Gemma Vibes — uses Gemma's richer vibe vocabulary for deep thematic sets
 * Gemma vibes are more nuanced than base vibes (e.g., "desolate", "cinematic", "whimsical")
 */
function curateGemmaVibes(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && p.gemma_vibes && p.gemma_vibes.length > 0 && (p.aesthetic || 0) > 4
  )
  if (photos.length < cells.length) return []

  const vibeCounts = new Map<string, number>()
  for (const p of photos) {
    for (const v of p.gemma_vibes!) {
      vibeCounts.set(v, (vibeCounts.get(v) || 0) + 1)
    }
  }

  // Pick a Gemma vibe with enough photos
  const goodVibes = [...vibeCounts.entries()]
    .filter(([, count]) => count >= cells.length * 1.5)
    .map(([vibe]) => vibe)
  if (goodVibes.length === 0) return []

  const targetVibe = randomFrom(goodVibes)
  const matching = photos.filter(p => p.gemma_vibes!.includes(targetVibe))

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // More shared Gemma vibes = stronger thematic fit
    const shared = p.gemma_vibes!.filter(v => vibeCounts.get(v)! >= 5).length
    s += shared * 3
    // Color cohesion within mood
    return s + Math.random() * 8
  })
}

/*
 * CURATOR: Subject Gallery — group by Gemma subject analysis
 * Finds photos with shared subject keywords for thematic exhibitions
 */
function curateSubjectGallery(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && p.gemma_subject && (p.aesthetic || 0) > 4
  )
  if (photos.length < cells.length) return []

  // Extract subject keywords and find clusters
  const subjectWords = new Map<string, Photo[]>()
  for (const p of photos) {
    const words = p.gemma_subject!.toLowerCase()
      .split(/[\s,;]+/)
      .filter(w => w.length > 3 && !['with', 'from', 'that', 'this', 'have', 'been', 'they', 'them', 'their'].includes(w))
    for (const w of words) {
      if (!subjectWords.has(w)) subjectWords.set(w, [])
      subjectWords.get(w)!.push(p)
    }
  }

  const goodSubjects = [...subjectWords.entries()]
    .filter(([, group]) => group.length >= cells.length && group.length <= 200)
    .map(([word]) => word)
  if (goodSubjects.length === 0) return []

  const targetWord = randomFrom(goodSubjects)
  const matching = subjectWords.get(targetWord)!
  const seen = new Set<string>()
  const unique = matching.filter(p => { if (seen.has(p.id)) return false; seen.add(p.id); return true })

  if (unique.length < cells.length) return []

  const pools = orientPools(unique)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Hue diversity within subject = visual interest
    return s + Math.random() * 3
  })
}

/*
 * CURATOR: Sharpness Showcase — crisp vs soft, motion blur artistry
 * Groups photos by Gemma sharpness assessment for technical exhibitions
 */
function curateSharpnessShowcase(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p =>
    p.thumb && p.display && !p.parent && p.gemma_sharpness && (p.aesthetic || 0) > 4
  )
  if (photos.length < cells.length) return []

  // Pick a sharpness category
  const categories = ['sharp', 'soft', 'motion_blur'] as const
  const counts = categories.map(c => ({
    cat: c,
    photos: photos.filter(p => p.gemma_sharpness === c),
  }))

  // Try sharp first (most dramatic), then soft (dreamy), then motion_blur (artistic)
  const viable = counts.filter(c => c.photos.length >= cells.length)
  if (viable.length === 0) return []

  const { cat: targetSharpness, photos: matching } = randomFrom(viable)

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    // Sharp: reward high gc_weight (strong subjects)
    // Soft/blur: reward mood and atmosphere
    if (targetSharpness === 'sharp' && p.gc_weight && p.gc_weight >= 7) s += 3
    if (targetSharpness === 'soft' && p.vibes?.some(v => ['dreamy', 'ethereal', 'serene'].includes(v))) s += 3
    if (targetSharpness === 'motion_blur' && (p.contrast || 50) > 60) s += 3
    return s + Math.random() * 8
  })
}

/* Default fill (fallback) — all photos are candidates, heavy randomness */
function fillBentoDefault(photos: Photo[], cells: BentoCell[]): Photo[] {
  const filtered = photos.filter(p => p.thumb && p.display)
  if (filtered.length === 0) return []
  // Use ALL photos — no top-N cap. Every picked photo deserves to appear.
  const pools = orientPools(filtered)

  const allPool = [...pools.L, ...pools.P]
  const firstPool = cells[0].orient === 'P' ? pools.P : pools.L
  const seed = randomFrom(firstPool.length > 0 ? firstPool : allPool)
  const seedHue = seed.hue || 0
  const usedIds = new Set<string>()

  return fillCells(cells, pools, usedIds, (p) => {
    let s = visualImpact(p)
    const hd = hueDist(seedHue, p.hue || 0)
    if (hd < 40) s += 3
    else if (hd > 140) s += 1.5
    if (p.parent) s -= 2
    // Heavy randomness so the full archive rotates — impact is a gentle nudge, not a filter
    return s + Math.random() * 8
  })
}

/* All curators — weighted by quality and frequency */
const CURATORS = [
  curateHeroStory,              // strongest: hero + court
  curateHeroStory,              // double-weight
  curateTemperatureHarmony,     // cohesive temperature
  curateColorStory,             // tight hue range
  curateColorStory,             // double-weight
  curateMoodBoard,              // vibe-based
  curateSceneStory,             // scene-based
  curateDepthJourney,           // depth contrast
  curateMonoAccent,             // B&W + color pop
  curateArchetypeExhibition,    // composition archetype (when data available)
  curateCameraStory,            // camera body character
  curateNightVision,            // dark & dramatic
  curateGoldenHour,             // warm golden hour light
  curateFaceGallery,            // people-focused
  curateStyleContrast,          // film vs digital
  curateBrightnessGradient,     // dark to light sweep
  // Gemma-powered curators
  curateEnergyFlow,             // visual energy direction groups
  curateEnergyFlow,             // double-weight — great visual coherence
  curateSemanticPops,           // shared striking color-object combos
  curatePrintWorthy,            // Gemma's museum-quality picks
  curatePrintWorthy,            // double-weight — always stunning
  curateGemmaVibes,             // deep thematic vibe matching
  curateGemmaVibes,             // double-weight — rich vocabulary
  curateSubjectGallery,         // shared subject keyword clusters
  curateSharpnessShowcase,      // crisp vs soft vs motion artistry
]

function fillBento(allPhotos: Photo[], layout: BentoLayout, colorFiltered: boolean = false): { photos: Photo[], curator: string } {
  const { cells } = layout

  if (!colorFiltered) {
    // Try up to 3 random curators before falling back
    const shuffled = [...CURATORS].sort(() => Math.random() - 0.5)
    for (let i = 0; i < Math.min(3, shuffled.length); i++) {
      const result = shuffled[i](allPhotos, cells)
      if (result.length >= cells.length) {
        return { photos: result.slice(0, cells.length), curator: shuffled[i].name }
      }
    }
  }

  return { photos: fillBentoDefault(allPhotos, cells), curator: 'default' }
}

/* ===== BentoTile component ===== */

interface BentoTileProps {
  photo: Photo
  cell: BentoCell
  cellIndex: number
  index: number
  revealed: boolean
  hasVariant: boolean
  onSwap: (tileEl: HTMLDivElement) => void
  onFullscreen: (photo: Photo) => void
}

function BentoTile({ photo, cell, cellIndex, index, revealed, hasVariant, onSwap, onFullscreen }: BentoTileProps) {
  const tileRef = useRef<HTMLDivElement>(null)

  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (!el) return
    loadProgressive(el, photo, 'display', '(max-width: 768px) 50vw, 33vw')
    /* Override object-position with smart crop */
    el.style.objectPosition = getObjectPosition(photo, cell)
  }, [photo, cell])

  const dominant = photo.palette?.[0]

  const handleClick = useCallback(() => {
    if (tileRef.current) onSwap(tileRef.current)
  }, [onSwap])

  const handleFullscreen = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onFullscreen(photo)
  }, [onFullscreen, photo])

  return (
    <div
      ref={tileRef}
      className={`bento-tile${revealed ? ' bento-tile-revealed' : ''}`}
      data-id={photo.id}
      data-orient={cell.orient}
      data-cell-idx={cellIndex}
      data-variant={photo.parent ? '' : undefined}
      style={{
        gridRow: `${cell.r} / ${cell.r + cell.rs}`,
        gridColumn: `${cell.c} / ${cell.c + cell.cs}`,
        backgroundColor: dominant ? dominant + '99' : undefined,
        '--i': index,
      } as React.CSSProperties}
      onClick={handleClick}
    >
      <img ref={imgRef} alt="" />
      {hasVariant && (
        <span className="bento-tile-variant" aria-label="AI variant available">
          &#x1F984;
        </span>
      )}
      <button className="bento-tile-fs" onClick={handleFullscreen}>
        <FullscreenIcon />
      </button>
    </div>
  )
}

/* ===== BentoView component ===== */

export function BentoView() {
  const data = useAppStore(s => s.data)
  const photoMap = useAppStore(s => s.photoMap)
  const openLightbox = useAppStore(s => s.openLightbox)

  const [layout, setLayout] = useState<BentoLayout | null>(null)
  const [layoutIdx, setLayoutIdx] = useState(-1)
  const [photos, setPhotos] = useState<Photo[]>([])
  const [colorBuckets, setColorBuckets] = useState<BentoColorBucket[]>([])
  const [activeColorIdx, setActiveColorIdx] = useState(-1) // -1 = all colors
  const [densityIdx, setDensityIdx] = useState(BENTO_DEFAULT_DENSITY_IDX)
  const [variantsOn, setVariantsOn] = useState(true)
  const [gridMode, setGridMode] = useState(false) // false=bento, true=uniform grid
  const [loved, setLoved] = useState(false)
  const [activeCurator, setActiveCurator] = useState('')

  /* Variant map: parentId → variant Photo (prefer smart_style > style_transfer) */
  const variantMap = useRef(new Map<string, Photo>())
  /* Track which tile indices are currently showing their variant */
  const revealedRef = useRef(new Set<number>())
  const [revealedSet, setRevealedSet] = useState(new Set<number>())

  /* Refs for mutable state used by intervals/callbacks */
  const photosRef = useRef<Photo[]>([])
  const layoutRef = useRef<BentoLayout | null>(null)
  const layoutIdxRef = useRef(-1)
  const deviceLayoutsRef = useRef<BentoLayout[]>(DESKTOP_LAYOUTS)
  const gridRef = useRef<HTMLDivElement>(null)

  /* Preload buffer: ready-to-swap photos per orientation, already in browser cache */
  const preloadBufferRef = useRef<{ P: Photo[]; L: Photo[] }>({ P: [], L: [] })
  const PRELOAD_COUNT = 6 // per orientation

  /* Build variant map: parent photo id → best variant photo */
  useEffect(() => {
    if (!data) return
    const map = new Map<string, Photo>()
    const typePriority: Record<string, number> = { smart_style: 3, style_transfer: 2, gemma_cartoon: 1, cartoon: 0 }
    for (const p of data.photos) {
      if (!p.parent || !p.variant_type) continue
      const existing = map.get(p.parent)
      if (!existing || (typePriority[p.variant_type] ?? 0) > (typePriority[existing.variant_type ?? ''] ?? 0)) {
        map.set(p.parent, p)
      }
    }
    variantMap.current = map
  }, [data])

  /* Build color buckets */
  useEffect(() => {
    if (!data) return
    setColorBuckets(buildBentoColorBuckets(data.photos))
  }, [data])

  /* Photo pool ref for crossfade/swap (respects color filter) */
  const photoPoolRef = useRef<Photo[]>([])
  useEffect(() => {
    if (!data) return
    photoPoolRef.current = activeColorIdx >= 0 && colorBuckets[activeColorIdx]
      ? colorBuckets[activeColorIdx].photos
      : data.photos
  }, [data, activeColorIdx, colorBuckets])

  /* Keep refs in sync with state */
  useEffect(() => { photosRef.current = photos }, [photos])
  useEffect(() => { layoutRef.current = layout }, [layout])
  useEffect(() => { layoutIdxRef.current = layoutIdx }, [layoutIdx])

  /* Fill preload buffer with candidates not currently displayed, and warm browser cache */
  const refillPreloadBuffer = useCallback((currentIds: Set<string>) => {
    if (!data) return
    const buf = preloadBufferRef.current
    // Remove any that are now displayed
    buf.P = buf.P.filter(p => !currentIds.has(p.id))
    buf.L = buf.L.filter(p => !currentIds.has(p.id))

    const allPool = data.photos.filter(p => p.thumb && p.display && p.aesthetic && !currentIds.has(p.id))
    const pPool = allPool.filter(p => p.orientation === 'portrait')
    const lPool = allPool.filter(p => p.orientation === 'landscape' || p.orientation === 'square')

    const bufPIds = new Set(buf.P.map(p => p.id))
    const bufLIds = new Set(buf.L.map(p => p.id))

    while (buf.P.length < PRELOAD_COUNT && pPool.length > 0) {
      const pick = pPool.splice(Math.floor(Math.random() * pPool.length), 1)[0]
      if (!bufPIds.has(pick.id)) { buf.P.push(pick); bufPIds.add(pick.id) }
    }
    while (buf.L.length < PRELOAD_COUNT && lPool.length > 0) {
      const pick = lPool.splice(Math.floor(Math.random() * lPool.length), 1)[0]
      if (!bufLIds.has(pick.id)) { buf.L.push(pick); bufLIds.add(pick.id) }
    }

    // Warm browser cache
    for (const p of [...buf.P, ...buf.L]) {
      const src = p.display || p.thumb
      if (src) { const img = new Image(); img.decoding = 'async'; img.src = src }
    }
  }, [data])

  /* Generate a fresh bento (layout + fill based on density & color) */
  const generate = useCallback(() => {
    if (!data) return
    const device = isDesktop() ? 'desktop' as const : 'mobile' as const
    let targetCount = BENTO_DENSITY_STEPS[densityIdx]
    const isColorFiltered = activeColorIdx >= 0 && colorBuckets[activeColorIdx]
    let photoPool = isColorFiltered ? colorBuckets[activeColorIdx].photos : data.photos

    // Fall back to all photos if color filter too restrictive
    const availableCount = photoPool.filter(p => p.thumb && p.display).length
    if (availableCount < 3) {
      photoPool = data.photos
    } else if (isColorFiltered && availableCount < targetCount) {
      // Adapt density to what's available in this color bucket
      targetCount = availableCount
    }

    let newLayout = gridMode
      ? uniformSameRatioGrid(targetCount, device)
      : pickLayoutForCount(targetCount, device)
    const fillResult = fillBento(photoPool, newLayout, !!isColorFiltered)
    let selected = fillResult.photos
    setActiveCurator(fillResult.curator)

    // NEVER allow empty tiles — if we have fewer photos than cells, fix it
    if (selected.length > 0 && selected.length < newLayout.count) {
      // First try: pull more photos from the pool to fill the gap
      const usedIds = new Set(selected.map(p => p.id))
      const extras = photoPool.filter(p => p.thumb && p.display && !usedIds.has(p.id))
      while (selected.length < newLayout.count && extras.length > 0) {
        const pick = extras.splice(Math.floor(Math.random() * extras.length), 1)[0]
        selected.push(pick)
      }
      // If still short, shrink to a uniform grid that exactly fits
      if (selected.length < newLayout.count) {
        newLayout = uniformSameRatioGrid(selected.length, device)
        selected = selected.slice(0, newLayout.count)
      }
    }

    // Inject AI variants when unicorn is on.
    // 1) Swap any naturally-selected photos that have variants
    // 2) Replace ~30-40% of remaining slots with variant-parents from the pool
    if (variantsOn && variantMap.current.size > 0) {
      const usedIds = new Set(selected.map(p => p.id))

      // Phase 1: swap photos already in grid that have variants
      for (let i = 0; i < selected.length; i++) {
        const v = variantMap.current.get(selected[i].id)
        if (v && (v.display || v.thumb)) {
          selected[i] = v
        }
      }

      // Phase 2: bring in variant-parents that curators missed.
      // Target: ~40% of grid shows variants (mix of originals + AI art).
      const currentVariantCount = selected.filter(p => p.parent).length
      const targetVariants = Math.ceil(selected.length * 0.4)
      const slotsToFill = targetVariants - currentVariantCount

      if (slotsToFill > 0) {
        // Find variant-parents NOT already in the grid
        const parentPhotos = photoPool
          .filter(p => variantMap.current.has(p.id) && !usedIds.has(p.id) && p.thumb && p.display && !p.parent)
        // Shuffle so we don't always pick the same ones
        for (let i = parentPhotos.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [parentPhotos[i], parentPhotos[j]] = [parentPhotos[j], parentPhotos[i]]
        }
        // Replace non-variant slots (skip slots that are already variants)
        let replaced = 0
        for (let i = 0; i < selected.length && replaced < slotsToFill && replaced < parentPhotos.length; i++) {
          if (selected[i].parent) continue // already a variant, skip
          const parent = parentPhotos[replaced]
          const v = variantMap.current.get(parent.id)
          if (v && (v.display || v.thumb)) {
            selected[i] = v
            replaced++
          }
        }
      }
    }

    deviceLayoutsRef.current = device === 'desktop' ? DESKTOP_LAYOUTS : MOBILE_LAYOUTS
    setLayout(newLayout)
    setLayoutIdx(-1)
    setPhotos(selected)
    revealedRef.current = new Set()
    setRevealedSet(new Set())
    requestAnimationFrame(() => refillPreloadBuffer(new Set(selected.map(p => p.id))))
  }, [data, densityIdx, activeColorIdx, colorBuckets, variantsOn, gridMode, refillPreloadBuffer])

  /* Cycle layouts with arrow keys — just regenerate */
  const cycle = useCallback((_dir: number) => {
    generate()
  }, [generate])

  /* Reveal variant with crossfade for a specific tile */
  const revealVariant = useCallback((tileEl: HTMLDivElement, variant: Photo, cellIdx: number) => {
    const oldId = tileEl.dataset.id
    const target = variant.display || variant.thumb
    if (!target) return

    /* Preload the variant image, then crossfade */
    const preload = new Image()
    preload.decoding = 'async'

    const doSwap = () => {
      const img = tileEl.querySelector('img:not(.bento-tile-original)') as HTMLImageElement
      if (!img) return

      img.src = target
      img.classList.remove('img-loading', 'img-loaded')
      tileEl.dataset.id = variant.id
      if (variant.parent) tileEl.dataset.variant = ''; else delete tileEl.dataset.variant

      const dominant = variant.palette?.[0]
      if (dominant) tileEl.style.backgroundColor = dominant + '99'

      const currentLayout = layoutRef.current
      if (currentLayout && currentLayout.cells[cellIdx]) {
        img.style.objectPosition = getObjectPosition(variant, currentLayout.cells[cellIdx])
      }

      setPhotos(prev => {
        const next = [...prev]
        const bIdx = next.findIndex(p => p.id === oldId)
        if (bIdx >= 0) next[bIdx] = variant
        return next
      })

      requestAnimationFrame(() => { tileEl.style.opacity = '1' })
    }

    /* Fade out → swap → fade in */
    tileEl.style.opacity = '0'
    let done = false
    const onEnd = () => {
      if (done) return
      done = true
      tileEl.removeEventListener('transitionend', onEnd)
      doSwap()
    }
    tileEl.addEventListener('transitionend', onEnd)
    setTimeout(() => { if (!done) { done = true; tileEl.removeEventListener('transitionend', onEnd); doSwap() } }, 600)

    preload.src = target
  }, [])

  /* Swap a single tile — toggle original↔variant first, then random swap */
  const swapTile = useCallback((tileEl: HTMLDivElement) => {
    if (!data) return
    const oldId = tileEl.dataset.id
    const orient = tileEl.dataset.orient as 'P' | 'L' | undefined
    const cellIdx = parseInt(tileEl.dataset.cellIdx || '0', 10)
    const currentPhoto = photosRef.current.find(p => p.id === oldId)

    /* Toggle: if showing a variant → show its original */
    if (currentPhoto?.parent && !revealedRef.current.has(cellIdx)) {
      const original = photoMap[currentPhoto.parent]
      if (original && (original.display || original.thumb)) {
        revealedRef.current.add(cellIdx)
        setRevealedSet(new Set(revealedRef.current))
        revealVariant(tileEl, original, cellIdx)
        return
      }
    }

    /* Toggle: if showing an original that has a variant → show the variant */
    if (oldId && !revealedRef.current.has(cellIdx)) {
      const variant = variantMap.current.get(oldId)
      if (variant && (variant.display || variant.thumb)) {
        revealedRef.current.add(cellIdx)
        setRevealedSet(new Set(revealedRef.current))
        revealVariant(tileEl, variant, cellIdx)
        return
      }
    }

    const currentIds = new Set(photosRef.current.map(p => p.id))
    const buf = preloadBufferRef.current
    const bufPool = orient === 'P' ? buf.P : buf.L

    /* Try preloaded buffer first (already in browser cache), fall back to full pool */
    let newPhoto: Photo | undefined
    const bufReady = bufPool.filter(p => !currentIds.has(p.id))
    if (bufReady.length > 0) {
      const idx = Math.floor(Math.random() * bufReady.length)
      newPhoto = bufReady[idx]
      const bIdx = orient === 'P'
        ? buf.P.findIndex(p => p.id === newPhoto!.id)
        : buf.L.findIndex(p => p.id === newPhoto!.id)
      if (bIdx >= 0) (orient === 'P' ? buf.P : buf.L).splice(bIdx, 1)
    } else {
      let pool = photoPoolRef.current.filter(p => p.thumb && p.display && p.aesthetic && !currentIds.has(p.id))
      if (orient === 'P') pool = pool.filter(p => p.orientation === 'portrait')
      else pool = pool.filter(p => p.orientation === 'landscape' || p.orientation === 'square')
      if (pool.length === 0) return
      newPhoto = randomFrom(pool)
    }

    const target = newPhoto.display || newPhoto.thumb
    if (!target) return

    const img = tileEl.querySelector('img:not(.bento-tile-original)') as HTMLImageElement
    if (!img) return

    /* Instant swap — image should be cached from preload buffer */
    img.src = target
    img.classList.remove('img-loading', 'img-loaded')
    tileEl.dataset.id = newPhoto.id
    if (newPhoto.parent) tileEl.dataset.variant = ''; else delete tileEl.dataset.variant
    const dominant = newPhoto.palette?.[0]
    if (dominant) tileEl.style.backgroundColor = dominant + '99'

    const currentLayout = layoutRef.current
    if (currentLayout && currentLayout.cells[cellIdx]) {
      img.style.objectPosition = getObjectPosition(newPhoto, currentLayout.cells[cellIdx])
    }

    setPhotos(prev => {
      const next = [...prev]
      const bIdx = next.findIndex(p => p.id === oldId)
      if (bIdx >= 0) next[bIdx] = newPhoto!
      return next
    })

    /* Refill buffer in background */
    const nextIds = new Set(photosRef.current.map(p => p.id))
    nextIds.delete(oldId!)
    nextIds.add(newPhoto.id)
    refillPreloadBuffer(nextIds)
  }, [data, refillPreloadBuffer, revealVariant])

  /* Auto crossfade one random tile every CROSSFADE_INTERVAL — uses preload buffer */
  const crossfadeOneTile = useCallback(() => {
    if (!data) return
    const tiles = document.querySelectorAll<HTMLDivElement>('.bento-tile')
    if (tiles.length === 0) return

    const tileIdx = Math.floor(Math.random() * tiles.length)
    const tile = tiles[tileIdx]
    const oldId = tile.dataset.id
    const orient = tile.dataset.orient as 'P' | 'L' | undefined
    const cellIdx = parseInt(tile.dataset.cellIdx || '0', 10)

    const currentIds = new Set(photosRef.current.map(p => p.id))
    const buf = preloadBufferRef.current
    const bufPool = orient === 'P' ? buf.P : buf.L

    let newPhoto: Photo | undefined
    const bufReady = bufPool.filter(p => !currentIds.has(p.id))
    if (bufReady.length > 0) {
      const idx = Math.floor(Math.random() * bufReady.length)
      newPhoto = bufReady[idx]
      const bIdx = orient === 'P'
        ? buf.P.findIndex(p => p.id === newPhoto!.id)
        : buf.L.findIndex(p => p.id === newPhoto!.id)
      if (bIdx >= 0) (orient === 'P' ? buf.P : buf.L).splice(bIdx, 1)
    } else {
      let pool = photoPoolRef.current.filter(p => p.thumb && p.display && p.aesthetic && !currentIds.has(p.id))
      if (orient === 'P') pool = pool.filter(p => p.orientation === 'portrait')
      else pool = pool.filter(p => p.orientation === 'landscape' || p.orientation === 'square')
      if (pool.length === 0) return
      newPhoto = randomFrom(pool)
    }

    const target = newPhoto.display || newPhoto.thumb
    if (!target) return

    let imageReady = false
    let fadeOutDone = false
    const preload = new Image()
    preload.decoding = 'async'

    const applySwap = () => {
      const img = tile.querySelector('img:not(.bento-tile-original)') as HTMLImageElement
      if (!img) return

      img.src = target
      img.classList.remove('img-loading', 'img-loaded')
      img.alt = ''
      tile.dataset.id = newPhoto!.id
      if (newPhoto!.parent) tile.dataset.variant = ''; else delete tile.dataset.variant
      const dominant = newPhoto!.palette?.[0]
      if (dominant) tile.style.backgroundColor = dominant + '99'

      const currentLayout = layoutRef.current
      if (currentLayout && currentLayout.cells[cellIdx]) {
        img.style.objectPosition = getObjectPosition(newPhoto!, currentLayout.cells[cellIdx])
      }

      setPhotos(prev => {
        const next = [...prev]
        const bIdx = next.findIndex(p => p.id === oldId)
        if (bIdx >= 0) next[bIdx] = newPhoto!
        return next
      })

      requestAnimationFrame(() => { tile.style.opacity = '1' })

      const nextIds = new Set(photosRef.current.map(p => p.id))
      nextIds.delete(oldId!)
      nextIds.add(newPhoto!.id)
      refillPreloadBuffer(nextIds)
    }

    const tryApply = () => {
      if (imageReady && fadeOutDone) applySwap()
    }

    preload.onload = () => { imageReady = true; tryApply() }
    preload.onerror = () => { imageReady = true; tryApply() }
    preload.src = target

    tile.style.opacity = '0'

    const onFadeOut = () => {
      tile.removeEventListener('transitionend', onFadeOut)
      fadeOutDone = true
      tryApply()
    }
    tile.addEventListener('transitionend', onFadeOut)
    setTimeout(() => { if (!fadeOutDone) { fadeOutDone = true; tile.removeEventListener('transitionend', onFadeOut); tryApply() } }, 900)
  }, [data, refillPreloadBuffer])

  /* Init: generate on mount */
  useEffect(() => {
    if (data) generate()
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  /* Crossfade timer */
  useEffect(() => {
    const id = window.setInterval(crossfadeOneTile, CROSSFADE_INTERVAL)
    return () => clearInterval(id)
  }, [crossfadeOneTile])

  /* Keyboard handler */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault()
        generate()
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        cycle(1)
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        cycle(-1)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [generate, cycle])

  /* Listen for 'bento-dice' custom event */
  useEffect(() => {
    const handler = () => generate()
    document.addEventListener('bento-dice', handler)
    return () => document.removeEventListener('bento-dice', handler)
  }, [generate])

  /* Resize/orientation change — regenerate if device class changes */
  useEffect(() => {
    let wasDesktop = isDesktop()
    const onResize = () => {
      const nowDesktop = isDesktop()
      if (nowDesktop !== wasDesktop) {
        wasDesktop = nowDesktop
        generate()
      }
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [generate])

  /* Touch/swipe support */
  const touchStartRef = useRef({ x: 0, y: 0 })
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
  }, [])
  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    const dx = e.changedTouches[0].clientX - touchStartRef.current.x
    const dy = e.changedTouches[0].clientY - touchStartRef.current.y
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
      if (dx > 0) cycle(-1)
      else cycle(1)
    }
  }, [cycle])

  /* Fullscreen handler */
  const handleFullscreen = useCallback((photo: Photo) => {
    openLightbox(photo, photosRef.current)
  }, [openLightbox])

  /* Density controls */
  const lessDense = useCallback(() => {
    setDensityIdx(i => Math.max(0, i - 1))
  }, [])

  const moreDense = useCallback(() => {
    setDensityIdx(i => Math.min(BENTO_DENSITY_STEPS.length - 1, i + 1))
  }, [])

  /* Color band selection */
  const selectColorBand = useCallback((idx: number) => {
    if (idx === activeColorIdx) {
      setActiveColorIdx(-1) // deselect = show all
    } else {
      setActiveColorIdx(idx)
    }
  }, [activeColorIdx])

  /* 🧞‍♂️ Best bento — pick a random count (2–16), use the best curator, best layout.
   * In unicorn mode: guarantee at least half the tiles show generated variants. */
  const showBestBento = useCallback(() => {
    if (!data) return
    const device = isDesktop() ? 'desktop' as const : 'mobile' as const
    const count = 2 + Math.floor(Math.random() * 15)
    const newLayout = pickLayoutForCount(count, device)
    const allPhotos = data.photos

    let bestResult: Photo[] = []
    let bestScore = -Infinity
    const shuffled = [...CURATORS].sort(() => Math.random() - 0.5)
    for (let i = 0; i < Math.min(8, shuffled.length); i++) {
      const result = shuffled[i](allPhotos, newLayout.cells)
      if (result.length >= Math.min(newLayout.cells.length, 2)) {
        const score = result.reduce((s, p) => s + visualImpact(p), 0) / result.length
        if (score > bestScore) { bestScore = score; bestResult = result.slice(0, newLayout.cells.length) }
      }
    }
    if (bestResult.length === 0) {
      bestResult = fillBentoDefault(allPhotos, newLayout.cells)
    }

    // In unicorn mode: mix — swap roughly half to variants, keep rest as originals
    if (variantsOn && variantMap.current.size > 0) {
      const variantParentIds = new Set(variantMap.current.keys())

      // Try to get photos that have variants into the mix
      const withVariant = allPhotos.filter(p => variantParentIds.has(p.id) && p.thumb && p.display && !p.parent)
      const usedIds = new Set(bestResult.map(p => p.id))
      for (let i = 0; i < bestResult.length && withVariant.length > 0; i++) {
        if (!variantParentIds.has(bestResult[i].id)) {
          const pick = withVariant.find(p => !usedIds.has(p.id))
          if (pick) {
            usedIds.delete(bestResult[i].id)
            bestResult[i] = pick
            usedIds.add(pick.id)
          }
        }
      }

      // Swap roughly half to variant versions, keep at least 1 original
      const swappable = bestResult
        .map((p, i) => ({ i, variant: variantMap.current.get(p.id) }))
        .filter(x => x.variant && (x.variant.display || x.variant.thumb))
      const maxSwap = Math.min(swappable.length, Math.max(1, Math.ceil(bestResult.length / 2)))
      const toSwap = [...swappable].sort(() => Math.random() - 0.5).slice(0, maxSwap)
      for (const { i, variant } of toSwap) {
        bestResult[i] = variant!
      }
    }

    setGridMode(false)
    setActiveColorIdx(-1)
    setDensityIdx(BENTO_DENSITY_STEPS.indexOf(
      BENTO_DENSITY_STEPS.reduce((best, s) => Math.abs(s - count) < Math.abs(best - count) ? s : best)
    ))
    setLayout(newLayout)
    setPhotos(bestResult)
    revealedRef.current = new Set()
    setRevealedSet(new Set())
    requestAnimationFrame(() => refillPreloadBuffer(new Set(bestResult.map(p => p.id))))
  }, [data, variantsOn, refillPreloadBuffer])

  /* Regenerate when density or color changes */
  useEffect(() => {
    if (data && colorBuckets.length > 0) generate()
  }, [densityIdx, activeColorIdx, variantsOn, gridMode]) // eslint-disable-line react-hooks/exhaustive-deps

  /* Reset heart when composition changes */
  useEffect(() => { setLoved(false) }, [photos, layout])

  /* Love this bento — render PNG on server + save locally + Firestore */
  const loveBento = useCallback(() => {
    if (!layout || photos.length === 0) return
    if (loved) return // already loved
    setLoved(true)

    const payload = {
      layoutId: layout.id,
      cols: layout.cols,
      rows: layout.rows,
      cells: layout.cells.map(c => ({ r: c.r, c: c.c, rs: c.rs, cs: c.cs, orient: c.orient })),
      photos: photos.map(p => p.id),
      gridMode,
      density: BENTO_DENSITY_STEPS[densityIdx],
      colorIdx: activeColorIdx,
      device: isDesktop() ? 'desktop' : 'mobile',
      curator: activeCurator || 'default',
    }

    // Save locally (always works)
    try {
      const loves = JSON.parse(localStorage.getItem('bento-loves') || '[]')
      loves.push({ ...payload, ts: Date.now() })
      localStorage.setItem('bento-loves', JSON.stringify(loves))
    } catch { /* localStorage full or unavailable */ }

    // Trigger server render (fire-and-forget)
    fetch('/api/bento/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {})

    // Firestore (may fail if auth expired — that's OK)
    fireAndForget('bento-loves', payload)
  }, [layout, photos, gridMode, densityIdx, activeColorIdx, loved, activeCurator])

  if (!layout || photos.length === 0) {
    return <div className="bento-wrap" />
  }

  const isMobile = layout.device === 'mobile'
  const containerRatio = isMobile ? (2 / 3) : (3 / 2)

  return (
    <div
      className={`bento-wrap${isMobile ? ' bento-mobile' : ''}`}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      onClick={(e) => { if (e.target === e.currentTarget) showBestBento() }}
    >
      <div
        ref={gridRef}
        className="bento-grid"
        style={{
          '--bento-cols': layout.cols,
          '--bento-rows': layout.rows,
          aspectRatio: containerRatio,
        } as React.CSSProperties}
      >
        {photos.map((photo, i) => {
          const cell = layout.cells[i]
          if (!cell || !photo) return null
          return (
            <BentoTile
              key={photo.id}
              photo={photo}
              cell={cell}
              cellIndex={i}
              index={i}
              revealed={revealedSet.has(i)}
              hasVariant={!photo.parent && variantMap.current.has(photo.id)}
              onSwap={swapTile}
              onFullscreen={handleFullscreen}
            />
          )
        })}
      </div>
      <ViewBottom>
        <div
          className="bento-controls"
        >
          <div className="bento-spectrum">
            {colorBuckets.map((bucket, i) => (
              <div
                key={i}
                className={`bento-band${i === activeColorIdx ? ' active' : ''}`}
                style={{ background: bucket.color }}
                onClick={() => selectColorBand(i)}
              />
            ))}
          </div>
          <div className="bento-btn-group">
            <button
              className="bento-ctrl-btn"
              onClick={lessDense}
              disabled={densityIdx <= 0}
              aria-label="Less dense"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
                <line x1="4" y1="10" x2="16" y2="10" />
              </svg>
            </button>
            <button
              className="bento-ctrl-btn"
              onClick={moreDense}
              disabled={densityIdx >= BENTO_DENSITY_STEPS.length - 1}
              aria-label="More dense"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
                <line x1="4" y1="10" x2="16" y2="10" />
                <line x1="10" y1="4" x2="10" y2="16" />
              </svg>
            </button>
            <button
              className="bento-ctrl-btn"
              onClick={() => setGridMode(g => !g)}
              aria-label={gridMode ? 'Switch to bento' : 'Switch to grid'}
              title={gridMode ? 'Uniform grid' : 'Bento layout'}
            >
              {gridMode ? (
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="2" width="7" height="7" rx="1.5" />
                  <rect x="11" y="2" width="7" height="7" rx="1.5" />
                  <rect x="2" y="11" width="7" height="7" rx="1.5" />
                  <rect x="11" y="11" width="7" height="7" rx="1.5" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="2" width="7" height="16" rx="1.5" />
                  <rect x="11" y="2" width="7" height="7" rx="1.5" />
                  <rect x="11" y="11" width="7" height="7" rx="1.5" />
                </svg>
              )}
            </button>
            <button
              className="bento-ctrl-btn"
              onClick={showBestBento}
              aria-label="Best bento"
              title="Show the best bento"
            >
              &#x1F9DE;&#x200D;&#x2642;&#xFE0F;
            </button>
            <button
              className={`bento-ctrl-btn${variantsOn ? ' bento-unicorn-active' : ''}`}
              onClick={() => setVariantsOn(v => !v)}
              aria-label="Toggle AI variants"
              title={variantsOn ? 'Hide AI variants' : 'Show AI variants'}
            >
              &#x1F984;
            </button>
          </div>
          <button
            className="bento-ctrl-btn bento-heart"
            onClick={loveBento}
            aria-label="Love this composition"
            title="Love this bento"
          >
            {loved ? '\u2764\uFE0F' : '\u{1F90D}'}
          </button>
        </div>
      </ViewBottom>
    </div>
  )
}
