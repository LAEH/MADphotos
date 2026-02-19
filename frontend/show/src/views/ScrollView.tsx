import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive, optimalTier } from '../lib/imageLoading'
import type { Photo } from '../types/photo'
import './ScrollView.css'

/* ===== Filter helpers ===== */

function objHas(p: Photo, ...labels: string[]): boolean {
  if (!p.objects) return false
  return p.objects.some(o => {
    const lower = o.toLowerCase()
    return labels.some(l => lower === l || lower.includes(l))
  })
}

function vibeHas(p: Photo, ...vibes: string[]): boolean {
  if (!p.vibes) return false
  return p.vibes.some(v => {
    const lower = v.toLowerCase()
    return vibes.some(t => lower.includes(t))
  })
}

function sceneHas(p: Photo, ...terms: string[]): boolean {
  if (!p.scene) return false
  const lower = p.scene.toLowerCase()
  return terms.some(t => lower.includes(t))
}

function timeIs(p: Photo, ...terms: string[]): boolean {
  if (!p.time) return false
  const lower = p.time.toLowerCase()
  return terms.some(t => lower.includes(t))
}

/* ===== Row theme definitions ===== */

interface RowDef {
  label: string
  pool: (p: Photo) => boolean
}

/* Ordered for maximum visual contrast between adjacent rows */
const ROW_DEFS: RowDef[] = [
  { label: 'Chats',       pool: p => objHas(p, 'cat') },
  { label: 'Nuit',        pool: p => timeIs(p, 'night') },
  { label: 'Dor\u00E9',        pool: p => timeIs(p, 'golden hour') },
  { label: 'Sombre',      pool: p => vibeHas(p, 'dark', 'moody', 'somber', 'melancholic') },
  { label: 'Oc\u00E9an',       pool: p => sceneHas(p, 'ocean', 'beach', 'sea', 'lake', 'river', 'waterfall') },
  { label: 'For\u00EAt',       pool: p => sceneHas(p, 'forest', 'jungle', 'woods') },
  { label: 'Rue',         pool: p => sceneHas(p, 'street', 'alley', 'crosswalk', 'sidewalk') },
  { label: 'Bleu',        pool: p => timeIs(p, 'blue hour', 'dusk') },
  { label: 'Canin',       pool: p => objHas(p, 'dog') },
  { label: 'Serein',      pool: p => vibeHas(p, 'serene', 'calm', 'peaceful', 'tranquil', 'zen') },
  { label: 'Int\u00E9rieur',   pool: p => sceneHas(p, 'interior', 'restaurant', 'bar', 'shop', 'caf') },
  { label: 'Ciel',        pool: p => sceneHas(p, 'sky', 'rooftop', 'aerial', 'balcony') },
  { label: 'March\u00E9',      pool: p => sceneHas(p, 'market', 'store', 'stall') },
  { label: 'Vibrant',     pool: p => vibeHas(p, 'vibrant', 'energetic', 'lively', 'colorful') },
  { label: 'Voyage',      pool: p => sceneHas(p, 'airport', 'train', 'highway', 'bridge', 'port') },
]

const ROW_MAX = 10
const ROW_MIN = 3

/* ===== Color helpers ===== */

function hexToRgb(hex: string): [number, number, number] | null {
  if (!hex || hex.length < 7) return null
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  if (isNaN(r) || isNaN(g) || isNaN(b)) return null
  return [r, g, b]
}

