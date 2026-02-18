import { useState, useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { getObjectPosition, BENTO_UNIT_RATIO } from '../lib/cropUtils'
import { randomFrom } from '../lib/utils'
import { ViewBottom, ActionButton } from '../components/ui/ViewBottom'
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
]

const CROSSFADE_INTERVAL = 20_000

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

function getLayoutsForDevice(): BentoLayout[] {
  return isDesktop() ? DESKTOP_LAYOUTS : MOBILE_LAYOUTS
}

/* ===== Photo selection logic ===== */

function fillBento(allPhotos: Photo[], layout: BentoLayout): Photo[] {
  const { cells } = layout

  const photos = allPhotos.filter(p => p.thumb && p.display && p.aesthetic)
  const sorted = [...photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))

  /* Strict orientation pools — no cross-orientation */
  const portraitPool = sorted.filter(p => p.orientation === 'portrait').slice(0, 500)
  const landscapePool = sorted.filter(p =>
    p.orientation === 'landscape' || p.orientation === 'square'
  ).slice(0, 500)

  /* Pick seed from the first cell's pool */
  const firstPool = cells[0].orient === 'P' ? portraitPool : landscapePool
  if (firstPool.length === 0) return []

  const seed = randomFrom(firstPool)
  const selected: Photo[] = [seed]
  const usedIds = new Set([seed.id])
  const usedScenes = new Set(seed.scene ? [seed.scene] : [])
  const usedVibes = new Set(seed.vibes || [])

  /* For each remaining cell, pick from the correct orientation pool */
  for (let i = 1; i < cells.length; i++) {
    const cell = cells[i]
    const pool = cell.orient === 'P' ? portraitPool : landscapePool
    const remaining = pool.filter(p => !usedIds.has(p.id))
    if (remaining.length === 0) continue

    let bestIdx = 0
    let bestScore = -1
    const useDiversity = i % 2 === 1

    for (let j = 0; j < Math.min(remaining.length, 200); j++) {
      const candidate = remaining[j]
      let score = 0

      /* Chromatic harmony with seed */
      let colorDist = Math.abs((seed.hue || 0) - (candidate.hue || 0))
      if (colorDist > 180) colorDist = 360 - colorDist
      score += colorDist < 60 ? 10 : (colorDist > 150 ? 8 : 3)

      /* Aesthetic bonus */
      score += (candidate.aesthetic || 5) / 2

      if (useDiversity) {
        if (candidate.scene && !usedScenes.has(candidate.scene)) score += 8
        if (candidate.vibes) {
          let newVibes = 0
          for (const v of candidate.vibes) {
            if (!usedVibes.has(v)) newVibes++
          }
          score += newVibes * 3
        }
      }

      if (score > bestScore) {
        bestScore = score
        bestIdx = j
      }
    }

    const pick = remaining[bestIdx]
    selected.push(pick)
    usedIds.add(pick.id)
    if (pick.scene) usedScenes.add(pick.scene)
    if (pick.vibes) { for (const v of pick.vibes) usedVibes.add(v) }
  }

  return selected
}

function pickLayout(): { layout: BentoLayout; idx: number; layouts: BentoLayout[] } {
  const layouts = getLayoutsForDevice()
  const idx = Math.floor(Math.random() * layouts.length)
  return { layout: layouts[idx], idx, layouts }
}

/* ===== BentoTile component ===== */

interface BentoTileProps {
  photo: Photo
  cell: BentoCell
  cellIndex: number
  index: number
  onSwap: (tileEl: HTMLDivElement) => void
  onFullscreen: (photo: Photo) => void
}

