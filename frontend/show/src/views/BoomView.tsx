import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { shuffleArray } from '../lib/utils'
import { hexToHue } from '../lib/colorUtils'
import { filterByImageType } from '../lib/layoutRegistry'
import { ShowControls } from '../components/controls/ShowControls'
import type { ImageTypeFilter } from '../lib/layoutRegistry'
import type { Photo, DriftNeighbor } from '../types/photo'
import './BoomView.css'

/* ===== Filter helpers ===== */

function hueRange(photo: Photo, lo: number, hi: number): boolean {
  if (!photo.palette || !photo.palette[0]) return false
  const h = hexToHue(photo.palette[0])
  if (h < 0) return false
  if (lo <= hi) return h >= lo && h <= hi
  return h >= lo || h <= hi
}

function objHas(photo: Photo, ...labels: string[]): boolean {
  if (!photo.objects) return false
  return photo.objects.some(o => {
    const lower = o.toLowerCase()
    return labels.some(l => lower === l || lower.includes(l))
  })
}

function vibeHas(photo: Photo, ...vibes: string[]): boolean {
  if (!photo.vibes) return false
  return photo.vibes.some(v => {
    const lower = v.toLowerCase()
    return vibes.some(t => lower.includes(t))
  })
}

function sceneIn(photo: Photo, ...scenes: string[]): boolean {
  return !!photo.scene && scenes.includes(photo.scene)
}

function consensusHas(photo: Photo, ...tags: string[]): boolean {
  return (photo.consensus || []).some(c => tags.includes(c))
}

function archetypeIs(photo: Photo, ...archetypes: string[]): boolean {
  return !!photo.gc_archetype && archetypes.includes(photo.gc_archetype)
}

function energyIs(photo: Photo, ...energies: string[]): boolean {
  return !!photo.gc_energy && energies.includes(photo.gc_energy)
}

function gemmaVibeHas(photo: Photo, ...vibes: string[]): boolean {
  if (!photo.gemma_vibes) return false
  return photo.gemma_vibes.some(v => vibes.some(t => v.toLowerCase().includes(t)))
}

/* ===== Set definitions ===== */

interface BoomDef {
  emoji: string
  label: string
  pool: (p: Photo) => boolean
}

