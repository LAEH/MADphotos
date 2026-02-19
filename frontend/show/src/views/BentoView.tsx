import { useState, useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { getObjectPosition, BENTO_UNIT_RATIO } from '../lib/cropUtils'
import { randomFrom } from '../lib/utils'
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
  const targetRatio = device === 'desktop' ? 1.25 : 0.5
  let bestCols = 1, bestRows = 1, bestScore = Infinity
  for (let c = 1; c <= 10; c++) {
    const r = Math.ceil(count / c)
    const waste = c * r - count
    const ratio = c / r
    const score = waste + Math.abs(ratio - targetRatio) * 5
    if (score < bestScore) { bestCols = c; bestRows = r; bestScore = score }
  }
  const cells: BentoCell[] = []
  const lastRowStart = count - (count % bestCols || bestCols)
  for (let i = 0; i < count; i++) {
    const r = Math.floor(i / bestCols) + 1
    const c = (i % bestCols) + 1
    if (i >= lastRowStart) {
      // Last row: distribute remaining items evenly across all columns
      const itemsInLastRow = count - lastRowStart
      const idx = i - lastRowStart
      const colSpan = Math.floor(bestCols / itemsInLastRow) + (idx < bestCols % itemsInLastRow ? 1 : 0)
      let colStart = 1
      for (let j = 0; j < idx; j++) {
        colStart += Math.floor(bestCols / itemsInLastRow) + (j < bestCols % itemsInLastRow ? 1 : 0)
      }
      cells.push(L(r, colStart, 1, colSpan))
    } else {
      cells.push(L(r, c, 1, 1))
    }
  }
  return { id: `UG${count}`, cols: bestCols, rows: bestRows, count: cells.length, device, cells }
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

/* ===== Smart curators — each produces a themed bento set ===== */

/** Helper: hue distance (0-180) */
function hueDist(a: number, b: number): number {
  const d = Math.abs(a - b)
  return d > 180 ? 360 - d : d
}

/** Helper: pick best from pool by scoring function */
function pickBest(
  pool: Photo[], usedIds: Set<string>, scoreFn: (p: Photo) => number,
): Photo | undefined {
  const available = pool.filter(p => !usedIds.has(p.id))
  if (available.length === 0) return undefined
  let best = available[0], bestScore = scoreFn(best)
  for (let i = 1; i < Math.min(available.length, 300); i++) {
    const s = scoreFn(available[i])
    if (s > bestScore) { best = available[i]; bestScore = s }
  }
  return best
}

/** Helper: split photos into orientation pools */
function orientPools(photos: Photo[]) {
  return {
    P: photos.filter(p => p.orientation === 'portrait'),
    L: photos.filter(p => p.orientation === 'landscape' || p.orientation === 'square'),
  }
}

/** Helper: fill cells from oriented pools with a scoring function */
function fillCells(
  cells: BentoCell[], pools: { P: Photo[]; L: Photo[] },
  usedIds: Set<string>, scoreFn: (p: Photo) => number,
): Photo[] {
  const result: Photo[] = []
  for (const cell of cells) {
    const pool = cell.orient === 'P' ? pools.P : pools.L
    const pick = pickBest(pool, usedIds, scoreFn)
    if (!pick) {
      // Fallback to other orientation
      const alt = cell.orient === 'P' ? pools.L : pools.P
      const altPick = pickBest(alt, usedIds, scoreFn)
      if (altPick) { result.push(altPick); usedIds.add(altPick.id) }
      continue
    }
    result.push(pick)
    usedIds.add(pick.id)
  }
  return result
}

/*
 * CURATOR 1: Style Showcase — pick a style, fill with variants of that style + color-matched originals
 */
function _curateStyleShowcase(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const variants = allPhotos.filter(p => p.style_name && p.parent && p.thumb && p.display)
  if (variants.length === 0) return []

  // Group variants by style
  const byStyle = new Map<string, Photo[]>()
  for (const v of variants) {
    const key = v.style_name!
    if (!byStyle.has(key)) byStyle.set(key, [])
    byStyle.get(key)!.push(v)
  }

  // Pick a style that has enough images
  const styleKeys = [...byStyle.keys()].filter(k => byStyle.get(k)!.length >= 3)
  if (styleKeys.length === 0) return []
  const style = randomFrom(styleKeys)
  const styleVariants = [...byStyle.get(style)!].sort(() => Math.random() - 0.5)

  // Fill ~50-70% with variants, rest with color-harmonious originals
  const variantSlots = Math.max(3, Math.ceil(cells.length * 0.6))
  const usedIds = new Set<string>()
  const usedParents = new Set<string>()

  // Pick variants
  const picked: Photo[] = []
  const pools = orientPools(styleVariants)
  for (let i = 0; i < Math.min(variantSlots, cells.length) && i < cells.length; i++) {
    const cell = cells[i]
    const pool = cell.orient === 'P' ? pools.P : pools.L
    const fallback = cell.orient === 'P' ? pools.L : pools.P
    const pick = pool.find(p => !usedIds.has(p.id) && !usedParents.has(p.parent!))
      || fallback.find(p => !usedIds.has(p.id) && !usedParents.has(p.parent!))
    if (!pick) break
    picked.push(pick)
    usedIds.add(pick.id)
    usedParents.add(pick.parent!)
  }

  if (picked.length === 0) return []

  // Fill remaining with originals that match the color palette
  const avgHue = picked.reduce((s, p) => s + (p.hue || 0), 0) / picked.length
  const originals = allPhotos.filter(p => !p.parent && p.thumb && p.display && p.aesthetic)
  const origPools = orientPools(originals)

  const remaining = cells.slice(picked.length)
  const fills = fillCells(remaining, origPools, usedIds, (p) => {
    let score = (p.aesthetic || 5)
    score += (30 - hueDist(p.hue || 0, avgHue)) / 3
    return score
  })

  return [...picked, ...fills]
}

/*
 * CURATOR 2: Transform Pairs — originals next to their generated versions
 */
function _curateTransformPairs(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const variants = allPhotos.filter(p => p.parent && p.thumb && p.display)
  const origMap = new Map<string, Photo>()
  for (const p of allPhotos) {
    if (!p.parent && p.thumb && p.display) origMap.set(p.id, p)
  }

  // Find variant+original pairs
  type Pair = { orig: Photo; variant: Photo }
  const pairs: Pair[] = []
  for (const v of variants) {
    const orig = origMap.get(v.parent!)
    if (orig) pairs.push({ orig, variant: v })
  }
  if (pairs.length === 0) return []

  // Shuffle and pick pairs
  const shuffled = [...pairs].sort(() => Math.random() - 0.5)
  const usedIds = new Set<string>()
  const selected: Photo[] = []

  for (const pair of shuffled) {
    if (selected.length >= cells.length) break
    if (usedIds.has(pair.orig.id) || usedIds.has(pair.variant.id)) continue

    // Try to place both — original first, variant second
    selected.push(pair.orig, pair.variant)
    usedIds.add(pair.orig.id)
    usedIds.add(pair.variant.id)
  }

  return selected.slice(0, cells.length)
}

/*
 * CURATOR 3: Color Story — tight hue range, mix of originals and variants
 */
function curateColorStory(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && (p.aesthetic || 0) > 4)

  // Pick a random target hue
  const targetHue = Math.random() * 360
  const hueRange = 40 // ±40 degrees

  // Find photos in this hue range
  const inRange = photos.filter(p => hueDist(p.hue || 0, targetHue) < hueRange)
  if (inRange.length < cells.length) {
    // Widen range
    const wider = photos.filter(p => hueDist(p.hue || 0, targetHue) < 80)
    if (wider.length < 4) return []
    return fillBentoDefault(wider, cells)
  }

  // Prioritize variants in this range
  const variants = inRange.filter(p => p.parent)
  const originals = inRange.filter(p => !p.parent)

  // Originals first, sprinkle in a few variants
  const sorted = [
    ...originals.sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0)),
    ...variants.sort(() => Math.random() - 0.5),
  ]

  const pools = orientPools(sorted)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let score = (p.aesthetic || 5)
    score += (40 - hueDist(p.hue || 0, targetHue)) / 4
    if (p.parent) score -= 2 // prefer originals
    return score + Math.random() * 3
  })
}

