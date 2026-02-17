import { useState, useEffect, useCallback, useRef } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { getObjectPosition } from '../lib/cropUtils'
import { randomFrom } from '../lib/utils'
import { ViewBottom } from '../components/ui/ViewBottom'
import type { Photo } from '../types/photo'
import type { BentoCell } from '../lib/cropUtils'
import './ColorsView.css'

const NUM_BUCKETS = 24

interface ColorBucket {
  hueStart: number
  hueEnd: number
  color: string
  photos: Photo[]
}

interface ColorsLayout {
  cols: number
  rows: number
  count: number
  cells: BentoCell[]
  colTpl: string  // grid-template-columns
  rowTpl: string  // grid-template-rows
}

/** Portrait cell: rs > cs (tall) */
function P(r: number, c: number, rs: number, cs: number): BentoCell {
  return { r, c, rs, cs, orient: 'P' }
}

/** Landscape cell: cs >= rs (wide or square) */
function L(r: number, c: number, rs: number, cs: number): BentoCell {
  return { r, c, rs, cs, orient: 'L' }
}

/*
 * Layout track sizing rationale (desktop, 3:2 container):
 *   Portrait column = 16fr, landscape column = 9fr
 *   Portrait rows = 9fr each, bottom row = 7fr (or 8fr)
 *
 *   Portrait cell (1 col × 2 rows): exact 2:3 aspect
 *   Landscape cell (2 cols × 1 row): exact 3:2 aspect
 *   1×1 cells in landscape cols: ~square; in portrait cols: ~3:2 landscape
 */

const DESKTOP_LAYOUTS: ColorsLayout[] = [
  /* D1: 4×3, 8 photos (2P + 6L) — symmetric portraits */
  {
    cols: 4, rows: 3, count: 8,
    colTpl: '16fr 9fr 9fr 16fr',
    rowTpl: '9fr 9fr 7fr',
    cells: [
      P(1,1,2,1), L(1,2,1,2), P(1,4,2,1),
      L(2,2,1,1), L(2,3,1,1),
      L(3,1,1,1), L(3,2,1,2), L(3,4,1,1),
    ],
  },
  /* D2: 5×3, 10 photos (1P + 9L) — single portrait left */
  {
    cols: 5, rows: 3, count: 10,
    colTpl: '16fr 9fr 9fr 9fr 9fr',
    rowTpl: '9fr 9fr 8fr',
    cells: [
      P(1,1,2,1), L(1,2,1,2), L(1,4,1,2),
      L(2,2,1,2), L(2,4,1,2),
      L(3,1,1,1), L(3,2,1,1), L(3,3,1,1), L(3,4,1,1), L(3,5,1,1),
    ],
  },
  /* D3: 4×3, 8 photos (2P + 6L) — symmetric portraits, wide center */
  {
    cols: 4, rows: 3, count: 8,
    colTpl: '16fr 9fr 9fr 16fr',
    rowTpl: '9fr 9fr 7fr',
    cells: [
      P(1,1,2,1), L(1,2,1,2), P(1,4,2,1),
      L(2,2,1,2),
      L(3,1,1,1), L(3,2,1,1), L(3,3,1,1), L(3,4,1,1),
    ],
  },
]

/*
 * Mobile track sizing (2:3 container):
 *   Portrait column = 16fr, landscape columns = 9fr each
 *   Portrait cells ~0.63 aspect (close to 2:3)
 *   Landscape 2-col cells ~1.41 aspect (close to 3:2)
 */