const BOOM_DEFS: BoomDef[] = [
  /* Color sets -- dominant palette hue */
  { emoji: '\uD83C\uDF39', label: 'Rouge',     pool: p => hueRange(p, 355, 25) },
  { emoji: '\uD83C\uDF4A', label: 'Ambre',     pool: p => hueRange(p, 20, 40) },
  { emoji: '\uD83C\uDF4B', label: 'Or',        pool: p => hueRange(p, 42, 62) },
  { emoji: '\uD83C\uDF40', label: '\u00C9meraude', pool: p => hueRange(p, 100, 165) },
  { emoji: '\uD83E\uDD8B', label: 'Azur',      pool: p => hueRange(p, 195, 250) },
  { emoji: '\uD83D\uDD2E', label: 'Am\u00E9thyste', pool: p => hueRange(p, 260, 315) },

  /* Time sets */
  { emoji: '\uD83C\uDF05', label: 'Dor\u00E9',       pool: p => p.time === 'golden hour' },
  { emoji: '\uD83C\uDF19', label: 'Nuit',       pool: p => p.time === 'night' },
  { emoji: '\uD83C\uDF0A', label: 'Cr\u00E9puscule',  pool: p => p.time === 'blue hour' },

  /* Object sets */
  { emoji: '\uD83D\uDC31', label: 'Chats',     pool: p => objHas(p, 'cat') },
  { emoji: '\uD83D\uDC15', label: 'Chiens',    pool: p => objHas(p, 'dog') },
  { emoji: '\uD83D\uDE97', label: 'Routes',    pool: p => objHas(p, 'car', 'truck', 'bus', 'motorcycle') },
  { emoji: '\uD83C\uDF3F', label: 'Flore',     pool: p => objHas(p, 'potted plant', 'vase') },
  { emoji: '\uD83C\uDF7D\uFE0F', label: 'Table',    pool: p => objHas(p, 'dining table', 'bowl', 'cup', 'wine glass') },
  { emoji: '\uD83D\uDCDA', label: 'Int\u00E9rieur', pool: p => objHas(p, 'book', 'chair', 'couch', 'bed') },
  { emoji: '\u2602\uFE0F', label: 'Pluie',     pool: p => objHas(p, 'umbrella') },
  { emoji: '\uD83D\uDC64', label: 'Portraits', pool: p => objHas(p, 'person') && (p.style === 'portrait' || p.orientation === 'portrait') },

  /* Vibe sets */
  { emoji: '\uD83D\uDE0C', label: 'Serein',    pool: p => vibeHas(p, 'serene', 'calm', 'peaceful', 'tranquil') },
  { emoji: '\uD83D\uDD25', label: 'Intense',   pool: p => vibeHas(p, 'dramatic', 'intense', 'powerful', 'bold') },
  { emoji: '\u2728',       label: 'Onirique',  pool: p => vibeHas(p, 'ethereal', 'dreamy', 'magical', 'mystical') },
  { emoji: '\uD83D\uDDA4', label: 'Sombre',    pool: p => vibeHas(p, 'dark', 'moody', 'somber', 'melancholic') },
  { emoji: '\uD83C\uDF89', label: 'Vivace',    pool: p => vibeHas(p, 'vibrant', 'lively', 'energetic', 'joyful') },
  { emoji: '\uD83C\uDF3B', label: 'Nostalgique', pool: p => vibeHas(p, 'nostalgic', 'vintage', 'retro', 'timeless') },

  /* Camera sets */
  { emoji: '\uD83D\uDCF8', label: 'Leica M8',     pool: p => p.camera === 'Leica M8' },
  { emoji: '\uD83C\uDF9E\uFE0F', label: 'Film',        pool: p => p.camera === 'Leica MP' },
  { emoji: '\u26AA',       label: 'Monochrom',  pool: p => p.camera === 'Leica Monochrom' },
  { emoji: '\uD83C\uDFA5', label: 'Osmo',       pool: p => !!p.camera && p.camera.startsWith('DJI') },
  { emoji: '\uD83D\uDCF7', label: 'Canon',      pool: p => p.camera === 'Canon G12' },

  /* Style / grading sets */
  { emoji: '\uD83C\uDFAC', label: 'Cin\u00E9ma',      pool: p => p.grading === 'Cinematic' },
  { emoji: '\uD83C\uDF31', label: 'Naturel',     pool: p => p.grading === 'Natural' },
  { emoji: '\uD83C\uDFAD', label: 'Analogique',  pool: p => p.style === 'analog' },
  { emoji: '\uD83C\uDFDB\uFE0F', label: 'Architecture', pool: p => p.style === 'architecture' },
  { emoji: '\uD83D\uDDBC\uFE0F', label: 'Documentaire', pool: p => p.style === 'documentary' },

  /* Scene clusters */
  { emoji: '\uD83C\uDF03', label: 'Skyline',     pool: p => sceneIn(p, 'skyscraper', 'downtown', 'highway', 'bridge') },
  { emoji: '\uD83C\uDFE0', label: 'Dedans',      pool: p => sceneIn(p, 'indoor', 'pet shop', 'music studio', 'car interior', 'discotheque') },
  { emoji: '\uD83C\uDF19', label: 'Souterrain',  pool: p => sceneIn(p, 'catacomb', 'elevator shaft', 'jail cell', 'loading dock') },
  { emoji: '\uD83C\uDF3F', label: 'Dehors',      pool: p => sceneIn(p, 'outdoor', 'sky', 'zen garden', 'ice floe', 'construction site') },

  /* Brightness / mood */
  { emoji: '\uD83D\uDD6F\uFE0F', label: 'Clair-obscur', pool: p => (p.brightness || 128) < 40 },
  { emoji: '\u2600\uFE0F',       label: 'Lumi\u00E8re',    pool: p => (p.brightness || 128) > 140 },
  { emoji: '\u2B1B',       label: 'Monochrome', pool: p => p.mono === true },

  /* Consensus / semantic */
  { emoji: '\uD83E\uDE9E', label: 'Reflets',     pool: p => consensusHas(p, 'reflection') },
  { emoji: '\uD83D\uDC64', label: 'Silhouettes', pool: p => consensusHas(p, 'silhouette') },
  { emoji: '\uD83C\uDFA8', label: 'Mural',       pool: p => consensusHas(p, 'mural', 'graffiti') },

  /* Gemma composition archetypes */
  { emoji: '\uD83D\uDEAA', label: 'Portails',    pool: p => archetypeIs(p, 'portal') },
  { emoji: '\uD83C\uDF04', label: 'Horizons',    pool: p => archetypeIs(p, 'horizon', 'panorama') },
  { emoji: '\uD83E\uDDF1', label: 'Textures',    pool: p => archetypeIs(p, 'texture') },
  { emoji: '\uD83D\uDC64', label: 'Figures',     pool: p => archetypeIs(p, 'figure', 'silhouette') },
  { emoji: '\u25B3',       label: 'G\u00E9om\u00E9trie', pool: p => archetypeIs(p, 'geometry') },
  { emoji: '\u26AB',       label: 'Vide',        pool: p => archetypeIs(p, 'void') },
  { emoji: '\uD83C\uDF1F', label: 'Clusters',    pool: p => archetypeIs(p, 'cluster') },

  /* Gemma energy directions */
  { emoji: '\u2197\uFE0F', label: 'Diagonale',   pool: p => energyIs(p, 'diagonal_down', 'diagonal_up') },
  { emoji: '\u27A1\uFE0F', label: 'Flux',        pool: p => energyIs(p, 'left_to_right', 'right_to_left') },
  { emoji: '\uD83C\uDF00', label: 'Rayonnant',   pool: p => energyIs(p, 'center_out', 'inward') },
  { emoji: '\u23F8\uFE0F', label: 'Statique',    pool: p => energyIs(p, 'static') },

  /* Gemma vibes (richer vocabulary) */
  { emoji: '\uD83C\uDF0C', label: 'Myst\u00E9rieux',  pool: p => gemmaVibeHas(p, 'mysterious', 'enigmatic', 'cryptic') },
  { emoji: '\uD83C\uDF42', label: 'M\u00E9lancolie',   pool: p => gemmaVibeHas(p, 'melanchol', 'wistful', 'bittersweet') },
  { emoji: '\u2728',       label: 'Cin\u00E9matique',  pool: p => gemmaVibeHas(p, 'cinematic', 'filmic', 'dramatic') },
  { emoji: '\uD83C\uDF3E', label: 'Bucolique',   pool: p => gemmaVibeHas(p, 'pastoral', 'rustic', 'bucolic', 'rural') },
  { emoji: '\uD83C\uDFD9\uFE0F', label: 'Urbain',      pool: p => gemmaVibeHas(p, 'urban', 'gritty', 'industrial', 'concrete') },
  { emoji: '\uD83D\uDDBC\uFE0F', label: 'Imprim\u00E9',      pool: p => p.print_worthy === true },

  /* Gemma temperature */
  { emoji: '\uD83E\uDDCA', label: 'Glacial',     pool: p => p.gc_temp === 'glacial' || p.gc_temp === 'cool' },
  { emoji: '\uD83C\uDF0B', label: 'Brul\u00E2nt',      pool: p => p.gc_temp === 'molten' || p.gc_temp === 'warm' },
  { emoji: '\uD83D\uDCA0', label: 'N\u00E9on',         pool: p => p.gc_temp === 'neon' || p.gc_temp === 'electric' },

  /* AI variant set */
  { emoji: '\uD83C\uDFA8', label: 'Art IA',      pool: p => !!p.variant_type },
]