/*
 * CURATOR 4: Mood Board — pick a vibe, find matching photos
 */
function curateMoodBoard(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && p.vibes && p.vibes.length > 0)
  if (photos.length === 0) return []

  // Count vibes to find popular ones
  const vibeCounts = new Map<string, number>()
  for (const p of photos) {
    for (const v of p.vibes!) {
      vibeCounts.set(v, (vibeCounts.get(v) || 0) + 1)
    }
  }

  // Pick a vibe that has enough photos
  const goodVibes = [...vibeCounts.entries()]
    .filter(([, count]) => count >= cells.length)
    .map(([vibe]) => vibe)
  if (goodVibes.length === 0) return []

  const targetVibe = randomFrom(goodVibes)
  const matching = photos.filter(p => p.vibes!.includes(targetVibe))
    .sort(() => Math.random() - 0.5)

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let score = (p.aesthetic || 5)
    // More shared vibes = better
    const shared = p.vibes!.filter(v => {
      const count = vibeCounts.get(v) || 0
      return count >= 5
    }).length
    score += shared * 2
    if (p.parent) score -= 2 // prefer originals
    return score + Math.random() * 3
  })
}

/*
 * CURATOR 5: Variants Gallery — all variants, curated by visual coherence
 */
function _curateVariantsGallery(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const variants = allPhotos.filter(p => p.parent && p.thumb && p.display)
  if (variants.length < 4) return []

  const shuffled = [...variants].sort(() => Math.random() - 0.5)
  const seed = shuffled[0]
  const seedHue = seed.hue || 0

  const pools = orientPools(variants)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let score = (p.aesthetic || 5)
    // Color coherence with seed
    score += (60 - hueDist(p.hue || 0, seedHue)) / 6
    // Style variety bonus
    if (p.style_name !== seed.style_name) score += 3
    return score + Math.random() * 4
  })
}

