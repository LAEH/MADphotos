import { useState, useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { getObjectPosition } from '../lib/cropUtils'
import { randomFrom } from '../lib/utils'
import { fireAndForget } from '../lib/firebase'
import {
  DESKTOP_STARTER_LAYOUTS, MOBILE_STARTER_LAYOUTS,
  uniformBentoGrid, pickLayoutForCount,
  filterByImageType, isSplittable, splitCell,
  type BentoLayout, type ImageTypeFilter,
} from '../lib/layoutRegistry'
import { ShowControls } from '../components/controls/ShowControls'
import type { Photo } from '../types/photo'
import type { BentoCell } from '../lib/cropUtils'
import './BentoView.css'

/* Layouts, density steps, and grid generators are in layoutRegistry.ts */

/** Rendered unit cell w/h ratio — set by fillBento before curators run.
 *  Desktop (5×3, container 3/2): 0.9. Mobile (3×6, container 2/3): 1.333. */
let _activeUnitRatio = 1

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
    // Gray detection: check top 2 dominant colors (not all) with generous threshold
    if (palette && palette.length > 0) {
      const topColors = palette.slice(0, Math.min(2, palette.length))
      const allGray = topColors.every(hex => {
        if (!hex || hex.length < 7) return true
        const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16)
        return (Math.max(r, g, b) - Math.min(r, g, b)) < 40
      })
      if (allGray) { grayPhotos.push(photo); continue }
    }
    const hue = photo.hue || 0
    const idx = Math.min(Math.floor(hue / bucketSize), BENTO_NUM_BUCKETS - 1)
    buckets[idx].photos.push(photo)
  }
  if (grayPhotos.length > 0) {
    buckets.push({ hueStart: -1, hueEnd: -1, color: '#8e8e93', photos: grayPhotos })
  }
  return buckets
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
 *  Higher coverage = more of the subject is visible in that crop = better fit.
 *  unitRatio = actual rendered w/h ratio of a 1×1 cell (accounts for container distortion). */