const BOOM_MIN = 25

/* ===== Color buckets for ShowControls ===== */

const BOOM_NUM_BUCKETS = 24

interface BoomColorBucket {
  color: string
  hueStart: number
  hueEnd: number
}

function buildBoomColorBuckets(): BoomColorBucket[] {
  const bucketSize = 360 / BOOM_NUM_BUCKETS
  const buckets: BoomColorBucket[] = []
  for (let i = 0; i < BOOM_NUM_BUCKETS; i++) {
    const hueStart = i * bucketSize
    const hueMid = hueStart + bucketSize / 2
    buckets.push({ hueStart, hueEnd: hueStart + bucketSize, color: `hsl(${hueMid}, 65%, 50%)` })
  }
  // Gray bucket
  buckets.push({ hueStart: -1, hueEnd: -1, color: '#8e8e93' })
  return buckets
}

function photoMatchesBucket(photo: Photo, bucket: BoomColorBucket): boolean {
  if (bucket.hueStart === -1) {
    // Gray: all palette entries are low-saturation
    const palette = photo.palette
    if (!palette || palette.length === 0) return false
    return palette.every(hex => {
      if (!hex || hex.length < 7) return true
      const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16)
      return (Math.max(r, g, b) - Math.min(r, g, b)) < 30
    })
  }
  const hue = photo.hue || 0
  if (bucket.hueStart <= bucket.hueEnd) return hue >= bucket.hueStart && hue < bucket.hueEnd
  return hue >= bucket.hueStart || hue < bucket.hueEnd
}