/*
 * CURATOR 6: Scene Story — photos from the same scene type
 */
function curateSceneStory(allPhotos: Photo[], cells: BentoCell[]): Photo[] {
  const photos = allPhotos.filter(p => p.thumb && p.display && p.scene)
  if (photos.length === 0) return []

  const sceneCounts = new Map<string, number>()
  for (const p of photos) {
    sceneCounts.set(p.scene!, (sceneCounts.get(p.scene!) || 0) + 1)
  }

  const goodScenes = [...sceneCounts.entries()]
    .filter(([, count]) => count >= cells.length)
    .map(([scene]) => scene)
  if (goodScenes.length === 0) return []

  const targetScene = randomFrom(goodScenes)
  const matching = photos.filter(p => p.scene === targetScene)
    .sort(() => Math.random() - 0.5)

  const pools = orientPools(matching)
  const usedIds = new Set<string>()
  return fillCells(cells, pools, usedIds, (p) => {
    let score = (p.aesthetic || 5)
    if (p.parent) score -= 2 // prefer originals
    return score + Math.random() * 3
  })
}

/* Default fill (fallback) — the original algorithm with variant boost */
function fillBentoDefault(photos: Photo[], cells: BentoCell[]): Photo[] {
  const filtered = photos.filter(p => p.thumb && p.display)
  if (filtered.length === 0) return []
  const sorted = [...filtered].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))
  const pools = orientPools(sorted.slice(0, 500))

  // Combine both pools as fallback
  const allPool = [...pools.L, ...pools.P]
  const firstPool = cells[0].orient === 'P' ? pools.P : pools.L
  const seed = randomFrom(firstPool.length > 0 ? firstPool : allPool)
  const usedIds = new Set([seed.id])
  const result = [seed]

  for (let i = 1; i < cells.length; i++) {
    const cell = cells[i]
    const primary = cell.orient === 'P' ? pools.P : pools.L
    const fallback = cell.orient === 'P' ? pools.L : pools.P
    const pick = pickBest(primary, usedIds, (p) => {
      let score = (p.aesthetic || 5) / 2
      let cd = hueDist(seed.hue || 0, p.hue || 0)
      score += cd < 60 ? 10 : (cd > 150 ? 8 : 3)
      if (p.parent) score -= 2
      return score + Math.random() * 2
    }) || pickBest(fallback, usedIds, (p) => (p.aesthetic || 5) + Math.random() * 2)
    if (pick) { result.push(pick); usedIds.add(pick.id) }
  }
  return result
}