function cropFitness(p: Photo, cell: BentoCell, unitRatio = 1): number {
  if (!p.gemma_crops) return 0
  const ratio = (cell.cs / cell.rs) * unitRatio
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
  const unitRatio = _activeUnitRatio
  // Sort cells by size (large cells first) to assign heroes to big cells
  const indexedCells = cells.map((cell, i) => ({ cell, i, size: cell.rs * cell.cs }))
  const sortedCells = [...indexedCells].sort((a, b) => b.size - a.size)

  // Score photos per-cell: base score + crop fitness for this specific cell
  const result: (Photo | undefined)[] = new Array(cells.length)
  const claimed = new Set<string>()

  // Parent-child dedup: skip photos whose parent or child is already claimed
  const skip = (p: Photo) =>
    usedIds.has(p.id) || claimed.has(p.id) ||
    (p.parent && (usedIds.has(p.parent) || claimed.has(p.parent)))

  const claim = (p: Photo) => {
    claimed.add(p.id)
    usedIds.add(p.id)
    // Also block the parent so the original can't be selected alongside its variant
    if (p.parent) { claimed.add(p.parent); usedIds.add(p.parent) }
  }

  for (const { cell, i } of sortedCells) {
    const primary = cell.orient === 'P' ? pools.P : pools.L
    const fallback = cell.orient === 'P' ? pools.L : pools.P

    // Score candidates with crop fitness bonus for this cell
    let best: Photo | undefined
    let bestScore = -Infinity
    for (const p of primary) {
      if (skip(p)) continue
      const s = scoreFn(p) + cropFitness(p, cell, unitRatio)
      if (s > bestScore) { bestScore = s; best = p }
    }
    if (!best) {
      for (const p of fallback) {
        if (skip(p)) continue
        const s = scoreFn(p) + cropFitness(p, cell, unitRatio)
        if (s > bestScore) { bestScore = s; best = p }
      }
    }
    if (best) {
      result[i] = best
      claim(best)
    }
  }

  // Second pass: fill any remaining empty slots from ALL unclaimed photos (ignore orientation)
  const allRemaining = [...pools.P, ...pools.L]
  for (let i = 0; i < result.length; i++) {
    if (result[i]) continue
    let best: Photo | undefined
    let bestScore = -Infinity
    for (const p of allRemaining) {
      if (skip(p)) continue
      const s = scoreFn(p)
      if (s > bestScore) { bestScore = s; best = p }
    }
    if (best) {
      result[i] = best
      claim(best)
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
  const photos = allPhotos.filter(p => p.thumb && p.display && (p.aesthetic || 0) > 4)
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
  const photos = allPhotos.filter(p => p.thumb && p.display && (p.aesthetic || 0) > 4)

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
    p.thumb && p.display && (p.aesthetic || 0) > 4 && p.depth_complexity != null
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
  const monoPhotos = allPhotos.filter(p => p.thumb && p.display && p.mono && (p.aesthetic || 0) > 4)
  const colorPhotos = allPhotos.filter(p =>
    p.thumb && p.display && !p.mono && (p.aesthetic || 0) > 5 &&
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
  const photos = allPhotos.filter(p => p.thumb && p.display && p.vibes && p.vibes.length > 0)
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
  const photos = allPhotos.filter(p => p.thumb && p.display && p.scene)
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
    p.thumb && p.display && p.gc_archetype && (p.aesthetic || 0) > 4
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
  const photos = allPhotos.filter(p => p.thumb && p.display && p.camera && (p.aesthetic || 0) > 4)
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
    p.thumb && p.display && (p.aesthetic || 0) > 4 &&
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
    p.thumb && p.display && (p.aesthetic || 0) > 4 &&
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
    p.thumb && p.display && (p.aesthetic || 0) > 4 &&
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
    p.thumb && p.display && (p.aesthetic || 0) > 4 && p.style === 'analog'
  )
  const digital = allPhotos.filter(p =>
    p.thumb && p.display && (p.aesthetic || 0) > 4 &&
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
    p.thumb && p.display && (p.aesthetic || 0) > 4 && p.brightness != null
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
    p.thumb && p.display && p.gc_energy && (p.aesthetic || 0) > 4
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
    p.thumb && p.display && p.gemma_pops && p.gemma_pops.length > 0 && (p.aesthetic || 0) > 4
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
    p.thumb && p.display && p.print_worthy && (p.aesthetic || 0) > 4
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
    p.thumb && p.display && p.gemma_vibes && p.gemma_vibes.length > 0 && (p.aesthetic || 0) > 4
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
    p.thumb && p.display && p.gemma_subject && (p.aesthetic || 0) > 4
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
    p.thumb && p.display && p.gemma_sharpness && (p.aesthetic || 0) > 4
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
  // Set the rendered unit ratio so cropFitness uses the true on-screen ratio
  const containerRatio = layout.device === 'mobile' ? (2 / 3) : (3 / 2)
  _activeUnitRatio = containerRatio * layout.rows / layout.cols

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

/* ===== Split icon ===== */
const SplitIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
  </svg>
)

/* ===== BentoTile component ===== */

interface BentoTileProps {
  photo: Photo
  cell: BentoCell
  cellIndex: number
  index: number
  revealed: boolean
  hasVariant: boolean
  splittable: boolean
  isSplit?: boolean
  gridCols: number
  gridRows: number
  containerRatio: number
  onSwap: (tileEl: HTMLDivElement) => void
  onSplit: (cellIndex: number) => void
  onFullscreen: (photo: Photo) => void
}

function BentoTile({ photo, cell, cellIndex, index, revealed, hasVariant, splittable, isSplit, gridCols, gridRows, containerRatio, onSwap, onSplit, onFullscreen }: BentoTileProps) {
  const tileRef = useRef<HTMLDivElement>(null)
  const touchRef = useRef({ x: 0, y: 0, moved: false })

  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (!el) return
    // After a crossfade swap, the tile DOM element has a data-swapped flag.
    // Skip loadProgressive — the image is already showing the correct source.
    // Without this, React re-render triggers micro→blur→decode→reveal jitter.
    if (el.parentElement?.dataset.swapped) {
      delete el.parentElement.dataset.swapped
      el.style.objectPosition = getObjectPosition(photo, cell, gridCols, gridRows, containerRatio)
      return
    }
    loadProgressive(el, photo, 'display', '(max-width: 768px) 50vw, 33vw')
    el.style.objectPosition = getObjectPosition(photo, cell, gridCols, gridRows, containerRatio)
  }, [photo, cell, gridCols, gridRows, containerRatio])

  const dominant = photo.palette?.[0]

  /* Click → swap photo (desktop primary action) */
  const handleClick = useCallback(() => {
    if (tileRef.current) onSwap(tileRef.current)
  }, [onSwap])

  const handleFullscreen = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onFullscreen(photo)
  }, [onFullscreen, photo])

  const handleSplitBtn = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onSplit(cellIndex)
  }, [onSplit, cellIndex])

  /* Mobile: per-tile touch — horizontal swipe swaps, vertical swipe splits */
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY, moved: false }
  }, [])

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    const dx = e.changedTouches[0].clientX - touchRef.current.x
    const dy = e.changedTouches[0].clientY - touchRef.current.y
    const absDx = Math.abs(dx)
    const absDy = Math.abs(dy)

    if (absDx < 30 && absDy < 30) return // tap, not swipe — let click handle it

    e.stopPropagation() // prevent grid-level swipe

    if (absDy > absDx && absDy > 40 && splittable) {
      // Vertical swipe → split
      onSplit(cellIndex)
    } else if (absDx > absDy && absDx > 40) {
      // Horizontal swipe → swap photo
      if (tileRef.current) onSwap(tileRef.current)
    }
  }, [splittable, cellIndex, onSwap, onSplit])

  return (
    <div
      ref={tileRef}
      className={`bento-tile${revealed ? ' bento-tile-revealed' : ''}${splittable ? ' bento-tile-splittable' : ''}${isSplit ? ' bento-tile-split' : ''}`}
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
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
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
      {splittable && (
        <button className="bento-tile-split-btn" onClick={handleSplitBtn}>
          <SplitIcon />
        </button>
      )}
    </div>
  )
}