/* Grid dimensions for rectangular container (landscape desktop / portrait mobile) */
function computeGrid(n: number): { cols: number; rows: number } {
  const isLandscape = window.innerWidth >= window.innerHeight
  if (isLandscape) {
    if (n >= 70) return { cols: 10, rows: 7 }
    if (n >= 54) return { cols: 9, rows: 6 }
    if (n >= 40) return { cols: 8, rows: 5 }
    return { cols: 6, rows: 4 }
  } else {
    if (n >= 70) return { cols: 7, rows: 10 }
    if (n >= 54) return { cols: 6, rows: 9 }
    if (n >= 40) return { cols: 5, rows: 8 }
    return { cols: 4, rows: 6 }
  }
}

/* ===== Diversity sampling ===== */

interface BoomSet {
  emoji: string
  label: string
  photos: Photo[]
}

function diverseSample(
  pool: Photo[],
  count: number,
  neighbors: Record<string, DriftNeighbor[]> | null,
): Photo[] {
  if (pool.length <= count) return shuffleArray([...pool])

  const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))
  const candidates = sorted.slice(0, Math.min(pool.length, count * 5))
  const neighborMap = neighbors || {}

  const neighborIds: Record<string, Set<string>> = {}
  for (const c of candidates) {
    const nList = neighborMap[c.id]
    neighborIds[c.id] = nList
      ? new Set(nList.map(n => n.uuid || n.id || (n as unknown as string)))
      : new Set()
  }

  const selected: Photo[] = []
  const selIds = new Set<string>()
  const selScenes: Record<string, number> = {}
  const selVibes: Record<string, number> = {}
  const selHues: number[] = []

  function addToSelected(photo: Photo) {
    selected.push(photo)
    selIds.add(photo.id)
    const sc = photo.scene || ''
    selScenes[sc] = (selScenes[sc] || 0) + 1
    if (photo.vibes) {
      for (const v of photo.vibes) selVibes[v] = (selVibes[v] || 0) + 1
    }
    if (photo.palette && photo.palette[0]) {
      const h = hexToHue(photo.palette[0])
      if (h >= 0) selHues.push(h)
    }
  }

  addToSelected(candidates[0])

  while (selected.length < count) {
    let bestIdx = -1
    let bestScore = -Infinity

    for (let i = 0; i < candidates.length; i++) {
      const c = candidates[i]
      if (selIds.has(c.id)) continue

      let score = 0
      const cNeighbors = neighborIds[c.id]
      let neighborOverlap = 0
      if (cNeighbors && cNeighbors.size > 0) {
        for (const s of selected) {
          if (cNeighbors.has(s.id)) neighborOverlap++
          if (neighborIds[s.id] && neighborIds[s.id].has(c.id)) neighborOverlap++
        }
      }
      score -= neighborOverlap * 50

      const cScene = c.scene || ''
      score -= (selScenes[cScene] || 0) * 8

      if (c.vibes) {
        let vibeOverlap = 0
        for (const v of c.vibes) vibeOverlap += (selVibes[v] || 0)
        score -= vibeOverlap * 3
      }

      if (c.palette && c.palette[0]) {
        const h = hexToHue(c.palette[0])
        if (h >= 0 && selHues.length > 0) {
          let minDiff = 360
          for (const sh of selHues) {
            const diff = Math.abs(h - sh)
            minDiff = Math.min(minDiff, diff, 360 - diff)
          }
          score += Math.min(minDiff / 10, 5)
        }
      }

      score += (c.aesthetic || 0) * 2

      if (score > bestScore) {
        bestScore = score
        bestIdx = i
      }
    }

    if (bestIdx < 0) break
    addToSelected(candidates[bestIdx])
  }

  return selected
}

/* ===== Build sets from photo data ===== */

