/**
 * ShowControls — Quiet Glass control bar.
 * One material. One shadow. Content supremacy.
 * Each view picks which controls to show via the `controls` array.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import type { DisplayMode, ImageTypeFilter } from '../../lib/layoutRegistry'
import './ShowControls.css'

/* ===== Control names ===== */

export type ShowControlName = 'color' | 'displayType' | 'density' | 'imageType' | 'genie' | 'heart'

/* ===== Component props ===== */

interface ColorBucket {
  color: string
  hueStart: number
}

export interface ShowControlsState {
  activeColorIdx: number      // -1 = all colors
  densityStepIdx: number
  displayMode: DisplayMode
  imageTypeFilter: ImageTypeFilter
  loved: boolean
}

export interface ShowControlsConfig {
  validDensities: number[]
  colorBuckets: ColorBucket[]
  hasVariants: boolean
}

export interface ShowControlsCallbacks {
  onColorChange: (idx: number) => void
  onDensityChange: (idx: number) => void
  onDisplayModeChange: (mode: DisplayMode) => void
  onImageTypeChange: (filter: ImageTypeFilter) => void
  onGenie: () => void
  onLove: () => void
}

interface ShowControlsProps {
  controls: ShowControlName[]
  state: ShowControlsState
  config: ShowControlsConfig
  callbacks: ShowControlsCallbacks
  compact?: boolean
}

/* ===== SVG icons ===== */

/** Camera icon with 3 fill modes — matches Figma frames 1247/1248/1249.
 *  photo: solid currentColor. mixed: left-half gradient, right-half solid.
 *  generated: full rainbow gradient with gradient lens center. */
const camBody = 'M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z'

const CameraIcon = ({ mode }: { mode: ImageTypeFilter }) => {
  const grad = mode !== 'photo'
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" className="show-ctrl-cam-svg">
      {grad && (
        <defs>
          <linearGradient id="it-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#f87171" />
            <stop offset="25%" stopColor="#fbbf24" />
            <stop offset="45%" stopColor="#34d399" />
            <stop offset="70%" stopColor="#60a5fa" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
          {mode === 'mixed' && (
            <>
              <clipPath id="it-cl"><rect x="0" y="0" width="12" height="24" /></clipPath>
              <clipPath id="it-cr"><rect x="12" y="0" width="12" height="24" /></clipPath>
            </>
          )}
        </defs>
      )}

      {mode === 'mixed' ? (
        <>
          <g clipPath="url(#it-cl)"><path d={camBody} fill="url(#it-g)" /></g>
          <g clipPath="url(#it-cr)"><path d={camBody} fill="currentColor" /></g>
        </>
      ) : (
        <path d={camBody} fill={grad ? 'url(#it-g)' : 'currentColor'} />
      )}

      {/* Lens ring */}
      <circle cx="12" cy="13.5" r="4" className="show-ctrl-cam-lens" />
      {/* Lens center */}
      <circle cx="12" cy="13.5" r="2.5" fill={mode === 'generated' ? 'url(#it-g)' : 'currentColor'} />
      {/* Flash dot */}
      <circle cx="18" cy="8.5" r="1" className="show-ctrl-cam-lens" />
    </svg>
  )
}

/** Density icon — 10 hand-tuned dot grids, one per density step.
 *  Each stepIdx maps to a distinct NxN grid that gets progressively denser.
 *  stepIdx 0 = 1 large dot, stepIdx 9 = 8×8 tiny dots. */
const DENSITY_GRIDS = [1, 2, 2, 3, 3, 4, 5, 6, 7, 8] as const

const DensityIcon = ({ stepIdx }: { stepIdx: number }) => {
  const n = DENSITY_GRIDS[Math.min(stepIdx, DENSITY_GRIDS.length - 1)] ?? 4
  const pad = 1.5
  const size = 16
  const area = size - pad * 2
  const step = area / n
  const r = Math.max(step * 0.34, 0.45)

  const dots: React.ReactNode[] = []
  for (let row = 0; row < n; row++) {
    for (let col = 0; col < n; col++) {
      dots.push(
        <circle
          key={`${row}-${col}`}
          cx={pad + step * 0.5 + col * step}
          cy={pad + step * 0.5 + row * step}
          r={r}
          fill="currentColor"
        />
      )
    }
  }

  return (
    <svg width="16" height="16" viewBox={`0 0 ${size} ${size}`}>
      {dots}
    </svg>
  )
}