function hexToHue(hex: string): number | null {
  const rgb = hexToRgb(hex)
  if (!rgb) return null
  const [r, g, b] = rgb.map(v => v / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const d = max - min
  if (d < 0.08) return null /* achromatic */
  if (max === 0 || d / max < 0.15) return null /* too desaturated */
  let h = 0
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6
  else if (max === g) h = ((b - r) / d + 2) / 6
  else h = ((r - g) / d + 4) / 6
  return h * 360
}

function paletteInHue(p: Photo, minH: number, maxH: number): boolean {
  if (!p.palette?.[0]) return false
  const hue = hexToHue(p.palette[0])
  if (hue === null) return false
  if (minH > maxH) return hue >= minH || hue <= maxH
  return hue >= minH && hue <= maxH
}

/* ===== Color row definitions ===== */

const COLOR_ROW_DEFS: RowDef[] = [
  { label: 'Rouge',  pool: p => paletteInHue(p, 345, 15) },
  { label: 'Bleu',   pool: p => paletteInHue(p, 190, 250) },
  { label: 'Vert',   pool: p => paletteInHue(p, 80, 160) },
  { label: 'Violet', pool: p => paletteInHue(p, 260, 320) },
  { label: 'Ambre',  pool: p => paletteInHue(p, 20, 50) },
]

/* ===== Build row data ===== */

interface RowData {
  label: string
  photos: Photo[]
  tintRgb: [number, number, number] | null
  colorRow?: boolean
}

function buildRows(photos: Photo[]): RowData[] {
  const isMobile = window.innerWidth < window.innerHeight
  const orient = isMobile ? 'portrait' : 'landscape'
  const pool = photos.filter(p => p.thumb && p.orientation === orient)
  const used = new Set<string>()

  /* Build regular rows */
  const regular: RowData[] = []
  for (const def of ROW_DEFS) {
    const matches = pool.filter(p => !used.has(p.id) && def.pool(p))
    if (matches.length < ROW_MIN) continue
    const sorted = [...matches].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))
    const sliced = sorted.slice(0, ROW_MAX)
    for (const p of sliced) used.add(p.id)
    const tintRgb = sliced[0]?.palette?.[0] ? hexToRgb(sliced[0].palette[0]) : null
    regular.push({ label: def.label, photos: sliced, tintRgb })
  }

  /* Build color rows */
  const colors: RowData[] = []
  for (const def of COLOR_ROW_DEFS) {
    const matches = pool.filter(p => !used.has(p.id) && def.pool(p))
    if (matches.length < ROW_MIN) continue
    const sorted = [...matches].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))
    const sliced = sorted.slice(0, ROW_MAX)
    for (const p of sliced) used.add(p.id)
    const tintRgb = sliced[0]?.palette?.[0] ? hexToRgb(sliced[0].palette[0]) : null
    colors.push({ label: def.label, photos: sliced, tintRgb, colorRow: true })
  }

  /* Interleave: 2 regular, 1 color, repeat */
  const result: RowData[] = []
  let ri = 0, ci = 0
  while (ri < regular.length || ci < colors.length) {
    if (ri < regular.length) result.push(regular[ri++])
    if (ri < regular.length) result.push(regular[ri++])
    if (ci < colors.length) result.push(colors[ci++])
  }

  return result
}

/* ===== Row background style ===== */

function rowBgStyle(row: RowData, isLight: boolean): React.CSSProperties {
  const { tintRgb: rgb, colorRow } = row

  /* Color rows: rich saturated background */
  if (colorRow && rgb) {
    const [r, g, b] = rgb
    return {
      background: [
        `radial-gradient(ellipse at 30% 40%, rgba(${r},${g},${b},0.55) 0%, transparent 65%)`,
        `radial-gradient(ellipse at 70% 60%, rgba(${r},${g},${b},0.35) 0%, transparent 60%)`,
        `linear-gradient(to bottom, rgba(${r},${g},${b},0.25) 0%, rgba(${r},${g},${b},0.40) 100%)`,
        `rgb(${Math.round(r * 0.12)},${Math.round(g * 0.12)},${Math.round(b * 0.12)})`,
      ].join(', '),
    }
  }

  /* Regular rows: alternate white / black */
  const base = isLight ? '#ffffff' : '#000000'

  if (!rgb) return { background: base }

  const [r, g, b] = rgb
  if (!isLight) {
    return {
      background: [
        `radial-gradient(ellipse at 30% 40%, rgba(${r},${g},${b},0.25) 0%, transparent 60%)`,
        `radial-gradient(ellipse at 70% 60%, rgba(${r},${g},${b},0.15) 0%, transparent 55%)`,
        `linear-gradient(135deg, rgba(${r},${g},${b},0.08) 0%, transparent 50%)`,
        base,
      ].join(', '),
    }
  }

  return {
    background: [
      `radial-gradient(ellipse at 30% 40%, rgba(${r},${g},${b},0.18) 0%, transparent 60%)`,
      `radial-gradient(ellipse at 70% 60%, rgba(${r},${g},${b},0.10) 0%, transparent 55%)`,
      `linear-gradient(135deg, rgba(${r},${g},${b},0.05) 0%, transparent 50%)`,
      base,
    ].join(', '),
  }
}

/* ===== Labels helpers ===== */

interface LabelEntry {
  label: string
  category: string
  confidence?: number
}

interface LabelsMap {
  [photoId: string]: { labels?: LabelEntry[] }
}

function pickBestLabels(photos: Photo[], labelsMap: LabelsMap | null, count: number): LabelEntry[] {
  if (!labelsMap) return []
  const seen = new Set<string>()
  const result: LabelEntry[] = []

  for (const photo of photos) {
    const entry = labelsMap[photo.id]
    if (!entry?.labels) continue
    for (const l of entry.labels) {
      const key = l.label.toLowerCase()
      if (!seen.has(key)) {
        seen.add(key)
        result.push(l)
        if (result.length >= count) return result
      }
    }
  }
  return result
}