function buildBoomSets(
  photos: Photo[],
  neighbors: Record<string, DriftNeighbor[]> | null,
  targetDensity?: number,
): BoomSet[] {
  const pool = photos.filter(p => p.thumb)
  const sets: BoomSet[] = []
  const shuffledDefs = shuffleArray([...BOOM_DEFS])

  for (const def of shuffledDefs) {
    const matches = pool.filter(def.pool)
    if (matches.length < BOOM_MIN) continue

    /* Use target density if specified, otherwise adapt to pool size */
    const targetN = targetDensity || (
      matches.length >= 100 ? 70
      : matches.length >= 70 ? 54
      : matches.length >= 50 ? 40 : 24
    )
    const grid = computeGrid(targetN)
    const n = grid.cols * grid.rows

    sets.push({
      emoji: def.emoji,
      label: def.label,
      photos: diverseSample(matches, Math.min(n, matches.length), neighbors),
    })

    if (sets.length >= 24) break
  }

  return sets
}

/* ===== Scatter CSS custom properties for a cell ===== */

interface CellScatterProps {
  sx: string
  sy: string
  sr: string
  d: string
  dOut: string
}

function computeScatter(
  i: number,
  cols: number,
  _rows: number,
  cx: number,
  cy: number,
  maxDist: number,
): CellScatterProps {
  const col = i % cols
  const row = Math.floor(i / cols)
  const dist = Math.sqrt((col - cx) ** 2 + (row - cy) ** 2)

  const angle = Math.random() * Math.PI * 2
  const scatter = 300 + Math.random() * 500

  const delay = (dist / maxDist) * 700 + Math.random() * 150

  return {
    sx: (Math.cos(angle) * scatter).toFixed(0) + 'px',
    sy: (Math.sin(angle) * scatter).toFixed(0) + 'px',
    sr: ((Math.random() - 0.5) * 540).toFixed(0) + 'deg',
    d: delay.toFixed(0) + 'ms',
    dOut: (Math.random() * 250).toFixed(0) + 'ms',
  }
}

/* ===== BoomPreview component ===== */

interface BoomPreviewProps {
  photo: Photo | null
  onClose: () => void
}

function BoomPreview({ photo, onClose }: BoomPreviewProps) {
  const [isOpen, setIsOpen] = useState(false)

  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (el && photo) loadProgressive(el, photo, 'display', '100vw')
  }, [photo])

  /* Animate in after mount */
  useEffect(() => {
    if (photo) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setIsOpen(true))
      })
    } else {
      setIsOpen(false)
    }
  }, [photo])

  /* Escape key to close */
  useEffect(() => {
    if (!photo) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [photo, onClose])

  const handleClose = useCallback(() => {
    setIsOpen(false)
    setTimeout(onClose, 300)
  }, [onClose])

  if (!photo) return null

  return (
    <div className={`boom-preview${isOpen ? ' open' : ''}`}>
      <div className="boom-preview-backdrop" onClick={handleClose} />
      <img
        ref={imgRef}
        className="boom-preview-img"
        alt={photo.caption || photo.alt || ''}
      />
    </div>
  )
}

/* ===== BoomMosaic component ===== */

interface BoomMosaicProps {
  photos: Photo[]
  assembled: boolean
  scattering: boolean
  onCellClick: (photo: Photo) => void
}

function BoomMosaic({ photos, assembled, scattering, onCellClick }: BoomMosaicProps) {
  const shuffled = useRef<Photo[]>([])
  const scatterProps = useRef<CellScatterProps[]>([])

  const gridRef = useRef({ cols: 6, rows: 4 })

  /* Shuffle once when photos change */
  const [, setKey] = useState(0)
  useEffect(() => {
    shuffled.current = shuffleArray([...photos])
    const grid = computeGrid(shuffled.current.length)
    gridRef.current = grid
    const { cols, rows } = grid
    const cx = (cols - 1) / 2
    const cy = (rows - 1) / 2
    const maxDist = Math.sqrt(cx * cx + cy * cy) || 1

    scatterProps.current = shuffled.current.map((_, i) =>
      computeScatter(i, cols, rows, cx, cy, maxDist)
    )
    setKey(k => k + 1)
  }, [photos])

  const mosaicRef = useRef<HTMLDivElement>(null)

  /* Free GPU memory after assembly animation completes */
  useEffect(() => {
    if (!assembled || !mosaicRef.current) return
    const timer = setTimeout(() => {
      if (mosaicRef.current) {
        mosaicRef.current.querySelectorAll<HTMLDivElement>('.boom-cell').forEach(c => {
          c.style.willChange = 'auto'
        })
      }
    }, 2500)
    return () => clearTimeout(timer)
  }, [assembled])

  const { cols, rows } = gridRef.current

  let className = 'boom-mosaic'
  if (assembled) className += ' assembled'
  if (scattering) className += ' scattering'

  return (
    <div
      ref={mosaicRef}
      className={className}
      style={{
        '--m-cols': cols,
        '--m-rows': rows,
      } as React.CSSProperties}
    >
      {shuffled.current.map((photo, i) => {
        const sp = scatterProps.current[i]
        if (!sp) return null
        return (
          <BoomCell
            key={photo.id}
            photo={photo}
            scatter={sp}
            onClick={() => onCellClick(photo)}
          />
        )
      })}
    </div>
  )
}