const MOBILE_LAYOUTS: ColorsLayout[] = [
  /* M1: 3×4, 8 photos (2P + 6L) — portraits right */
  {
    cols: 3, rows: 4, count: 8,
    colTpl: '9fr 9fr 16fr',
    rowTpl: '1fr 1fr 1fr 1fr',
    cells: [
      L(1,1,1,2), P(1,3,2,1),
      L(2,1,1,1), L(2,2,1,1),
      L(3,1,1,2), P(3,3,2,1),
      L(4,1,1,1), L(4,2,1,1),
    ],
  },
  /* M2: 3×5, 10 photos (2P + 8L) — portraits right, extra row */
  {
    cols: 3, rows: 5, count: 10,
    colTpl: '9fr 9fr 16fr',
    rowTpl: '1fr 1fr 1fr 1fr 1fr',
    cells: [
      L(1,1,1,2), P(1,3,2,1),
      L(2,1,1,1), L(2,2,1,1),
      L(3,1,1,2), P(3,3,2,1),
      L(4,1,1,1), L(4,2,1,1),
      L(5,1,1,2), L(5,3,1,1),
    ],
  },
  /* M3: 3×4, 8 photos (2P + 6L) — portraits left */
  {
    cols: 3, rows: 4, count: 8,
    colTpl: '16fr 9fr 9fr',
    rowTpl: '1fr 1fr 1fr 1fr',
    cells: [
      P(1,1,2,1), L(1,2,1,2),
      L(2,2,1,1), L(2,3,1,1),
      P(3,1,2,1), L(3,2,1,2),
      L(4,2,1,1), L(4,3,1,1),
    ],
  },
]

/* ===== Color bucketing ===== */

function isGrayPalette(palette?: string[]): boolean {
  if (!palette || palette.length === 0) return false
  return palette.every(hex => {
    if (!hex || hex.length < 7) return true
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    return (Math.max(r, g, b) - Math.min(r, g, b)) < 30
  })
}

function buildColorBuckets(photos: Photo[]): ColorBucket[] {
  const bucketSize = 360 / NUM_BUCKETS
  const buckets: ColorBucket[] = []

  for (let i = 0; i < NUM_BUCKETS; i++) {
    const hueStart = i * bucketSize
    const hueMid = hueStart + bucketSize / 2
    buckets.push({
      hueStart,
      hueEnd: hueStart + bucketSize,
      color: `hsl(${hueMid}, 65%, 50%)`,
      photos: [],
    })
  }

  const grayPhotos: Photo[] = []
  for (const photo of photos) {
    if (!photo.thumb) continue
    if (photo.has_border) continue
    if (isGrayPalette(photo.palette)) {
      grayPhotos.push(photo)
      continue
    }
    const hue = photo.hue || 0
    const idx = Math.min(Math.floor(hue / bucketSize), NUM_BUCKETS - 1)
    buckets[idx].photos.push(photo)
  }

  if (grayPhotos.length > 0) {
    buckets.push({
      hueStart: -1,
      hueEnd: -1,
      color: '#8e8e93',
      photos: grayPhotos,
    })
  }

  return buckets
}

/* ===== Device detection ===== */

function isPortrait(): boolean {
  return typeof window !== 'undefined' && window.innerWidth < window.innerHeight
}

/* ===== Orientation-aware photo filling ===== */

function fillColorsLayout(
  bucket: ColorBucket,
  allBuckets: ColorBucket[],
  activeIdx: number,
  layout: ColorsLayout,
): Photo[] {
  const candidates: Photo[] = [...bucket.photos]
  const usedIds = new Set(candidates.map(p => p.id))

  // Borrow from adjacent buckets if the primary bucket is small
  for (let offset = 1; offset <= 3 && candidates.length < layout.count * 2; offset++) {
    for (const dir of [-1, 1]) {
      const adjIdx = (activeIdx + dir * offset + allBuckets.length) % allBuckets.length
      const adj = allBuckets[adjIdx]
      if (!adj) continue
      const adjSorted = [...adj.photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))
      for (const p of adjSorted) {
        if (!usedIds.has(p.id)) {
          candidates.push(p)
          usedIds.add(p.id)
        }
      }
    }
  }

  const sorted = [...candidates].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))
  const portraitPool = sorted.filter(p => p.orientation === 'portrait')
  const landscapePool = sorted.filter(p => p.orientation === 'landscape' || p.orientation === 'square')

  const selected: Photo[] = []
  const pickedIds = new Set<string>()

  for (const cell of layout.cells) {
    const primary = cell.orient === 'P' ? portraitPool : landscapePool
    const fallback = cell.orient === 'P' ? landscapePool : portraitPool

    let pick = primary.find(p => !pickedIds.has(p.id))
    if (!pick) pick = fallback.find(p => !pickedIds.has(p.id))
    if (!pick) break

    selected.push(pick)
    pickedIds.add(pick.id)
  }

  return selected
}