/* All curators — weighted toward originals, variants are the spice not the main course */
const CURATORS = [
  curateColorStory,
  curateMoodBoard,
  curateSceneStory,
  curateColorStory,   // double-weight: mostly originals
  curateMoodBoard,    // double-weight: mostly originals
]

function fillBento(allPhotos: Photo[], layout: BentoLayout, colorFiltered: boolean = false): Photo[] {
  const { cells } = layout

  if (!colorFiltered) {
    // Pick a random curator
    const curator = randomFrom(CURATORS)
    const result = curator(allPhotos, cells)

    // If curator produced enough photos, use them
    if (result.length >= Math.min(cells.length, 4)) {
      return result.slice(0, cells.length)
    }
  }

  // Fallback to default (always used for color-filtered)
  return fillBentoDefault(allPhotos, cells)
}

/* ===== BentoTile component ===== */

interface BentoTileProps {
  photo: Photo
  cell: BentoCell
  cellIndex: number
  index: number
  revealed: boolean
  onSwap: (tileEl: HTMLDivElement) => void
  onFullscreen: (photo: Photo) => void
}

function BentoTile({ photo, cell, cellIndex, index, revealed, onSwap, onFullscreen }: BentoTileProps) {
  const tileRef = useRef<HTMLDivElement>(null)

  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (!el) return
    loadProgressive(el, photo, 'display')
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
      <button className="bento-tile-fs" onClick={handleFullscreen}>
        <FullscreenIcon />
      </button>
    </div>
  )
}

/* ===== BentoView component ===== */

