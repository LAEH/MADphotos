import { useState, useEffect, useRef, useCallback, useMemo, memo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { useViewCleanup } from '../hooks/useViewCleanup'
import type { Photo } from '../types/photo'
import './AllView.css'

/* ── Types ──────────────────────────────────────────────────────────── */

interface LayoutTile {
  photo: Photo
  x: number
  y: number
  w: number
  h: number
  idx: number
}

interface LayoutRow {
  y: number
  h: number
  tiles: LayoutTile[]
}

/* Grid-cell tracking for reveal completion (30×20 = 600 cells) */
const REVEAL_GRID_COLS = 30
const REVEAL_GRID_ROWS = 20

/* ── Helpers ────────────────────────────────────────────────────────── */

function hexLuminance(hex: string): number {
  const c = hex.replace('#', '')
  const r = parseInt(c.substring(0, 2), 16) || 0
  const g = parseInt(c.substring(2, 4), 16) || 0
  const b = parseInt(c.substring(4, 6), 16) || 0
  return r * 0.299 + g * 0.587 + b * 0.114
}

/* ── Square Grid Layout (fills viewport edge-to-edge, drops extras) ── */

function computeSquareLayout(
  photos: Photo[],
  W: number,
  H: number,
): { rows: LayoutRow[]; placed: number } {
  const n = photos.length
  if (!n) return { rows: [], placed: 0 }

  /*
   * Find cols × rowCount that:
   *  1. Fills the entire viewport (no empty space)
   *  2. Tiles are approximately square (≤20% stretch)
   *  3. Maximizes the number of photos used (cols*rows ≤ n)
   */
  let bestCols = 1, bestRows = 1, bestCapacity = 1
  const maxCols = Math.ceil(Math.sqrt(n * W / H)) + 5

  for (let c = 1; c <= maxCols; c++) {
    const tileW = W / c
    const idealR = Math.round(H / tileW)
    for (const r of [idealR - 1, idealR, idealR + 1]) {
      if (r < 1) continue
      const cap = c * r
      if (cap > n) continue
      /* Reject grids where tiles are too stretched */
      const tileH = H / r
      const ratio = Math.min(tileW, tileH) / Math.max(tileW, tileH)
      if (ratio < 0.8) continue
      if (cap > bestCapacity) {
        bestCapacity = cap
        bestCols = c
        bestRows = r
      }
    }
  }

  /* Tiles stretch to fill viewport exactly — zero gaps */
  const rows: LayoutRow[] = []
  let idx = 0
  for (let r = 0; r < bestRows; r++) {
    const tiles: LayoutTile[] = []
    const y = Math.round(r * (H / bestRows))
    const h = Math.round((r + 1) * (H / bestRows)) - y
    for (let c = 0; c < bestCols && idx < bestCapacity; c++) {
      const x = Math.round(c * (W / bestCols))
      const w = Math.round((c + 1) * (W / bestCols)) - x
      tiles.push({ photo: photos[idx], x, y, w, h, idx })
      idx++
    }
    rows.push({ y, h, tiles })
  }
  return { rows, placed: idx }
}

/* ── Justified Layout (fill exact viewport) ─────────────────────────── */

function computeJustifiedLayout(
  photos: Photo[],
  W: number,
  H: number,
): { rows: LayoutRow[]; placed: number } {
  /*
   * Strategy: binary-search for the row height that makes the total grid
   * height land closest to the available viewport height H.
   * All images are placed, last row is stretched/compressed to fit.
   */
  function tryLayout(targetRowH: number) {
    const rows: LayoutRow[] = []
    let currentRow: { photo: Photo; aspect: number; idx: number }[] = []
    let yOffset = 0

    for (let i = 0; i < photos.length; i++) {
      const photo = photos[i]
      const aspect = photo.aspect || photo.w / photo.h || 1.5
      currentRow.push({ photo, aspect, idx: i })

      const totalAspect = currentRow.reduce((s, it) => s + it.aspect, 0)
      const rowHeight = W / totalAspect

      if (rowHeight <= targetRowH && currentRow.length >= 2) {
        const tiles: LayoutTile[] = []
        let x = 0
        for (let j = 0; j < currentRow.length; j++) {
          const it = currentRow[j]
          const tileW =
            j === currentRow.length - 1
              ? W - Math.round(x)
              : Math.round(it.aspect * rowHeight)
          tiles.push({
            photo: it.photo,
            x: Math.round(x),
            y: 0, // will be set later
            w: tileW,
            h: Math.round(rowHeight),
            idx: it.idx,
          })
          x += it.aspect * rowHeight
        }
        rows.push({ y: 0, h: Math.round(rowHeight), tiles })
        yOffset += rowHeight
        currentRow = []
      }
    }

    /* Drop incomplete last row — OK to skip a few images */

    return { rows, totalHeight: yOffset }
  }

  /* Binary search for the row height that fits H */
  let lo = 5,
    hi = 200,
    bestRows: LayoutRow[] = [],
    bestDiff = Infinity

  for (let iter = 0; iter < 40; iter++) {
    const mid = (lo + hi) / 2
    const result = tryLayout(mid)
    const diff = result.totalHeight - H

    if (Math.abs(diff) < Math.abs(bestDiff)) {
      bestDiff = diff
      bestRows = result.rows
    }

    if (diff > 0) {
      hi = mid // rows too tall → shrink
    } else {
      lo = mid // too short → grow
    }
  }

  /* Scale rows to exactly fill H */
  const rawHeight = bestRows.reduce((s, r) => s + r.h, 0)
  const scale = rawHeight > 0 ? H / rawHeight : 1
  let yOffset = 0
  for (const row of bestRows) {
    const scaledH = Math.round(row.h * scale)
    row.y = Math.round(yOffset)
    row.h = scaledH
    for (const tile of row.tiles) {
      tile.y = row.y
      tile.h = scaledH
    }
    yOffset += scaledH
  }

  const placed = bestRows.reduce((s, r) => s + r.tiles.length, 0)
  return { rows: bestRows, placed }
}

/* ── Tile component (memoized — 2700+ instances) ────────────────────── */
/*
 * Performance contract:
 * - Renders ONCE. Never re-renders (memo + stable props).
 * - Shows palette color instantly. Image loads off-DOM via new Image().
 * - Only when cached + decoded, sets visible <img>.src and triggers
 *   a single compositor-only opacity transition. Zero React state.
 */

const AllTile = memo(function AllTile({
  photo,
  x,
  y,
  w,
  h,
  idx,
  onClick,
}: {
  photo: Photo
  x: number
  y: number
  w: number
  h: number
  idx: number
  onClick: (idx: number) => void
}) {
  const imgRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    const img = imgRef.current
    if (!img) return

    const src = photo.micro || photo.thumb
    if (!src) return

    /*
     * Spatial wave: top → bottom over 800ms + tiny deterministic jitter.
     * Creates an organic "waterfall" instead of random popcorn.
     * Top tiles appear first, each row ~20ms apart, bottom tiles last.
     */
    const vh = window.innerHeight || 1
    const delay = Math.round((y / vh) * 800) + ((idx * 7) % 40)

    /* Preload off-DOM — browser caches the bytes */
    const pre = new Image()
    pre.decoding = 'async'

    let timer: ReturnType<typeof setTimeout> | null = null

    const reveal = () => {
      img.src = src
      timer = setTimeout(() => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            img.classList.add('all-tile-reveal')
          })
        })
      }, delay)
    }

    pre.onload = reveal
    pre.src = src
    if (pre.complete && pre.naturalWidth) reveal()

    return () => {
      pre.onload = null
      if (timer) clearTimeout(timer)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps — mount only

  const bg = photo.palette?.[0] || '#111'

  return (
    <div
      className="all-tile"
      data-idx={idx}
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width: w,
        height: h,
        backgroundColor: bg,
      }}
      onClick={() => onClick(idx)}
    >
      <img ref={imgRef} className="all-tile-img" decoding="async" alt="" />
    </div>
  )
})