/* ===== BoomCell component ===== */

interface BoomCellProps {
  photo: Photo
  scatter: CellScatterProps
  onClick: () => void
}

function BoomCell({ photo, scatter, onClick }: BoomCellProps) {
  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (el) loadProgressive(el, photo, 'thumb', '(max-width: 640px) 33vw, 160px')
  }, [photo])

  return (
    <div
      className="boom-cell"
      style={{
        '--sx': scatter.sx,
        '--sy': scatter.sy,
        '--sr': scatter.sr,
        '--d': scatter.d,
        '--d-out': scatter.dOut,
        backgroundColor: (photo.palette?.[0] || '') + '80',
      } as React.CSSProperties}
      onClick={(e) => { e.stopPropagation(); onClick() }}
    >
      <img ref={imgRef} alt="" />
    </div>
  )
}

/* ===== BoomView component ===== */

export function BoomView() {
  const data = useAppStore(s => s.data)
  const loadDriftNeighbors = useAppStore(s => s.loadDriftNeighbors)

  const [sets, setSets] = useState<BoomSet[]>([])
  const [activeIdx, setActiveIdx] = useState(-1)
  const [animating, setAnimating] = useState(false)
  const [assembled, setAssembled] = useState(false)
  const [scattering, setScattering] = useState(false)
  const [previewPhoto, setPreviewPhoto] = useState<Photo | null>(null)
  const [boomDensityIdx, setBoomDensityIdx] = useState(0)
  const [boomLoved, setBoomLoved] = useState(false)
  const [activeColorIdx, setActiveColorIdx] = useState(-1)
  const [imageTypeFilter, setImageTypeFilter] = useState<ImageTypeFilter>('mixed')

  const boomDensities = [24, 40, 54, 70]
  const isMobile = typeof window !== 'undefined' && window.innerWidth < window.innerHeight
  const colorBuckets = useMemo(buildBoomColorBuckets, [])
  const hasVariants = useMemo(() => data ? data.photos.some(p => !!p.parent) : false, [data])

  /* Refs for mutable state used in callbacks */
  const setsRef = useRef<BoomSet[]>([])
  const activeIdxRef = useRef(-1)
  const animatingRef = useRef(false)

  useEffect(() => { setsRef.current = sets }, [sets])
  useEffect(() => { activeIdxRef.current = activeIdx }, [activeIdx])
  useEffect(() => { animatingRef.current = animating }, [animating])

  /* Ref for drift neighbors (loaded once, reused on rebuilds) */
  const neighborsRef = useRef<Record<string, DriftNeighbor[]> | null>(null)

  /* Load drift neighbors once */
  useEffect(() => {
    if (!data) return
    let cancelled = false
    loadDriftNeighbors().then(neighbors => {
      if (cancelled) return
      neighborsRef.current = neighbors
      // Trigger initial build
      rebuildSets(data.photos, neighbors, boomDensities[boomDensityIdx], activeColorIdx, imageTypeFilter)
    })
    return () => { cancelled = true }
  }, [data, loadDriftNeighbors]) // eslint-disable-line react-hooks/exhaustive-deps

  /* Rebuild sets when density, color, or imageType changes */
  const rebuildSets = useCallback((
    photos: Photo[],
    neighbors: Record<string, DriftNeighbor[]> | null,
    density: number,
    colorIdx: number,
    imgType: ImageTypeFilter,
  ) => {
    // Apply image type filter
    let pool = filterByImageType(photos, imgType)
    // Apply color filter
    if (colorIdx >= 0 && colorBuckets[colorIdx]) {
      pool = pool.filter(p => photoMatchesBucket(p, colorBuckets[colorIdx]))
    }
    const builtSets = buildBoomSets(pool, neighbors, density)
    setSets(builtSets)
    if (builtSets.length > 0) {
      const startIdx = Math.floor(Math.random() * builtSets.length)
      selectSet(startIdx, builtSets)
    } else {
      setActiveIdx(-1)
      setAssembled(false)
    }
  }, [colorBuckets]) // eslint-disable-line react-hooks/exhaustive-deps

  /* Re-trigger build when controls change (after initial load) */
  const initialBuildDone = useRef(false)
  useEffect(() => {
    if (!data || !neighborsRef.current) return
    if (!initialBuildDone.current) { initialBuildDone.current = true; return }
    rebuildSets(data.photos, neighborsRef.current, boomDensities[boomDensityIdx], activeColorIdx, imageTypeFilter)
  }, [boomDensityIdx, activeColorIdx, imageTypeFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  /* Select a set and animate assembly */
  const selectSet = useCallback((idx: number, setsOverride?: BoomSet[]) => {
    const currentSets = setsOverride || setsRef.current
    if (animatingRef.current || idx === activeIdxRef.current) return
    if (!currentSets[idx]) return

    setAnimating(true)
    animatingRef.current = true

    const wasAssembled = activeIdxRef.current >= 0

    if (wasAssembled) {
      /* Scatter out current, then assemble new */
      setAssembled(false)
      setScattering(true)

      setTimeout(() => {
        setActiveIdx(idx)
        activeIdxRef.current = idx
        setScattering(false)

        /* Double rAF for DOM update then assembly */
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setAssembled(true)
            setAnimating(false)
            animatingRef.current = false
          })
        })
      }, 450)
    } else {
      /* First assembly -- no scatter */
      setActiveIdx(idx)
      activeIdxRef.current = idx
      setScattering(false)

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setAssembled(true)
          setAnimating(false)
          animatingRef.current = false
        })
      })
    }
  }, [])

  /* Blow: scatter out + new random set */
  const blow = useCallback(() => {
    if (animatingRef.current || setsRef.current.length === 0) return
    setAnimating(true)
    animatingRef.current = true

    /* Scatter out */
    setAssembled(false)
    setScattering(true)

    /* Pick a different random set */
    let next: number
    do { next = Math.floor(Math.random() * setsRef.current.length) }
    while (next === activeIdxRef.current && setsRef.current.length > 1)

    setTimeout(() => {
      setActiveIdx(next)
      activeIdxRef.current = next
      setScattering(false)

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setAssembled(true)
          setAnimating(false)
          animatingRef.current = false
        })
      })
    }, 350)
  }, [])

  /* Keyboard handler */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        blow()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [blow])

  /* Preview handlers */
  const openPreview = useCallback((photo: Photo) => {
    setPreviewPhoto(photo)
  }, [])

  const closePreview = useCallback(() => {
    setPreviewPhoto(null)
  }, [])

  const activeSet = activeIdx >= 0 ? sets[activeIdx] : null

  return (
    <div className="boom-wrap">
      <div className="boom-viewport">
        {activeSet && (
          <div className="boom-mosaic-wrap">
            <BoomMosaic
              photos={activeSet.photos}
              assembled={assembled}
              scattering={scattering}
              onCellClick={openPreview}
            />
          </div>
        )}
      </div>
      <div className="view-bottom">
        <ShowControls
          controls={['color', 'density', 'imageType', 'genie', 'heart']}
          state={{
            activeColorIdx,
            densityStepIdx: boomDensityIdx,
            displayMode: 'bento',
            imageTypeFilter,
            loved: boomLoved,
          }}
          config={{
            validDensities: boomDensities,
            colorBuckets: colorBuckets.map(b => ({ color: b.color, hueStart: b.hueStart })),
            hasVariants,
            samplePhoto: data?.photos.find(p => p.id === '001a5d8a-64bc-5ff7-a53f-9a8040e25f78')?.thumb
              || data?.photos.find(p => !p.parent && p.thumb)?.thumb,
            sampleVariant: data?.photos.find(p => p.id === '001a5d8a-64bc-5ff7-a53f-9a8040e25f78_gonzo')?.thumb
              || data?.photos.find(p => p.parent && p.thumb)?.thumb,
          }}
          callbacks={{
            onColorChange: setActiveColorIdx,
            onDensityChange: setBoomDensityIdx,
            onDisplayModeChange: () => {},
            onImageTypeChange: setImageTypeFilter,
            onGenie: blow,
            onLove: () => setBoomLoved(l => !l),
          }}
          compact={isMobile}
        />
      </div>

      <BoomPreview photo={previewPhoto} onClose={closePreview} />
    </div>
  )
}