export function BentoView() {
  const data = useAppStore(s => s.data)
  const openLightbox = useAppStore(s => s.openLightbox)

  const [layout, setLayout] = useState<BentoLayout | null>(null)
  const [layoutIdx, setLayoutIdx] = useState(-1)
  const [photos, setPhotos] = useState<Photo[]>([])
  const [colorBuckets, setColorBuckets] = useState<BentoColorBucket[]>([])
  const [activeColorIdx, setActiveColorIdx] = useState(-1) // -1 = all colors
  const [densityIdx, setDensityIdx] = useState(BENTO_DEFAULT_DENSITY_IDX)

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
  const [gridWidth, setGridWidth] = useState<number | undefined>()

  /* Sync controls width with grid width */
  useEffect(() => {
    const el = gridRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width
      if (w) setGridWidth(w)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

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
    const targetCount = BENTO_DENSITY_STEPS[densityIdx]
    const isColorFiltered = activeColorIdx >= 0 && colorBuckets[activeColorIdx]
    let photoPool = isColorFiltered ? colorBuckets[activeColorIdx].photos : data.photos

    // Fall back to all photos if color filter too restrictive
    if (photoPool.filter(p => p.thumb && p.display).length < 3) {
      photoPool = data.photos
    }

    let newLayout = pickLayoutForCount(targetCount, device)
    let selected = fillBento(photoPool, newLayout, !!isColorFiltered)

    // If couldn't fill layout, use a uniform grid that tiles perfectly
    if (selected.length > 0 && selected.length < newLayout.count) {
      newLayout = uniformBentoGrid(selected.length, device)
      selected = selected.slice(0, newLayout.count)
    }

    deviceLayoutsRef.current = device === 'desktop' ? DESKTOP_LAYOUTS : MOBILE_LAYOUTS
    setLayout(newLayout)
    setLayoutIdx(-1)
    setPhotos(selected)
    revealedRef.current = new Set()
    setRevealedSet(new Set())
    requestAnimationFrame(() => refillPreloadBuffer(new Set(selected.map(p => p.id))))
  }, [data, densityIdx, activeColorIdx, colorBuckets, refillPreloadBuffer])

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
      const img = tileEl.querySelector('img')
      if (!img) return

      img.src = target
      img.classList.remove('img-loading', 'img-loaded')
      tileEl.dataset.id = variant.id
      tileEl.dataset.variant = ''

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

  /* Swap a single tile — check for variant reveal first, then random swap */
  const swapTile = useCallback((tileEl: HTMLDivElement) => {
    if (!data) return
    const oldId = tileEl.dataset.id
    const orient = tileEl.dataset.orient as 'P' | 'L' | undefined
    const cellIdx = parseInt(tileEl.dataset.cellIdx || '0', 10)

    /* Check if this tile has a variant to reveal */
    if (oldId && !revealedRef.current.has(cellIdx)) {
      const variant = variantMap.current.get(oldId)
      if (variant) {
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

    const img = tileEl.querySelector('img')
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
      const img = tile.querySelector('img')
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

  /* Dice = randomize EVERYTHING */
  const rollDice = useCallback(() => {
    if (colorBuckets.length > 0) {
      const nonEmpty = colorBuckets.map((b, i) => ({ b, i })).filter(x => x.b.photos.length > 0)
      if (nonEmpty.length > 0 && Math.random() > 0.3) {
        setActiveColorIdx(randomFrom(nonEmpty).i)
      } else {
        setActiveColorIdx(-1) // sometimes show all colors
      }
    }
    setDensityIdx(Math.floor(Math.random() * BENTO_DENSITY_STEPS.length))
  }, [colorBuckets])

  /* Recycle = new layout, same photos */
  const reshuffleLayout = useCallback(() => {
    if (photos.length === 0) return
    const device = isDesktop() ? 'desktop' as const : 'mobile' as const
    const targetCount = BENTO_DENSITY_STEPS[densityIdx]
    let newLayout = pickLayoutForCount(targetCount, device)
    const shuffled = [...photos].sort(() => Math.random() - 0.5)
    const trimmed = shuffled.slice(0, newLayout.count)
    if (trimmed.length < newLayout.count) {
      newLayout = uniformBentoGrid(trimmed.length, device)
    }
    setLayout(newLayout)
    setPhotos(trimmed.slice(0, newLayout.count))
    revealedRef.current = new Set()
    setRevealedSet(new Set())
  }, [photos, densityIdx])

  /* Regenerate when density or color changes */
  useEffect(() => {
    if (data && colorBuckets.length > 0) generate()
  }, [densityIdx, activeColorIdx]) // eslint-disable-line react-hooks/exhaustive-deps

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
              onSwap={swapTile}
              onFullscreen={handleFullscreen}
            />
          )
        })}
      </div>
      <ViewBottom>
        <div
          className="bento-controls"
          style={{ width: gridWidth ? `${gridWidth}px` : undefined }}
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
              <svg width="22" height="22" viewBox="0 0 20 20" fill="none">
                <rect x="2" y="3" width="7" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.5"/>
                <rect x="11" y="3" width="7" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.5"/>
              </svg>
            </button>
            <button
              className="bento-ctrl-btn"
              onClick={moreDense}
              disabled={densityIdx >= BENTO_DENSITY_STEPS.length - 1}
              aria-label="More dense"
            >
              <svg width="22" height="22" viewBox="0 0 20 20" fill="none">
                <rect x="1" y="2" width="5" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                <rect x="7.5" y="2" width="5" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                <rect x="14" y="2" width="5" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                <rect x="1" y="11" width="5" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                <rect x="7.5" y="11" width="5" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                <rect x="14" y="11" width="5" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
              </svg>
            </button>
            <button
              className="bento-ctrl-btn"
              onClick={reshuffleLayout}
              aria-label="New layout"
              title="Rearrange current photos"
            >
              &#x267B;&#xFE0F;
            </button>
            <button
              className="bento-ctrl-btn"
              onClick={rollDice}
              aria-label="Shuffle everything"
              title="New layout, color & density"
            >
              &#x1F3B2;
            </button>
            <button
              className="bento-ctrl-btn"
              aria-label="Like"
              title="Save to favorites"
            >
              &#x2764;&#xFE0F;
            </button>
          </div>
        </div>
      </ViewBottom>
    </div>
  )
}