/* ── Clean fullscreen preview (no labels) ───────────────────────────── */

function AllPreview({
  photo,
  onClose,
  onPrev,
  onNext,
}: {
  photo: Photo | null
  onClose: () => void
  onPrev: () => void
  onNext: () => void
}) {
  const [isOpen, setIsOpen] = useState(false)

  const imgRef = useCallback(
    (el: HTMLImageElement | null) => {
      if (el && photo) loadProgressive(el, photo, 'display', '100vw')
    },
    [photo],
  )

  useEffect(() => {
    if (photo) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setIsOpen(true))
      })
    } else {
      setIsOpen(false)
    }
  }, [photo])

  const handleClose = useCallback(() => {
    setIsOpen(false)
    setTimeout(onClose, 450) // match CSS transition duration
  }, [onClose])

  useEffect(() => {
    if (!photo) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); handleClose() }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); onPrev() }
      else if (e.key === 'ArrowRight') { e.preventDefault(); onNext() }
    }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [photo, onPrev, onNext, handleClose])

  /* Touch swipe */
  const touchX = useRef(0)
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchX.current = e.touches[0].clientX
  }, [])
  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const dx = e.changedTouches[0].clientX - touchX.current
      if (Math.abs(dx) > 50) dx > 0 ? onPrev() : onNext()
    },
    [onPrev, onNext],
  )

  if (!photo) return null

  return (
    <div
      className={`all-preview${isOpen ? ' open' : ''}`}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <div className="all-preview-backdrop" onClick={handleClose} />
      <img
        ref={imgRef}
        className="all-preview-img"
        alt=""
      />
    </div>
  )
}