/* ===== Component ===== */

export function ShowControls({ controls, state, config, callbacks, compact }: ShowControlsProps) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [geniePulsing, setGeniePulsing] = useState(false)
  const [densitySlide, setDensitySlide] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const colorBtnRef = useRef<HTMLButtonElement>(null)
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  /* Close picker on outside click */
  useEffect(() => {
    if (!pickerOpen) return
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node) &&
          colorBtnRef.current && !colorBtnRef.current.contains(e.target as Node)) {
        setPickerOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [pickerOpen])

  /* Color button: click cycles, long-press opens picker */
  const handleColorDown = useCallback(() => {
    longPressTimer.current = setTimeout(() => {
      setPickerOpen(p => !p)
      longPressTimer.current = null
    }, 300)
  }, [])

  const handleColorUp = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
      const buckets = config.colorBuckets
      if (buckets.length === 0) return
      let next = state.activeColorIdx + 1
      if (next >= buckets.length) next = -1
      callbacks.onColorChange(next)
    }
  }, [config.colorBuckets, state.activeColorIdx, callbacks])

  /* Density: click cycles forward with animation */
  const handleDensityClick = useCallback(() => {
    const vd = config.validDensities
    if (vd.length === 0) return
    let next = state.densityStepIdx + 1
    if (next >= vd.length) next = 0
    setDensitySlide(true)
    setTimeout(() => setDensitySlide(false), 250)
    callbacks.onDensityChange(next)
  }, [config.validDensities, state.densityStepIdx, callbacks])

  const handleDensityContext = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    const vd = config.validDensities
    if (vd.length === 0) return
    let prev = state.densityStepIdx - 1
    if (prev < 0) prev = vd.length - 1
    setDensitySlide(true)
    setTimeout(() => setDensitySlide(false), 250)
    callbacks.onDensityChange(prev)
  }, [config.validDensities, state.densityStepIdx, callbacks])

  /* Display mode toggle */
  const handleDisplayToggle = useCallback(() => {
    callbacks.onDisplayModeChange(state.displayMode === 'bento' ? 'uniform' : 'bento')
  }, [state.displayMode, callbacks])

  /* Image type cycle */
  const handleImageTypeCycle = useCallback(() => {
    const order: ImageTypeFilter[] = ['photo', 'mixed', 'generated']
    const cur = order.indexOf(state.imageTypeFilter)
    const next = (cur + 1) % order.length
    callbacks.onImageTypeChange(order[next])
  }, [state.imageTypeFilter, callbacks])

  /* Genie with pulse */
  const handleGenie = useCallback(() => {
    callbacks.onGenie()
    setGeniePulsing(true)
    setTimeout(() => setGeniePulsing(false), 400)
  }, [callbacks])

  /* Heart */
  const [heartBounce, setHeartBounce] = useState(false)
  const handleHeart = useCallback(() => {
    callbacks.onLove()
    setHeartBounce(true)
    setTimeout(() => setHeartBounce(false), 350)
  }, [callbacks])

  /* Color picker swatch click */
  const handleSwatchClick = useCallback((idx: number) => {
    if (idx === state.activeColorIdx) {
      callbacks.onColorChange(-1)
      setPickerOpen(false)
    } else {
      callbacks.onColorChange(idx)
    }
  }, [state.activeColorIdx, callbacks])


  const densityValue = config.validDensities[state.densityStepIdx] ?? 0
  const activeColor = state.activeColorIdx >= 0 && config.colorBuckets[state.activeColorIdx]
    ? config.colorBuckets[state.activeColorIdx].color
    : undefined

  /* Active color tints the bar border */
  const barStyle: React.CSSProperties | undefined = activeColor
    ? { borderColor: activeColor + '40' } // 25% opacity
    : undefined

  /* Determine if we need a divider (filters on left, actions on right) */
  const hasFilters = controls.some(c => ['color', 'displayType', 'density', 'imageType'].includes(c))
  const hasActions = controls.some(c => ['genie', 'heart'].includes(c))
  const needsDivider = hasFilters && hasActions

  return (
    <div className={`show-controls${compact ? ' compact' : ''}`} style={barStyle}>
      {/* Color picker popover */}
      {pickerOpen && controls.includes('color') && (
        <div className="show-ctrl-color-picker" ref={pickerRef}>
          {config.colorBuckets.map((b, i) => (
            <div
              key={i}
              className={`show-ctrl-color-swatch${i === state.activeColorIdx ? ' active' : ''}`}
              style={{ background: b.color }}
              onClick={() => handleSwatchClick(i)}
            />
          ))}
        </div>
      )}

      {/* 1. Color */}
      {controls.includes('color') && (
        <button
          ref={colorBtnRef}
          className={`show-ctrl-color${state.activeColorIdx >= 0 ? ' active' : ''}${
            activeColor && state.activeColorIdx >= 0 && config.colorBuckets[state.activeColorIdx]?.hueStart === -1 ? ' color-gray' : ''
          }`}
          style={activeColor ? { '--show-ctrl-color-glow': activeColor } as React.CSSProperties : undefined}
          onPointerDown={handleColorDown}
          onPointerUp={handleColorUp}
          onPointerLeave={() => {
            if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null }
          }}
          aria-label="Color filter"
          title="Color filter (long-press for picker)"
        />
      )}

      {/* 2. Display Type */}
      {controls.includes('displayType') && (
        <button
          className="show-ctrl-btn show-ctrl-display"
          onClick={handleDisplayToggle}
          aria-label={state.displayMode === 'bento' ? 'Switch to uniform grid' : 'Switch to bento'}
          title={state.displayMode === 'bento' ? 'Uniform grid' : 'Bento layout'}
        >
          {state.displayMode === 'bento' ? '\uD83C\uDF71' : '\uD83E\uDDC7'}
        </button>
      )}

      {/* 3. Density */}
      {controls.includes('density') && (
        <button
          className={`show-ctrl-btn show-ctrl-density${densitySlide ? ' morphing' : ''}`}
          onClick={handleDensityClick}
          onContextMenu={handleDensityContext}
          aria-label={`Density: ${densityValue}`}
          title="Density (right-click to go back)"
        >
          <DensityIcon stepIdx={state.densityStepIdx} />
        </button>
      )}

      {/* 4. Image Type */}
      {controls.includes('imageType') && config.hasVariants && (
        <button
          className={`show-ctrl-btn show-ctrl-imgtype${state.imageTypeFilter !== 'mixed' ? ' active' : ''}`}
          onClick={handleImageTypeCycle}
          aria-label={`Image type: ${state.imageTypeFilter}`}
          title={`Showing: ${state.imageTypeFilter}`}
        >
          <CameraIcon mode={state.imageTypeFilter} />
        </button>
      )}

      {/* Divider between filters and actions */}
      {needsDivider && <div className="show-ctrl-divider" />}

      {/* 5. Heart */}
      {controls.includes('heart') && (
        <button
          className={`show-ctrl-btn show-ctrl-heart${state.loved ? ' active' : ''}${state.loved && heartBounce ? ' loved' : ''}`}
          onClick={handleHeart}
          aria-label="Love this composition"
          title="Love this composition"
        >
          {state.loved ? '\u2764\uFE0F' : '\uD83E\uDD0D'}
        </button>
      )}

      {/* 6. Genie — always rightmost, never dimmed */}
      {controls.includes('genie') && (
        <button
          className={`show-ctrl-btn show-ctrl-genie${geniePulsing ? ' pulsing' : ''}`}
          onClick={handleGenie}
          aria-label="Best layout"
          title="Show the best layout"
        >
          &#x1F9DE;&#x200D;&#x2642;&#xFE0F;
        </button>
      )}
    </div>
  )
}