function BentoTile({ photo, cell, cellIndex, index, onSwap, onFullscreen }: BentoTileProps) {
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
      className="bento-tile"
      data-id={photo.id}
      data-orient={cell.orient}
      data-cell-idx={cellIndex}
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
  const registerTimer = useAppStore(s => s.registerTimer)

  const [layout, setLayout] = useState<BentoLayout | null>(null)
  const [layoutIdx, setLayoutIdx] = useState(-1)
  const [photos, setPhotos] = useState<Photo[]>([])

  /* Refs for mutable state used by intervals/callbacks */
  const photosRef = useRef<Photo[]>([])
  const layoutRef = useRef<BentoLayout | null>(null)
  const layoutIdxRef = useRef(-1)
  const deviceLayoutsRef = useRef<BentoLayout[]>(DESKTOP_LAYOUTS)

  /* Preload buffer: ready-to-swap photos per orientation, already in browser cache */
  const preloadBufferRef = useRef<{ P: Photo[]; L: Photo[] }>({ P: [], L: [] })
  const PRELOAD_COUNT = 6 // per orientation

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

  /* Generate a fresh bento (random layout + fill) */
  const generate = useCallback(() => {
    if (!data) return
    const { layout: newLayout, idx, layouts } = pickLayout()
    const selected = fillBento(data.photos, newLayout)
    deviceLayoutsRef.current = layouts
    setLayout(newLayout)
    setLayoutIdx(idx)
    setPhotos(selected)
    // Refill preload buffer after render
    requestAnimationFrame(() => refillPreloadBuffer(new Set(selected.map(p => p.id))))
  }, [data, refillPreloadBuffer])

  /* Generate with a specific layout index from the current device library */
  const generateWithLayout = useCallback((idx: number) => {
    if (!data) return
    const layouts = getLayoutsForDevice()
    deviceLayoutsRef.current = layouts
    const newLayout = layouts[idx % layouts.length]
    const selected = fillBento(data.photos, newLayout)
    setLayout(newLayout)
    setLayoutIdx(idx % layouts.length)
    setPhotos(selected)
    requestAnimationFrame(() => refillPreloadBuffer(new Set(selected.map(p => p.id))))
  }, [data, refillPreloadBuffer])

  /* Cycle layouts with arrow keys */
  const cycle = useCallback((dir: number) => {
    const layouts = deviceLayoutsRef.current
    const newIdx = (layoutIdxRef.current + dir + layouts.length) % layouts.length
    generateWithLayout(newIdx)
  }, [generateWithLayout])

  /* Swap a single tile — instant, no fade. Image is pre-cached. */
  const swapTile = useCallback((tileEl: HTMLDivElement) => {
    if (!data) return
    const oldId = tileEl.dataset.id
    const orient = tileEl.dataset.orient as 'P' | 'L' | undefined
    const cellIdx = parseInt(tileEl.dataset.cellIdx || '0', 10)

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
      let pool = data.photos.filter(p => p.thumb && p.display && p.aesthetic && !currentIds.has(p.id))
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
  }, [data, refillPreloadBuffer])

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
      let pool = data.photos.filter(p => p.thumb && p.display && p.aesthetic && !currentIds.has(p.id))
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
    registerTimer(id)
    return () => clearInterval(id)
  }, [crossfadeOneTile, registerTimer])

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

  if (!layout || photos.length === 0) {
    return <div className="bento-wrap" />
  }

  const isMobile = layout.device === 'mobile'
  const containerRatio = layout.cols * BENTO_UNIT_RATIO / layout.rows

  return (
    <div
      className={`bento-wrap${isMobile ? ' bento-mobile' : ''}`}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <div
        className="bento-grid"
        style={{
          '--bento-cols': layout.cols,
          '--bento-rows': layout.rows,
          aspectRatio: isMobile ? containerRatio : undefined,
          width: isMobile ? undefined : `calc(67dvh * ${containerRatio})`,
        } as React.CSSProperties}
      >
        {photos.map((photo, i) => {
          const cell = layout.cells[i]
          if (!cell || !photo) return null
          return (
            <BentoTile
              key={i}
              photo={photo}
              cell={cell}
              cellIndex={i}
              index={i}
              onSwap={swapTile}
              onFullscreen={handleFullscreen}
            />
          )
        })}
      </div>
      <ViewBottom>
        <ActionButton emoji="&#x1F3B2;" onClick={generate} label="Shuffle" />
      </ViewBottom>
    </div>
  )
}