/* ── Main view ──────────────────────────────────────────────────────── */

export function AllView() {
  useViewCleanup()
  const navigate = useNavigate()
  const data = useAppStore(s => s.data)

  const [dims, setDims] = useState({ w: 0, h: 0 })
  const [ready, setReady] = useState(false)
  const [previewIdx, setPreviewIdx] = useState(-1)
  const [squareMode, setSquareMode] = useState(false)
  /* Reveal → Preview mode (desktop only; mobile skips reveal) */
  const [previewMode, setPreviewMode] = useState(
    () => !window.matchMedia('(hover: hover) and (pointer: fine)').matches,
  )
  const previewModeRef = useRef(previewMode)
  previewModeRef.current = previewMode
  const countRef = useRef<HTMLDivElement>(null)
  const revealCanvasRef = useRef<HTMLCanvasElement>(null)
  const glowRef = useRef<HTMLDivElement>(null)
  const cellsRef = useRef(new Set<number>())
  const lastPosRef = useRef({ x: -1, y: -1 })
  const wrapRef = useRef<HTMLDivElement>(null)

  /* Shuffled photos — stable across re-renders */
  const photos = useMemo(() => {
    if (!data?.photos) return []
    const arr = [...data.photos]
    let seed = 42
    const rand = () => {
      seed = (seed * 16807 + 0) % 2147483647
      return seed / 2147483647
    }
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1))
      ;[arr[i], arr[j]] = [arr[j], arr[i]]
    }
    return arr
  }, [data])

  /* Display photos: shuffled (default) or sorted by brightness (square mode) */
  const displayPhotos = useMemo(() => {
    if (!squareMode) return photos
    return [...photos].sort((a, b) => {
      const lumA = hexLuminance(a.palette?.[0] || '#000')
      const lumB = hexLuminance(b.palette?.[0] || '#000')
      return lumB - lumA
    })
  }, [photos, squareMode])

  /* Measure container */
  useEffect(() => {
    const measure = () => {
      if (wrapRef.current) {
        setDims({ w: wrapRef.current.clientWidth, h: wrapRef.current.clientHeight })
      }
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  /* Compute layout to exactly fill viewport */
  const layout = useMemo(() => {
    if (!dims.w || !dims.h || !displayPhotos.length) return null
    return squareMode
      ? computeSquareLayout(displayPhotos, dims.w, dims.h)
      : computeJustifiedLayout(displayPhotos, dims.w, dims.h)
  }, [displayPhotos, dims.w, dims.h, squareMode])

  /* Entrance animation */
  useEffect(() => {
    if (layout) {
      const id = requestAnimationFrame(() => setReady(true))
      return () => cancelAnimationFrame(id)
    }
  }, [layout])

  /* Fill reveal canvas with black */
  useEffect(() => {
    if (previewMode) return
    const canvas = revealCanvasRef.current
    if (!canvas || !dims.w || !dims.h) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, dims.w, dims.h)
    cellsRef.current.clear()
    lastPosRef.current = { x: -1, y: -1 }
  }, [dims.w, dims.h, previewMode])

  /* Tile click — blocked during reveal mode (desktop) */
  const handleTileClick = useCallback((idx: number) => {
    if (!previewModeRef.current) return
    setPreviewIdx(idx)
  }, [])

  /* ── Hover preview (desktop only, zero React re-renders) ──────────── */
  const hoverRef = useRef<HTMLDivElement>(null)
  const hoverImgRef = useRef<HTMLImageElement>(null)
  const hoveredIdxRef = useRef(-1)
  const hoverDimsRef = useRef({ w: 340, h: 227 })
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const hoverMouseRef = useRef({ x: 0, y: 0 })
  const pendingTileRef = useRef(-1)
  const photosRef = useRef(displayPhotos)
  photosRef.current = displayPhotos

  const handleCanvasPointer = useCallback((e: React.PointerEvent) => {
    const hover = hoverRef.current
    const hoverImg = hoverImgRef.current
    const glow = glowRef.current

    /* ── Reveal mode: erase canvas at cursor (no tile detection needed) ── */
    if (!previewModeRef.current) {
      const rc = revealCanvasRef.current
      if (rc) {
        const ctx = rc.getContext('2d')
        if (ctx) {
          const rect = rc.getBoundingClientRect()
          const x = e.clientX - rect.left
          const y = e.clientY - rect.top

          /* Speed-adaptive brush: faster → bigger swipe */
          const prevX = lastPosRef.current.x
          const prevY = lastPosRef.current.y
          const hasPrev = prevX >= 0 && prevY >= 0
          const ddx = hasPrev ? x - prevX : 0
          const ddy = hasPrev ? y - prevY : 0
          const speed = Math.sqrt(ddx * ddx + ddy * ddy)
          const radius = 120 + Math.min(speed * 0.6, 60)

          /* Interpolate between positions for gapless strokes */
          const steps = hasPrev ? Math.max(1, Math.floor(speed / 8)) : 1
          ctx.globalCompositeOperation = 'destination-out'
          for (let s = 0; s <= steps; s++) {
            const t = steps > 0 ? s / steps : 1
            const ix = hasPrev ? prevX + (x - prevX) * t : x
            const iy = hasPrev ? prevY + (y - prevY) * t : y
            const grad = ctx.createRadialGradient(ix, iy, 0, ix, iy, radius)
            grad.addColorStop(0, 'rgba(0,0,0,1)')
            grad.addColorStop(0.5, 'rgba(0,0,0,0.5)')
            grad.addColorStop(1, 'rgba(0,0,0,0)')
            ctx.fillStyle = grad
            ctx.beginPath()
            ctx.arc(ix, iy, radius, 0, Math.PI * 2)
            ctx.fill()
          }
          ctx.globalCompositeOperation = 'source-over'
          lastPosRef.current = { x, y }

          /* Track cell coverage for completion */
          const cellW = rc.width / REVEAL_GRID_COLS
          const cellH = rc.height / REVEAL_GRID_ROWS
          const cellR = Math.ceil(radius / Math.min(cellW, cellH))
          const cx = Math.floor(x / cellW)
          const cy = Math.floor(y / cellH)
          for (let dr = -cellR; dr <= cellR; dr++) {
            for (let dc = -cellR; dc <= cellR; dc++) {
              const nx = cx + dc, ny = cy + dr
              if (nx >= 0 && nx < REVEAL_GRID_COLS && ny >= 0 && ny < REVEAL_GRID_ROWS) {
                cellsRef.current.add(nx * REVEAL_GRID_ROWS + ny)
              }
            }
          }

          /* Progress + auto-complete at 92% */
          const totalCells = REVEAL_GRID_COLS * REVEAL_GRID_ROWS
          const revealed = cellsRef.current.size
          const pct = Math.min(100, Math.round((revealed / totalCells) * 100))
          if (countRef.current) countRef.current.textContent = `${pct}%`

          if (revealed >= totalCells * 0.92) {
            if (countRef.current) countRef.current.textContent = '100%'
            rc.style.opacity = '0'
            if (glow) glow.classList.remove('visible')
            setTimeout(() => {
              previewModeRef.current = true
              setPreviewMode(true)
            }, 800)
          }
        }
      }

      /* Position glow spotlight */
      if (glow) {
        glow.classList.add('visible')
        glow.style.transform = `translate3d(${e.clientX - 130}px,${e.clientY - 130}px,0)`
      }

      if (hover) hover.classList.remove('visible')
      hoveredIdxRef.current = -1
      return
    }

    /* ── Preview mode: debounced hover preview (show on pause, not move) ── */
    const tile = (e.target as HTMLElement).closest('[data-idx]') as HTMLElement | null
    if (!tile) {
      clearTimeout(hoverTimerRef.current)
      pendingTileRef.current = -1
      if (hover) hover.classList.remove('visible')
      hoveredIdxRef.current = -1
      return
    }

    if (!hover || !hoverImg) return
    const idx = parseInt(tile.dataset.idx!, 10)

    /* Already showing for this tile — stay put */
    if (idx === hoveredIdxRef.current) return

    /* Still debouncing same tile — just update mouse pos */
    if (idx === pendingTileRef.current) {
      hoverMouseRef.current = { x: e.clientX, y: e.clientY }
      return
    }

    /* New tile — fade out old, debounce new */
    pendingTileRef.current = idx
    clearTimeout(hoverTimerRef.current)
    hover.classList.remove('visible')
    hoveredIdxRef.current = -1
    hoverMouseRef.current = { x: e.clientX, y: e.clientY }

    hoverTimerRef.current = setTimeout(() => {
      const photo = photosRef.current[idx]
      if (!photo || !hover || !hoverImg) return

      hoveredIdxRef.current = idx
      const aspect = photo.aspect || 1.5
      let pw: number, ph: number
      if (aspect >= 1) {
        pw = 340; ph = Math.round(340 / aspect)
      } else {
        ph = 380; pw = Math.round(380 * aspect)
      }
      hoverDimsRef.current = { w: pw, h: ph }
      hoverImg.style.width = pw + 'px'
      hoverImg.style.height = ph + 'px'

      /*
       * Use thumb/micro — already cached by tiles, loads from disk instantly.
       * Card + image appear together as one unit (no two-phase flash).
       */
      hoverImg.src = photo.thumb || photo.micro || ''

      const { x: mx, y: my } = hoverMouseRef.current
      const cw = pw + 24, ch = ph + 24
      let px = mx < window.innerWidth / 2 ? mx : mx - cw
      let py = my < window.innerHeight / 2 ? my : my - ch
      if (px < 4) px = 4
      if (py < 4) py = 4
      if (px + cw > window.innerWidth - 4) px = window.innerWidth - cw - 4
      if (py + ch > window.innerHeight - 4) py = window.innerHeight - ch - 4

      /* Scale origin = cursor corner → card "grows" from where you're looking */
      const ox = mx < window.innerWidth / 2 ? 'left' : 'right'
      const oy = my < window.innerHeight / 2 ? 'top' : 'bottom'
      hover.style.transformOrigin = `${ox} ${oy}`
      hover.style.transform = `translate3d(${px}px,${py}px,0)`
      hover.classList.add('visible')
    }, 250)
  }, [])

  const handleCanvasLeave = useCallback(() => {
    clearTimeout(hoverTimerRef.current)
    pendingTileRef.current = -1
    if (hoverRef.current) {
      hoverRef.current.classList.remove('visible')
      hoveredIdxRef.current = -1
    }
    if (glowRef.current) glowRef.current.classList.remove('visible')
    lastPosRef.current = { x: -1, y: -1 }
  }, [])

  /* Cleanup timer on unmount */
  useEffect(() => () => clearTimeout(hoverTimerRef.current), [])

  /* Circus emoji — random view on click */
  const handleCircus = useCallback(() => {
    const views = ['bento', 'game', 'boom', 'isit', 'scroll']
    navigate('/' + views[Math.floor(Math.random() * views.length)])
  }, [navigate])

  /* Cascade animation when toggling square mode (compositor-only, 60fps) */
  const squareModeInitRef = useRef(true)
  useEffect(() => {
    if (squareModeInitRef.current) { squareModeInitRef.current = false; return }
    if (!previewMode) return
    const canvas = wrapRef.current?.querySelector('.all-canvas') as HTMLElement | null
    if (!canvas) return
    const tiles = canvas.querySelectorAll('.all-tile') as NodeListOf<HTMLElement>
    const h = canvas.clientHeight || 1

    /* Phase 1: hide all tiles instantly (no transition) */
    tiles.forEach(t => {
      t.style.opacity = '0'
      t.style.transform = 'scale(0.92)'
      t.style.transition = 'none'
    })

    /* Phase 2: cascade reveal top → bottom */
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        tiles.forEach(t => {
          const top = parseFloat(t.style.top) || 0
          const delay = Math.round((top / h) * 400)
          t.style.transition = `opacity 0.4s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms, transform 0.4s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms`
          t.style.opacity = '1'
          t.style.transform = 'none'
        })
        /* Clean up inline styles after animation settles */
        setTimeout(() => {
          tiles.forEach(t => { t.style.transition = ''; t.style.transform = '' })
        }, 800)
      })
    })
  }, [squareMode]) // eslint-disable-line react-hooks/exhaustive-deps

  /* Preview navigation */
  const previewPhoto = previewIdx >= 0 && previewIdx < displayPhotos.length ? displayPhotos[previewIdx] : null
  const handlePrev = useCallback(() => {
    setPreviewIdx(i => (i > 0 ? i - 1 : i))
  }, [])
  const handleNext = useCallback(() => {
    setPreviewIdx(i => (i < displayPhotos.length - 1 ? i + 1 : i))
  }, [displayPhotos.length])

  return (
    <div className={`all-wrap${ready ? ' all-ready' : ''}${previewMode ? ' preview-mode' : ''}`} ref={wrapRef}>
      {layout && (
        <>
          <div
            className="all-canvas"
            style={{ width: dims.w, height: dims.h }}
            onPointerMove={handleCanvasPointer}
            onPointerLeave={handleCanvasLeave}
          >
            {layout.rows.flatMap(row =>
              row.tiles.map(tile => (
                <AllTile
                  key={tile.photo.id}
                  photo={tile.photo}
                  x={tile.x}
                  y={tile.y}
                  w={tile.w}
                  h={tile.h}
                  idx={tile.idx}
                  onClick={handleTileClick}
                />
              ))
            )}
            {/* Reveal: canvas fog overlay (desktop only) */}
            {!previewMode && (
              <canvas
                ref={revealCanvasRef}
                className="all-reveal-canvas"
                width={dims.w}
                height={dims.h}
              />
            )}
          </div>
          {/* Glow spotlight — follows cursor during reveal */}
          {!previewMode && <div ref={glowRef} className="all-reveal-glow" />}
          {/* Hover preview — always in DOM, shown/hidden via CSS class */}
          <div ref={hoverRef} className="all-hover-preview">
            <img ref={hoverImgRef} className="all-hover-preview-img" alt="" />
          </div>
          <div ref={countRef} className="all-count">
            {previewMode
              ? `${layout.placed.toLocaleString()} photographs`
              : '0%'
            }
          </div>
          {/* Bouncing circus — nested wrappers for independent X/Y transforms */}
          <div className="all-circus-x">
            <div className="all-circus-y">
              <div className="all-circus" onClick={handleCircus}>🎪</div>
            </div>
          </div>
          {/* Genie — floating disk like circus, toggle square/brightness mode */}
          {previewMode && (
            <div className="all-genie-x">
              <div className="all-genie-y">
                <div
                  className={`all-genie${squareMode ? ' active' : ''}`}
                  onClick={() => setSquareMode(m => !m)}
                >
                  🧞
                </div>
              </div>
            </div>
          )}
        </>
      )}
      <AllPreview
        photo={previewPhoto}
        onClose={() => setPreviewIdx(-1)}
        onPrev={handlePrev}
        onNext={handleNext}
      />
    </div>
  )
}