/* ===== CouleursTile component ===== */

function CouleursTile({ photo, cell, index, onClick }: {
  photo: Photo; cell: BentoCell; index: number; onClick: () => void
}) {
  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (!el) return
    loadProgressive(el, photo, 'display')
    el.style.objectPosition = getObjectPosition(photo, cell)
  }, [photo, cell])

  return (
    <div
      className="couleurs-tile"
      style={{
        gridRow: `${cell.r} / ${cell.r + cell.rs}`,
        gridColumn: `${cell.c} / ${cell.c + cell.cs}`,
        backgroundColor: (photo.palette?.[2] || photo.palette?.[0] || '') + '4D',
        '--i': index,
      } as React.CSSProperties}
      onClick={onClick}
    >
      <img ref={imgRef} alt="" />
    </div>
  )
}

/* ===== ColorsView component ===== */

export function ColorsView() {
  const data = useAppStore(s => s.data)
  const openLightbox = useAppStore(s => s.openLightbox)
  const [buckets, setBuckets] = useState<ColorBucket[]>([])
  const [activeIdx, setActiveIdx] = useState(0)
  const [selected, setSelected] = useState<Photo[]>([])
  const [layout, setLayout] = useState<ColorsLayout | null>(null)
  const [portrait, setPortrait] = useState(isPortrait)
  const layoutCycleRef = useRef(0)
  const prevPortraitRef = useRef(portrait)

  // Build color buckets once
  useEffect(() => {
    if (!data) return
    const b = buildColorBuckets(data.photos)
    setBuckets(b)
    const nonEmpty = b.map((bucket, i) => ({ bucket, i })).filter(x => x.bucket.photos.length > 0)
    const startIdx = nonEmpty.length > 0 ? randomFrom(nonEmpty).i : 0
    setActiveIdx(startIdx)
  }, [data])

  // Select photos when bucket or orientation changes
  useEffect(() => {
    if (buckets.length === 0) return

    // Reset layout cycle on orientation change
    if (prevPortraitRef.current !== portrait) {
      layoutCycleRef.current = 0
      prevPortraitRef.current = portrait
    }

    const bucket = buckets[activeIdx]
    if (!bucket || bucket.photos.length === 0) {
      setSelected([])
      setLayout(null)
      return
    }

    const layouts = portrait ? MOBILE_LAYOUTS : DESKTOP_LAYOUTS
    const newLayout = layouts[layoutCycleRef.current % layouts.length]
    layoutCycleRef.current++

    const picks = fillColorsLayout(bucket, buckets, activeIdx, newLayout)
    setLayout(newLayout)
    setSelected(picks)
  }, [buckets, activeIdx, portrait])

  // Orientation change listener
  useEffect(() => {
    const onResize = () => setPortrait(isPortrait())
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const selectBand = useCallback((idx: number) => {
    setActiveIdx(idx)
  }, [])

  return (
    <div className="couleurs-wrap">
      <div
        className="couleurs-card"
        id="couleurs-card"
        key={activeIdx}
        style={layout ? {
          gridTemplateColumns: layout.colTpl,
          gridTemplateRows: layout.rowTpl,
        } : undefined}
      >
        {!layout || selected.length === 0 ? (
          <div className="couleurs-empty">
            No photos in this range
          </div>
        ) : (
          selected.map((photo, i) => {
            const cell = layout.cells[i]
            if (!cell || !photo) return null
            return (
              <CouleursTile
                key={photo.id}
                photo={photo}
                cell={cell}
                index={i}
                onClick={() => openLightbox(photo, selected)}
              />
            )
          })
        )}
      </div>
      <ViewBottom className="couleurs-bottom">
        <div className="couleurs-spectrum" id="couleurs-spectrum">
          {buckets.map((bucket, i) => (
            <div
              key={i}
              className={`couleurs-band${i === activeIdx ? ' active' : ''}`}
              style={{ background: bucket.color }}
              onClick={() => selectBand(i)}
            />
          ))}
        </div>
      </ViewBottom>
    </div>
  )
}