/* ===== BentoView component ===== */

export function BentoView() {
  const data = useAppStore(s => s.data)
  const openLightbox = useAppStore(s => s.openLightbox)

  const [layout, setLayout] = useState<BentoLayout | null>(null)
  const [workingCells, setWorkingCells] = useState<BentoCell[]>([])
  const [photos, setPhotos] = useState<Photo[]>([])
  const [colorBuckets, setColorBuckets] = useState<BentoColorBucket[]>([])
  const [activeColorIdx, setActiveColorIdx] = useState(-1) // set to random after buckets build
  const [imageTypeFilter, setImageTypeFilter] = useState<ImageTypeFilter>('generated')
  const [loved, setLoved] = useState(false)
  const [activeCurator, setActiveCurator] = useState('')
  /* Track which cell indices were just split (for animation) */
  const [splitIndices, setSplitIndices] = useState(new Set<number>())

  /* Variant map: parentId → variant Photo (prefer smart_style > style_transfer) */
  const variantMap = useRef(new Map<string, Photo>())
  const [hasVariants, setHasVariants] = useState(false)
  const samplePhotoRef = useRef<string | undefined>(undefined)
  const sampleVariantRef = useRef<string | undefined>(undefined)
  /* Track which tile indices are currently showing their variant */
  const revealedRef = useRef(new Set<number>())
  const [revealedSet, setRevealedSet] = useState(new Set<number>())
  /* Recently shown photo IDs — prevent repeats across consecutive generations */
  const recentlyShownRef = useRef(new Set<string>())
  const RECENTLY_SHOWN_CAP = 2000

  /* Refs for mutable state used by intervals/callbacks */
  const photosRef = useRef<Photo[]>([])
  const workingCellsRef = useRef<BentoCell[]>([])
  const layoutRef = useRef<BentoLayout | null>(null)
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
    setHasVariants(map.size > 0)
    if (!samplePhotoRef.current) {
      samplePhotoRef.current = data.photos.find(p => !p.parent && p.thumb)?.thumb
    }
    if (!sampleVariantRef.current) {
      const variant = [...map.values()].find(v => v.thumb)
      if (variant) sampleVariantRef.current = variant.thumb
    }
  }, [data])

  /* Build color buckets — pick a random starting color with enough photos */
  const initialColorPicked = useRef(false)
  useEffect(() => {
    if (!data) return
    const buckets = buildBentoColorBuckets(data.photos)
    setColorBuckets(buckets)
    if (!initialColorPicked.current) {
      initialColorPicked.current = true
      // Pick a random bucket that has enough photos (at least 4)
      const rich = buckets.map((b, i) => ({ i, count: b.photos.length })).filter(x => x.count >= 4)
      if (rich.length > 0) {
        setActiveColorIdx(rich[Math.floor(Math.random() * rich.length)].i)
      }
    }
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
  useEffect(() => { workingCellsRef.current = workingCells }, [workingCells])
  useEffect(() => { layoutRef.current = layout }, [layout])

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

    // Warm browser cache + decode so swaps are instant
    for (const p of [...buf.P, ...buf.L]) {
      const src = p.display || p.thumb
      if (src) {
        const img = new Image()
        img.decoding = 'async'
        img.src = src
        if (typeof img.decode === 'function') img.decode().catch(() => {})
      }
    }
  }, [data])

  /* Generate a fresh bento — always picks from starter layouts (low density, big splittable tiles) */
  const generate = useCallback(() => {
    if (!data) return
    const device = isDesktop() ? 'desktop' as const : 'mobile' as const
    const starterLayouts = device === 'desktop' ? DESKTOP_STARTER_LAYOUTS : MOBILE_STARTER_LAYOUTS
    const newLayout = randomFrom(starterLayouts)

    const isColorFiltered = activeColorIdx >= 0 && colorBuckets[activeColorIdx]
    let photoPool = isColorFiltered ? colorBuckets[activeColorIdx].photos : data.photos

    // Apply image type filter
    photoPool = filterByImageType(photoPool, imageTypeFilter)

    // Exclude recently shown photos for freshness across taps
    const recent = recentlyShownRef.current
    const freshPool = photoPool.filter(p => !recent.has(p.id))
    // Only use fresh pool if it has enough candidates; otherwise allow repeats
    if (freshPool.filter(p => p.thumb && p.display).length >= newLayout.count * 2) {
      photoPool = freshPool
    }

    // Fall back to all photos if color/type filter too restrictive
    const availableCount = photoPool.filter(p => p.thumb && p.display).length
    if (availableCount < 3) {
      photoPool = filterByImageType(data.photos, imageTypeFilter)
      if (photoPool.filter(p => p.thumb && p.display).length < 3) {
        photoPool = data.photos
      }
    }

    const fillResult = fillBento(photoPool, newLayout, !!isColorFiltered)
    let selected = fillResult.photos
    setActiveCurator(fillResult.curator)

    // NEVER allow empty tiles — if we have fewer photos than cells, fix it
    if (selected.length > 0 && selected.length < newLayout.count) {
      const usedIds = new Set(selected.map(p => p.id))
      // Also block parents of selected variants to prevent duplicates
      for (const p of selected) { if (p.parent) usedIds.add(p.parent) }
      const extras = photoPool.filter(p => p.thumb && p.display && !usedIds.has(p.id) && (!p.parent || !usedIds.has(p.parent)))
      while (selected.length < newLayout.count && extras.length > 0) {
        const pick = extras.splice(Math.floor(Math.random() * extras.length), 1)[0]
        selected.push(pick)
      }
      if (selected.length < newLayout.count) {
        const fallbackLayout = uniformBentoGrid(selected.length, device)
        setLayout(fallbackLayout)
        setWorkingCells([...fallbackLayout.cells])
        selected = selected.slice(0, fallbackLayout.count)
        setPhotos(selected)
        revealedRef.current = new Set()
        setRevealedSet(new Set())
        setSplitIndices(new Set())
        requestAnimationFrame(() => refillPreloadBuffer(new Set(selected.map(p => p.id))))
        return
      }
    }

    // Inject at most 1 AI variant as an accent — never dominate
    // Skip when color filtered — variants break color coherence
    if (imageTypeFilter === 'mixed' && variantMap.current.size > 0 && !isColorFiltered) {
      const hasVariant = selected.some(p => p.parent)
      if (!hasVariant) {
        // Try to swap one selected photo that has a variant available
        let injected = false
        for (let i = 0; i < selected.length; i++) {
          const v = variantMap.current.get(selected[i].id)
          if (v && (v.display || v.thumb) && !recentlyShownRef.current.has(v.id)) {
            selected[i] = v
            injected = true
            break
          }
        }
        // Fallback: if no selected photo had a variant, pick any random variant
        if (!injected) {
          const allVariants = [...variantMap.current.values()].filter(
            v => (v.display || v.thumb) && !recentlyShownRef.current.has(v.id)
          )
          if (allVariants.length > 0) {
            const pick = allVariants[Math.floor(Math.random() * allVariants.length)]
            // Swap into a random slot
            const slot = Math.floor(Math.random() * selected.length)
            selected[slot] = pick
          }
        }
      }
    }

    // Track recently shown to avoid repeats across taps
    for (const p of selected) recent.add(p.id)
    if (recent.size > RECENTLY_SHOWN_CAP) {
      const arr = [...recent]
      recentlyShownRef.current = new Set(arr.slice(arr.length - RECENTLY_SHOWN_CAP))
    }

    setLayout(newLayout)
    setWorkingCells([...newLayout.cells])
    setPhotos(selected)
    revealedRef.current = new Set()
    setRevealedSet(new Set())
    setSplitIndices(new Set())
    requestAnimationFrame(() => refillPreloadBuffer(new Set(selected.map(p => p.id))))
  }, [data, activeColorIdx, colorBuckets, imageTypeFilter, refillPreloadBuffer])

  /* Perform split — replace a multi-span cell with 1×1 children, filling new photos */
  const performSplit = useCallback((cellIdx: number) => {
    if (!data) return
    const cells = workingCellsRef.current
    const cell = cells[cellIdx]
    if (!cell || !isSplittable(cell)) return

    // Split the cell into 1×1 children
    const newCells = splitCell(cells, cellIdx)
    // How many new cells were created (children - 1 original)
    const childCount = cell.rs * cell.cs
    const newSlots = childCount - 1

    // The original photo stays in the first child cell (at cellIdx)
    // We need newSlots new photos for the remaining children
    const currentIds = new Set(photosRef.current.map(p => p.id))
    const buf = preloadBufferRef.current
    const newPhotos: Photo[] = []

    for (let i = 0; i < newSlots; i++) {
      let pick: Photo | undefined

      // Try preload buffer first
      const allBuf = [...buf.L, ...buf.P]
      const ready = allBuf.filter(p => !currentIds.has(p.id) && !newPhotos.some(np => np.id === p.id))
      if (ready.length > 0) {
        pick = ready[Math.floor(Math.random() * ready.length)]
        // Remove from buffer
        let bIdx = buf.L.findIndex(p => p.id === pick!.id)
        if (bIdx >= 0) buf.L.splice(bIdx, 1)
        else { bIdx = buf.P.findIndex(p => p.id === pick!.id); if (bIdx >= 0) buf.P.splice(bIdx, 1) }
      } else {
        // Fall back to random pool
        const pool = (data.photos).filter(p =>
          p.thumb && p.display && !currentIds.has(p.id) && !newPhotos.some(np => np.id === p.id)
        )
        if (pool.length > 0) pick = randomFrom(pool)
      }

      if (pick) {
        newPhotos.push(pick)
        currentIds.add(pick.id)
      }
    }

    // Build new photos array: splice in new photos after the original
    const updatedPhotos = [...photosRef.current]
    updatedPhotos.splice(cellIdx + 1, 0, ...newPhotos)

    // Track which indices are newly split (for animation)
    const newSplitIndices = new Set<number>()
    for (let i = 0; i < childCount; i++) {
      newSplitIndices.add(cellIdx + i)
    }

    setWorkingCells(newCells)
    setPhotos(updatedPhotos)
    setSplitIndices(newSplitIndices)
    // Clear split animation class after animation completes
    setTimeout(() => setSplitIndices(new Set()), 500)

    // Refill preload buffer
    requestAnimationFrame(() => refillPreloadBuffer(new Set(updatedPhotos.map(p => p.id))))
  }, [data, refillPreloadBuffer])

  /* Swap a single tile — crossfade to a new photo from preload buffer */
  const swapTile = useCallback((tileEl: HTMLDivElement) => {
    if (!data) return
    const oldId = tileEl.dataset.id
    const orient = tileEl.dataset.orient as 'P' | 'L' | undefined
    const cellIdx = parseInt(tileEl.dataset.cellIdx || '0', 10)

    // Remove any in-flight crossfade overlay
    tileEl.querySelectorAll('.bento-tile-next').forEach(el => el.remove())

    let newPhoto: Photo | undefined

    // If current photo is a variant, first click reveals the original
    const currentPhoto = photosRef.current.find(p => p.id === oldId)
    if (currentPhoto?.parent) {
      const original = data.photos.find(p => p.id === currentPhoto.parent)
      if (original && (original.display || original.thumb)) {
        newPhoto = original
      }
    }

    // Normal swap: pull from preload buffer or pool
    if (!newPhoto) {
      const currentIds = new Set(photosRef.current.map(p => p.id))
      const buf = preloadBufferRef.current
      const bufPool = orient === 'P' ? buf.P : buf.L
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
    }

    const target = newPhoto.display || newPhoto.thumb
    if (!target) return

    const mainImg = tileEl.querySelector('img:not(.bento-tile-next)') as HTMLImageElement
    if (!mainImg) return

    // Compute object-position for new photo
    const wCells = workingCellsRef.current
    const ly = layoutRef.current
    let objPos = ''
    if (wCells[cellIdx]) {
      objPos = ly
        ? getObjectPosition(newPhoto, wCells[cellIdx], ly.cols, ly.rows, ly.device === 'mobile' ? 2/3 : 3/2)
        : getObjectPosition(newPhoto, wCells[cellIdx])
    }

    // Preload new image, then crossfade overlay
    const captured = newPhoto
    const preload = new Image()
    preload.decoding = 'async'

    const doSwap = () => {
      const overlay = document.createElement('img')
      overlay.className = 'bento-tile-next'
      overlay.src = target
      overlay.alt = ''
      if (objPos) overlay.style.objectPosition = objPos
      tileEl.appendChild(overlay)

      // Double-rAF: ensure browser paints opacity:0 before transitioning
      requestAnimationFrame(() => {
        requestAnimationFrame(() => { overlay.style.opacity = '1' })
      })

      let cleaned = false
      const cleanup = () => {
        if (cleaned) return
        cleaned = true
        overlay.removeEventListener('transitionend', cleanup)
        // Transfer to main image
        mainImg.src = target
        if (objPos) mainImg.style.objectPosition = objPos
        mainImg.classList.remove('img-loading', 'img-loaded', 'img-blur-up')
        mainImg.style.filter = ''
        mainImg.style.transform = ''
        // Flag: tell imgRef to skip loadProgressive on the React re-render
        tileEl.dataset.swapped = ''
        tileEl.dataset.id = captured.id
        if (captured.parent) tileEl.dataset.variant = ''
        else delete tileEl.dataset.variant
        const dominant = captured.palette?.[0]
        if (dominant) tileEl.style.backgroundColor = dominant + '99'
        overlay.remove()

        setPhotos(prev => {
          const next = [...prev]
          const idx = next.findIndex(p => p.id === oldId)
          if (idx >= 0) next[idx] = captured
          return next
        })

        const nextIds = new Set(photosRef.current.map(p => p.id))
        nextIds.delete(oldId!)
        nextIds.add(captured.id)
        refillPreloadBuffer(nextIds)
      }

      overlay.addEventListener('transitionend', cleanup)
      setTimeout(cleanup, 400)
    }

    preload.onload = doSwap
    preload.onerror = doSwap
    preload.src = target
  }, [data, refillPreloadBuffer])

  /* Cycle layouts with arrow keys — just regenerate */
  const cycle = useCallback((_dir: number) => {
    generate()
  }, [generate])

  /* Init: generate on mount */
  useEffect(() => {
    if (data) generate()
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

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

  /* Fullscreen handler — minimal mode: image only, no chrome */
  const handleFullscreen = useCallback((photo: Photo) => {
    openLightbox(photo, photosRef.current, true)
  }, [openLightbox])

  /* ShowControls callbacks */
  const handleColorChange = useCallback((idx: number) => setActiveColorIdx(idx), [])
  const handleImageTypeChange = useCallback((filter: ImageTypeFilter) => setImageTypeFilter(filter), [])

  /* Best bento — curated exhibition, not a variant showcase.
   * Shuffles curators for variety. ~1 in 3 taps applies a random color filter.
   * 6-12 tiles, max 1 variant accent, avoids recently shown. */
  const showBestBento = useCallback(() => {
    if (!data) return
    const device = isDesktop() ? 'desktop' as const : 'mobile' as const
    // 6-12 tiles — always a meaningful composition
    const count = 6 + Math.floor(Math.random() * 7)
    const newLayout = pickLayoutForCount(count, device)

    // Filter out recently shown photos for freshness
    const recent = recentlyShownRef.current
    let freshPhotos = filterByImageType(data.photos, imageTypeFilter).filter(p => !recent.has(p.id))
    // Only fall back to all photos if fresh pool is truly exhausted
    if (freshPhotos.filter(p => p.thumb && p.display).length < count * 2) {
      freshPhotos = filterByImageType(data.photos, imageTypeFilter)
    }

    // ~1 in 3 taps: pick a random color bucket for a chromatic set
    let colorIdx = -1
    if (colorBuckets.length > 0 && Math.random() < 0.35) {
      const rich = colorBuckets
        .map((b, i) => ({ i, photos: filterByImageType(b.photos, imageTypeFilter).filter(p => !recent.has(p.id) && p.thumb && p.display) }))
        .filter(x => x.photos.length >= count)
      if (rich.length > 0) {
        const pick = rich[Math.floor(Math.random() * rich.length)]
        colorIdx = pick.i
        freshPhotos = pick.photos
      }
    }

    const allPhotos = freshPhotos

    // Set unit ratio for cropFitness
    const containerRatio = newLayout.device === 'mobile' ? (2 / 3) : (3 / 2)
    _activeUnitRatio = containerRatio * newLayout.rows / newLayout.cols

    // Shuffle curators — try until one succeeds (each tap gets a different curation style)
    const shuffled = [...CURATORS].sort(() => Math.random() - 0.5)
    let bestResult: Photo[] = []
    let bestCurator = ''
    for (const curator of shuffled) {
      const result = curator(allPhotos, newLayout.cells)
      if (result.length >= newLayout.cells.length) {
        bestResult = result.slice(0, newLayout.cells.length)
        bestCurator = curator.name
        break
      }
    }
    if (bestResult.length === 0) {
      bestResult = fillBentoDefault(allPhotos, newLayout.cells)
      bestCurator = 'default'
    }

    // At most 1 variant as accent — skip when color filtered (variants break coherence)
    if (imageTypeFilter !== 'photo' && variantMap.current.size > 0 && colorIdx < 0) {
      const hasVariant = bestResult.some(p => p.parent)
      if (!hasVariant) {
        // Try to swap one photo that has a variant, preferring smaller tiles
        let injected = false
        for (let i = bestResult.length - 1; i >= 0; i--) {
          const v = variantMap.current.get(bestResult[i].id)
          if (v && (v.display || v.thumb) && !recent.has(v.id)) {
            bestResult[i] = v
            injected = true
            break
          }
        }
        // Fallback: if no selected photo had a variant, pick any random variant
        if (!injected) {
          const allVariants = [...variantMap.current.values()].filter(
            v => (v.display || v.thumb) && !recent.has(v.id)
          )
          if (allVariants.length > 0) {
            const pick = allVariants[Math.floor(Math.random() * allVariants.length)]
            // Inject into second half (smaller tiles)
            const half = Math.floor(bestResult.length / 2)
            const slot = half + Math.floor(Math.random() * (bestResult.length - half))
            bestResult[slot] = pick
          }
        }
      }
    }

    // Track recently shown
    for (const p of bestResult) recent.add(p.id)
    if (recent.size > RECENTLY_SHOWN_CAP) {
      const arr = [...recent]
      recentlyShownRef.current = new Set(arr.slice(arr.length - RECENTLY_SHOWN_CAP))
    }

    setActiveCurator(bestCurator)
    setActiveColorIdx(colorIdx)
    setLayout(newLayout)
    setWorkingCells([...newLayout.cells])
    setPhotos(bestResult)
    revealedRef.current = new Set()
    setRevealedSet(new Set())
    setSplitIndices(new Set())
    requestAnimationFrame(() => refillPreloadBuffer(new Set(bestResult.map(p => p.id))))
  }, [data, colorBuckets, imageTypeFilter, refillPreloadBuffer])

  /* Regenerate when color or image type changes */
  useEffect(() => {
    if (data && colorBuckets.length > 0) generate()
  }, [activeColorIdx, imageTypeFilter]) // eslint-disable-line react-hooks/exhaustive-deps

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
      cells: workingCells.map(c => ({ r: c.r, c: c.c, rs: c.rs, cs: c.cs, orient: c.orient })),
      photos: photos.map(p => p.id),
      displayMode: 'bento',
      density: workingCells.length,
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
  }, [layout, photos, workingCells, activeColorIdx, loved, activeCurator])

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
          const cell = workingCells[i]
          if (!cell || !photo) return null
          const canSplit = isSplittable(cell)
          return (
            <BentoTile
              key={`${cell.r}-${cell.c}`}
              photo={photo}
              cell={cell}
              cellIndex={i}
              index={i}
              revealed={revealedSet.has(i)}
              hasVariant={!photo.parent && variantMap.current.has(photo.id)}
              splittable={canSplit}
              isSplit={splitIndices.has(i)}
              gridCols={layout.cols}
              gridRows={layout.rows}
              containerRatio={containerRatio}
              onSwap={swapTile}
              onSplit={performSplit}
              onFullscreen={handleFullscreen}
            />
          )
        })}
      </div>
      <div className="view-bottom">
        <ShowControls
          controls={['imageType', 'heart', 'genie']}
          state={{
            activeColorIdx,
            densityStepIdx: 0,
            displayMode: 'bento',
            imageTypeFilter,
            loved,
          }}
          config={{
            validDensities: [],
            colorBuckets: colorBuckets.map(b => ({ color: b.color, hueStart: b.hueStart })),
            hasVariants,
            samplePhoto: samplePhotoRef.current,
            sampleVariant: sampleVariantRef.current,
          }}
          callbacks={{
            onColorChange: handleColorChange,
            onDensityChange: () => {},
            onDisplayModeChange: () => {},
            onImageTypeChange: handleImageTypeChange,
            onGenie: showBestBento,
            onLove: loveBento,
          }}
          compact={isMobile}
        />
      </div>
    </div>
  )
}
