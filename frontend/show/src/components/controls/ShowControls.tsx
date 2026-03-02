/**
 * ShowControls — Quiet Glass control bar.
 * One material. One shadow. Content supremacy.
 * Each view picks which controls to show via the `controls` array.
 *
 * All icons are 20×20 SVGs in a 24×24 viewBox for uniform optical weight.
 * Genie stays emoji — user designs it.
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
  samplePhoto?: string   // thumb URL for an original photo
  sampleVariant?: string // thumb URL for a generated variant
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

/* ===== SVG Icons — all 20×20 in 24×24 viewBox for consistent optical size ===== */

const ICON = 'show-ctrl-icon'

/** Bento — mixed-size rectangles */
const BentoIcon = () => (
  <svg className={ICON} viewBox="0 0 24 24" fill="currentColor">
    <rect x="3" y="3" width="8" height="11" rx="2" />
    <rect x="13" y="3" width="8" height="5" rx="2" />
    <rect x="13" y="10" width="8" height="11" rx="2" />
    <rect x="3" y="16" width="8" height="5" rx="2" />
  </svg>
)

/** Grid — uniform 2×2 */
const GridIcon = () => (
  <svg className={ICON} viewBox="0 0 24 24" fill="currentColor">
    <rect x="3" y="3" width="8" height="8" rx="2" />
    <rect x="13" y="3" width="8" height="8" rx="2" />
    <rect x="3" y="13" width="8" height="8" rx="2" />
    <rect x="13" y="13" width="8" height="8" rx="2" />
  </svg>
)

/** Density — dynamic dot grid, scales with step */
const DENSITY_GRIDS = [1, 2, 2, 3, 3, 4, 5, 6, 7, 8] as const

const DensityIcon = ({ stepIdx }: { stepIdx: number }) => {
  const n = DENSITY_GRIDS[Math.min(stepIdx, DENSITY_GRIDS.length - 1)] ?? 4
  const pad = 4
  const area = 24 - pad * 2
  const step = area / n
  const r = Math.max(step * 0.32, 0.6)

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

  return <svg className={ICON} viewBox="0 0 24 24">{dots}</svg>
}

/** Heart — always filled for visual weight, color changes on love */
const HeartIcon = () => (
  <svg className={ICON} viewBox="0 0 24 24" fill="currentColor">
    <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
  </svg>
)

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

  /* Next color — preview what clicking will activate */
  const buckets = config.colorBuckets
  const nextColorIdx = buckets.length > 0
    ? (state.activeColorIdx + 1 >= buckets.length ? -1 : state.activeColorIdx + 1)
    : -1
  const nextColor = nextColorIdx >= 0 && buckets[nextColorIdx]
    ? buckets[nextColorIdx].color
    : undefined
  const activeColor = state.activeColorIdx >= 0 && buckets[state.activeColorIdx]
    ? buckets[state.activeColorIdx].color
    : undefined

  /* Active color tints the bar border */
  const barStyle: React.CSSProperties | undefined = activeColor
    ? { borderColor: activeColor + '40' } // 25% opacity
    : undefined

  /* Determine if we need a divider (grid controls on left, personal on right) */
  const hasFilters = controls.some(c => ['displayType', 'density', 'imageType'].includes(c))
  const hasActions = controls.some(c => ['color', 'genie', 'heart'].includes(c))
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

      {/* 1. Color — shows next color preview */}
      {controls.includes('color') && (
        <button
          ref={colorBtnRef}
          className={`show-ctrl-color${nextColor ? ' show-next' : ''}${
            nextColor && nextColorIdx >= 0 && buckets[nextColorIdx]?.hueStart === -1 ? ' color-gray' : ''
          }`}
          style={nextColor ? { '--show-ctrl-color-glow': nextColor } as React.CSSProperties : undefined}
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
          {state.displayMode === 'bento' ? <BentoIcon /> : <GridIcon />}
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

      {/* 4. Image Type — photo disc (28px visual inside 44px touch target) */}
      {controls.includes('imageType') && config.hasVariants && config.samplePhoto && (
        <button
          className="show-ctrl-imgdisc"
          onClick={handleImageTypeCycle}
          aria-label={`Image type: ${state.imageTypeFilter}`}
          title={`Showing: ${state.imageTypeFilter}`}
        >
          <span className="show-ctrl-imgdisc-inner">
            {state.imageTypeFilter === 'mixed' ? (
              <>
                <img className="show-ctrl-imgdisc-half left" src={config.samplePhoto} alt="" />
                <img className="show-ctrl-imgdisc-half right" src={config.sampleVariant || config.samplePhoto} alt="" />
              </>
            ) : (
              <img
                className="show-ctrl-imgdisc-full"
                src={state.imageTypeFilter === 'photo' ? config.samplePhoto : (config.sampleVariant || config.samplePhoto)}
                alt=""
              />
            )}
          </span>
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
          <HeartIcon />
        </button>
      )}

      {/* 6. Genie — emoji, always rightmost, never dimmed */}
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