interface GemmaEntry {
  story?: string
  stories?: { poetic?: string; noir?: string; romantic?: string; silly?: string; surrealist?: string }
  mood?: string
}

interface GemmaMap {
  [photoId: string]: GemmaEntry
}

function bestCaption(photos: Photo[], gemmaMap: GemmaMap | null): string {
  if (gemmaMap) {
    for (const p of photos) {
      const g = gemmaMap[p.id]
      if (g?.stories?.poetic) return g.stories.poetic
      if (g?.story) return g.story
    }
  }
  for (const p of photos) {
    if (p.best_caption) return p.best_caption
  }
  return ''
}

/* ===== ScrollView component ===== */

export function ScrollView() {
  const data = useAppStore(s => s.data)
  const [rows, setRows] = useState<RowData[]>([])
  const [activeRow, setActiveRow] = useState(0)
  const [activeSlides, setActiveSlides] = useState<Record<number, number>>({})
  const [labelsMap, setLabelsMap] = useState<LabelsMap | null>(null)
  const [gemmaMap, setGemmaMap] = useState<GemmaMap | null>(null)

  const rowsContainerRef = useRef<HTMLDivElement>(null)
  const slideContainersRef = useRef<(HTMLDivElement | null)[]>([])

  /* Read user's theme preference — first row matches it */
  const isDark = document.documentElement.classList.contains('dark')

  /* Viewport lock */
  useEffect(() => {
    const html = document.documentElement
    const body = document.body
    html.style.overflow = 'hidden'
    body.style.overflow = 'hidden'
    return () => {
      html.style.overflow = ''
      body.style.overflow = ''
    }
  }, [])

  /* Load labels + gemma data */
  useEffect(() => {
    fetch('/data/photo_labels.json?v=' + Date.now())
      .then(r => r.json())
      .then(d => setLabelsMap(d))
      .catch(() => setLabelsMap({}))
    fetch('/data/gemma_picks.json?v=' + Date.now())
      .then(r => r.json())
      .then(d => setGemmaMap(d))
      .catch(() => setGemmaMap({}))
  }, [])

  /* Build rows from data */
  useEffect(() => {
    if (!data) return
    const built = buildRows(data.photos)
    setRows(built)
    const initial: Record<number, number> = {}
    built.forEach((_, i) => { initial[i] = 0 })
    setActiveSlides(initial)
  }, [data])

  /* Observe active row (vertical scroll) */
  useEffect(() => {
    const container = rowsContainerRef.current
    if (!container || rows.length === 0) return

    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio > 0.5) {
            const idx = Number(entry.target.getAttribute('data-row-idx'))
            if (!isNaN(idx)) setActiveRow(idx)
          }
        }
      },
      { root: container, threshold: 0.5 }
    )

    const rowEls = container.querySelectorAll('.scroll-row')
    rowEls.forEach(el => observer.observe(el))
    return () => observer.disconnect()
  }, [rows])

  /* Observe active slide (horizontal scroll) per row */
  useEffect(() => {
    if (rows.length === 0) return
    const observers: IntersectionObserver[] = []

    for (let rowIdx = 0; rowIdx < rows.length; rowIdx++) {
      const container = slideContainersRef.current[rowIdx]
      if (!container) continue

      const rIdx = rowIdx
      const observer = new IntersectionObserver(
        entries => {
          for (const entry of entries) {
            if (entry.isIntersecting && entry.intersectionRatio > 0.5) {
              const sIdx = Number(entry.target.getAttribute('data-slide-idx'))
              if (!isNaN(sIdx)) {
                setActiveSlides(prev => ({ ...prev, [rIdx]: sIdx }))
              }
            }
          }
        },
        { root: container, threshold: 0.5 }
      )

      const slideEls = container.querySelectorAll('.scroll-slide')
      slideEls.forEach(el => observer.observe(el))
      observers.push(observer)
    }

    return () => observers.forEach(o => o.disconnect())
  }, [rows])

  /* Keyboard navigation */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const container = rowsContainerRef.current
      if (!container) return

      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const rowEls = container.querySelectorAll('.scroll-row')
        const targetRow = e.key === 'ArrowDown'
          ? Math.min(activeRow + 1, rows.length - 1)
          : Math.max(activeRow - 1, 0)
        rowEls[targetRow]?.scrollIntoView({ behavior: 'smooth' })
      }

      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault()
        const slideContainer = slideContainersRef.current[activeRow]
        if (!slideContainer) return
        const slideEls = slideContainer.querySelectorAll('.scroll-slide')
        const currentSlide = activeSlides[activeRow] || 0
        const totalSlides = slideEls.length
        const targetSlide = e.key === 'ArrowRight'
          ? Math.min(currentSlide + 1, totalSlides - 1)
          : Math.max(currentSlide - 1, 0)
        slideEls[targetSlide]?.scrollIntoView({ behavior: 'smooth', inline: 'start' })
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [activeRow, activeSlides, rows.length])

  /* Build slides for a row — on mobile portrait, pair up landscape images */
  const buildSlides = useCallback((rowPhotos: Photo[], rowIdx: number): React.ReactNode[] => {
    const currentActive = activeSlides[rowIdx] || 0

    return rowPhotos.map((photo, i) => (
      <ScrollSlide
        key={photo.id}
        photo={photo}
        slideIdx={i}
        rowIdx={rowIdx}
        isActive={i === currentActive}
        labelsMap={labelsMap} gemmaMap={gemmaMap}
      />
    ))
  }, [activeSlides, labelsMap, gemmaMap])

  /* Count slides for dot indicators */
  const slideCounts = useMemo(() => {
    return rows.map(row => row.photos.length)
  }, [rows])

  if (rows.length === 0) return null

  return (
    <div className="scroll-wrap">
      <div className="scroll-rows" ref={rowsContainerRef}>
        {rows.map((row, rowIdx) => {
          /* lightIdx counts only non-color rows for alternation */
          const lightIdx = rows.slice(0, rowIdx).filter(r => !r.colorRow).length
          /* First regular row matches user's theme; isDark flips the alternation */
          const isLight = isDark ? (lightIdx % 2 !== 0) : (lightIdx % 2 === 0)
          const themeClass = row.colorRow
            ? ' scroll-row-dark scroll-row-color'
            : (isLight ? ' scroll-row-light' : ' scroll-row-dark')

          return (
          <div
            key={row.label}
            className={'scroll-row' + themeClass + (rowIdx === 0 ? ' scroll-row-first' : '')}
            data-row-idx={rowIdx}
          >
            <div className="scroll-row-bg" style={rowBgStyle(row, isLight)} />
            <div
              className="scroll-slides"
              ref={el => { slideContainersRef.current[rowIdx] = el }}
            >
              {buildSlides(row.photos, rowIdx)}
            </div>
            {slideCounts[rowIdx] > 1 && (
              <div className="scroll-dots-h">
                {Array.from({ length: slideCounts[rowIdx] }, (_, i) => (
                  <div
                    key={i}
                    className={'scroll-dot-h' + (i === (activeSlides[rowIdx] || 0) ? ' active' : '')}
                  />
                ))}
              </div>
            )}
            {rowIdx < rows.length - 1 && (
              <div className="scroll-hint-down">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 8l5 5 5-5" />
                </svg>
              </div>
            )}
          </div>
          )
        })}
      </div>

      {rows.length > 1 && (
        <div className="scroll-dots-v">
          {rows.map((_, i) => (
            <div
              key={i}
              className={'scroll-dot-v' + (i === activeRow ? ' active' : '')}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/* ===== Photo info (camera + caption + predicted labels) ===== */

function PhotoInfo({ photos, labelsMap, gemmaMap }: { photos: Photo[]; labelsMap: LabelsMap | null; gemmaMap: GemmaMap | null }) {
  const photo = photos[0]
  const caption = bestCaption(photos, gemmaMap)
  const labels = pickBestLabels(photos, labelsMap, 3)
  const camera = photo?.camera || null

  if (!caption && labels.length === 0 && !camera) return null

  return (
    <div className="scroll-info">
      {caption && <p className="scroll-caption">{caption}</p>}
      {(camera || labels.length > 0) && (
        <div className="scroll-labels">
          {camera && <span className="scroll-camera">{camera}</span>}
          {labels.map(l => (
            <span key={l.label} className="scroll-label">{l.label}</span>
          ))}
        </div>
      )}
    </div>
  )
}

/* ===== Single image slide ===== */

interface ScrollSlideProps {
  photo: Photo
  slideIdx: number
  rowIdx: number
  isActive: boolean
  labelsMap: LabelsMap | null
  gemmaMap: GemmaMap | null
}

function ScrollSlide({ photo, slideIdx, isActive, labelsMap, gemmaMap }: ScrollSlideProps) {
  const tier = useMemo(() => optimalTier('full'), [])

  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (el) loadProgressive(el, photo, tier, '100vw')
  }, [photo, tier])

  return (
    <div className={'scroll-slide' + (isActive ? ' scroll-slide-active' : '')} data-slide-idx={slideIdx}>
      <div className="scroll-slide-content">
        <div className="scroll-image-wrap">
          <img ref={imgRef} alt={photo.caption || photo.alt || ''} />
        </div>
        <PhotoInfo photos={[photo]} labelsMap={labelsMap} gemmaMap={gemmaMap} />
      </div>
    </div>
  )
}

