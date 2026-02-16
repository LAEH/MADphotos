import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { shuffleArray, canonKey } from '../lib/utils'
import { hueDiff, hueLabel } from '../lib/colorUtils'
import { fireAndForget } from '../lib/firebase'
import type { Photo, GamePair, DriftNeighbor } from '../types/photo'
import './GameView.css'

/* ===== Constants ===== */

const FAV_KEY = 'sq-couple-favs'
const FAV_MAX = 200
const REJECT_KEY = 'sq-couple-rejects'
const CAM_CAP = 1200
const MAX_APPEARANCES = 3

/* ===== Strategy Types ===== */

interface Strategy {
  id: string
  name: string
  subtitle: string
  icon: string
  type: 'harmony' | 'tension' | 'special'
  needsDrift: boolean
  build: (
    photos: Photo[],
    photoMap: Record<string, Photo>,
    drift: Record<string, DriftNeighbor[]> | null
  ) => GamePair[]
}

/* ===== localStorage Helpers ===== */

function getRejects(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(REJECT_KEY) || '[]'))
  } catch {
    return new Set()
  }
}

function addReject(photoId: string): void {
  const rejects = getRejects()
  rejects.add(photoId)
  localStorage.setItem(REJECT_KEY, JSON.stringify([...rejects]))
  fireAndForget('couple-rejects', { photo: photoId })
}

function addApprove(photoId: string): void {
  fireAndForget('couple-approves', { photo: photoId })
}

function getFavs(): { a: string; b: string }[] {
  try {
    return JSON.parse(localStorage.getItem(FAV_KEY) || '[]')
  } catch {
    return []
  }
}

function setFavs(favs: { a: string; b: string }[]): void {
  localStorage.setItem(FAV_KEY, JSON.stringify(favs.slice(-FAV_MAX)))
}

/* ===== 13 Strategies ===== */

const STRATEGIES: Strategy[] = [
  /* --- Harmony --- */
  {
    id: 'twins',
    name: 'Twins',
    subtitle: 'Uncanny resemblance',
    icon: '\uD83E\uDEDE',
    type: 'harmony',
    needsDrift: true,
    build(_photos, photoMap, drift) {
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      if (!drift) return pairs
      for (const [id, neighbors] of Object.entries(drift)) {
        const a = photoMap[id]
        if (!a || !a.thumb || (a.aesthetic || 0) < 9.5) continue
        for (const nb of neighbors.slice(0, 3)) {
          if (!nb || nb.score < 0.60) continue
          const b = photoMap[nb.id]
          if (!b || !b.thumb || (b.aesthetic || 0) < 9.5) continue
          const key = canonKey(a.id, b.id)
          if (seen.has(key)) continue
          seen.add(key)
          pairs.push({ a, b, reason: `drift ${nb.score.toFixed(2)}` })
        }
      }
      return pairs
    },
  },
  {
    id: 'chromatic',
    name: 'Chromatic',
    subtitle: 'Same palette, different subject',
    icon: '\uD83C\uDFA8',
    type: 'harmony',
    needsDrift: false,
    build(photos) {
      const buckets: Record<number, Photo[]> = {}
      for (const p of photos) {
        if (p.mono || p.hue == null || (p.aesthetic || 0) < 9.5) continue
        const bucket = Math.floor(p.hue / 15) % 24
        ;(buckets[bucket] = buckets[bucket] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      for (const group of Object.values(buckets)) {
        if (group.length < 2) continue
        const shuffled = shuffleArray([...group])
        for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
          const a = shuffled[i]
          for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
            const b = shuffled[j]
            if (a.scene === b.scene) continue
            if (Math.abs((a.brightness || 50) - (b.brightness || 50)) > 20) continue
            if (Math.abs((a.contrast || 50) - (b.contrast || 50)) > 15) continue
            const key = canonKey(a.id, b.id)
            if (seen.has(key)) continue
            seen.add(key)
            pairs.push({ a, b, reason: `${hueLabel(a.hue!)} ~${Math.round(a.hue!)}\u00B0` })
            break
          }
        }
      }
      return pairs
    },
  },
  {
    id: 'texture',
    name: 'Texture',
    subtitle: 'Same feel, same gaze',
    icon: '\uD83E\uDDF5',
    type: 'harmony',
    needsDrift: false,
    build(photos) {
      const buckets: Record<string, Photo[]> = {}
      for (const p of photos) {
        if (!p.depth || !p.composition || !p.style || (p.aesthetic || 0) < 9.5) continue
        const key = p.depth + '|' + p.composition + '|' + p.style
        ;(buckets[key] = buckets[key] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      for (const group of Object.values(buckets)) {
        if (group.length < 2) continue
        const shuffled = shuffleArray([...group])
        for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
          const a = shuffled[i]
          for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
            const b = shuffled[j]
            if (Math.abs((a.depth_complexity || 0) - (b.depth_complexity || 0)) > 0.3) continue
            if (a.scene === b.scene) continue
            const key = canonKey(a.id, b.id)
            if (seen.has(key)) continue
            seen.add(key)
            pairs.push({ a, b, reason: `${a.style} \u2014 ${a.depth}, ${a.composition}` })
            break
          }
        }
      }
      return pairs
    },
  },
  {
    id: 'timewarp',
    name: 'Time Warp',
    subtitle: 'Years apart, same spirit',
    icon: '\u23F3',
    type: 'harmony',
    needsDrift: false,
    build(photos) {
      const buckets: Record<string, Photo[]> = {}
      for (const p of photos) {
        if (!p.date || !p.scene || !p.style || (p.aesthetic || 0) < 9.5) continue
        const key = p.scene + '|' + p.style
        ;(buckets[key] = buckets[key] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      for (const group of Object.values(buckets)) {
        if (group.length < 2) continue
        const sorted = [...group].sort((a, b) => a.date!.localeCompare(b.date!))
        for (let i = 0; i < sorted.length - 1 && pairs.length < 500; i++) {
          const a = sorted[i]
          for (let j = sorted.length - 1; j > i && pairs.length < 500; j--) {
            const b = sorted[j]
            const ya = new Date(a.date!).getFullYear()
            const yb = new Date(b.date!).getFullYear()
            if (Math.abs(yb - ya) < 3) continue
            if (Math.abs((a.brightness || 50) - (b.brightness || 50)) > 25) continue
            const key = canonKey(a.id, b.id)
            if (seen.has(key)) continue
            seen.add(key)
            pairs.push({ a, b, reason: `${a.scene}, ${a.style} \u2014 ${ya} \u2194 ${yb}` })
            break
          }
        }
      }
      return pairs
    },
  },
  {
    id: 'solitude',
    name: 'Solitude',
    subtitle: 'Quiet frames, same world',
    icon: '\uD83C\uDF2C\uFE0F',
    type: 'harmony',
    needsDrift: false,
    build(photos) {
      const lonely = photos.filter(
        (p) =>
          (p.aesthetic || 0) >= 9.5 &&
          (p.face_count || 0) === 0 &&
          !(p.objects || []).includes('person') &&
          p.saliency &&
          p.saliency.spread < 16 &&
          p.scene &&
          p.depth
      )
      const buckets: Record<string, Photo[]> = {}
      for (const p of lonely) {
        ;(buckets[p.scene!] = buckets[p.scene!] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      for (const group of Object.values(buckets)) {
        if (group.length < 2) continue
        const shuffled = shuffleArray([...group])
        for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
          const a = shuffled[i]
          for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
            const b = shuffled[j]
            if (Math.abs((a.brightness || 50) - (b.brightness || 50)) > 20) continue
            if (a.depth !== b.depth) continue
            const key = canonKey(a.id, b.id)
            if (seen.has(key)) continue
            seen.add(key)
            pairs.push({ a, b, reason: `${a.scene} \u2014 quiet, ${a.depth}` })
            break
          }
        }
      }
      return pairs
    },
  },
  {
    id: 'moodring',
    name: 'Mood Ring',
    subtitle: 'Same emotion, same place, different eye',
    icon: '\uD83D\uDE36\u200D\uD83C\uDF2B\uFE0F',
    type: 'harmony',
    needsDrift: false,
    build(photos) {
      const buckets: Record<string, Photo[]> = {}
      for (const p of photos) {
        if (!p.emotion || !p.scene || (p.aesthetic || 0) < 9.5) continue
        const key = p.emotion + '|' + p.scene
        ;(buckets[key] = buckets[key] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      for (const [bucket, group] of Object.entries(buckets)) {
        if (group.length < 2) continue
        const shuffled = shuffleArray([...group])
        for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
          const a = shuffled[i]
          for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
            const b = shuffled[j]
            if (a.camera === b.camera && a.style === b.style) continue
            const key = canonKey(a.id, b.id)
            if (seen.has(key)) continue
            seen.add(key)
            const [emotion, scene] = bucket.split('|')
            pairs.push({ a, b, reason: `${emotion} \u2014 ${scene}` })
            break
          }
        }
      }
      return pairs
    },
  },

  /* --- Tension --- */
  {
    id: 'complement',
    name: 'Complement',
    subtitle: 'Opposite colors, shared soul',
    icon: '\uD83C\uDF08',
    type: 'tension',
    needsDrift: false,
    build(photos) {
      const colored = photos.filter(
        (p) => !p.mono && p.hue != null && (p.aesthetic || 0) >= 9.5
      )
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      const shuffled = shuffleArray([...colored])
      for (let i = 0; i < shuffled.length && pairs.length < 500; i++) {
        const a = shuffled[i]
        for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
          const b = shuffled[j]
          const diff = hueDiff(a.hue!, b.hue!)
          if (diff < 150 || diff > 210) continue
          const sharedVibe = (a.vibes || []).find((v) => (b.vibes || []).includes(v))
          if (!sharedVibe) continue
          const key = canonKey(a.id, b.id)
          if (seen.has(key)) continue
          seen.add(key)
          pairs.push({
            a,
            b,
            reason: `${hueLabel(a.hue!)} \u2194 ${hueLabel(b.hue!)} \u2014 ${sharedVibe}`,
          })
          break
        }
      }
      return pairs
    },
  },
  {
    id: 'strangers',
    name: 'Strangers',
    subtitle: 'Same place, different world',
    icon: '\uD83D\uDC65',
    type: 'tension',
    needsDrift: false,
    build(photos) {
      const buckets: Record<string, Photo[]> = {}
      for (const p of photos) {
        if (!p.scene || !p.style || !p.composition || (p.aesthetic || 0) < 9.5) continue
        ;(buckets[p.scene] = buckets[p.scene] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      for (const group of Object.values(buckets)) {
        if (group.length < 2) continue
        const shuffled = shuffleArray([...group])
        for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
          const a = shuffled[i]
          for (let j = i + 1; j < shuffled.length; j++) {
            const b = shuffled[j]
            let diffs = 0
            if (a.time !== b.time) diffs++
            if (a.style !== b.style) diffs++
            if (a.grading !== b.grading) diffs++
            if (diffs < 2) continue
            if (a.composition !== b.composition) continue
            const key = canonKey(a.id, b.id)
            if (seen.has(key)) continue
            seen.add(key)
            pairs.push({ a, b, reason: `${a.scene} \u2014 ${a.style} vs ${b.style}` })
            break
          }
        }
      }
      return pairs
    },
  },
  {
    id: 'lightdark',
    name: 'Light & Dark',
    subtitle: 'Brightness extremes',
    icon: '\u25D1',
    type: 'tension',
    needsDrift: false,
    build(photos) {
      const quality = photos.filter(
        (p) => p.brightness != null && (p.aesthetic || 0) >= 9.5
      )
      const sorted = [...quality].sort((a, b) => a.brightness! - b.brightness!)
      const cut = Math.floor(sorted.length * 0.15)
      const darks = sorted.slice(0, cut)
      const lights = sorted.slice(-cut)
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      const shuffledD = shuffleArray([...darks])
      const shuffledL = shuffleArray([...lights])
      for (let i = 0; i < shuffledD.length && pairs.length < 500; i++) {
        const a = shuffledD[i]
        for (let j = 0; j < shuffledL.length && pairs.length < 500; j++) {
          const b = shuffledL[j]
          const sharedScene = a.scene && a.scene === b.scene
          const sharedVibe = (a.vibes || []).some((v) => (b.vibes || []).includes(v))
          const sharedObj = (a.objects || []).some((o) => (b.objects || []).includes(o))
          if (!sharedScene && !(sharedVibe && sharedObj)) continue
          const key = canonKey(a.id, b.id)
          if (seen.has(key)) continue
          seen.add(key)
          const link = sharedScene ? a.scene : ''
          pairs.push({
            a,
            b,
            reason: `${Math.round(a.brightness!)} vs ${Math.round(b.brightness!)}${link ? ' \u2014 ' + link : ''}`,
          })
          break
        }
      }
      return pairs
    },
  },
  {
    id: 'doppelganger',
    name: 'Doppelganger',
    subtitle: 'Same object, different world',
    icon: '\uD83E\uDE9E',
    type: 'tension',
    needsDrift: false,
    build(photos) {
      const skip = new Set([
        'person',
        'car',
        'tree',
        'building',
        'sky',
        'wall',
        'floor',
        'window',
        'traffic light',
        'truck',
        'couch',
        'chair',
        'tv',
        'bus',
        'bed',
      ])
      const buckets: Record<string, Photo[]> = {}
      for (const p of photos) {
        if ((p.aesthetic || 0) < 9.5 || !p.depth) continue
        for (const obj of p.objects || []) {
          if (skip.has(obj)) continue
          ;(buckets[obj] = buckets[obj] || []).push(p)
        }
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      for (const [obj, group] of Object.entries(buckets)) {
        if (group.length < 2 || group.length > 200) continue
        const shuffled = shuffleArray([...group])
        for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
          const a = shuffled[i]
          for (let j = i + 1; j < shuffled.length; j++) {
            const b = shuffled[j]
            if (a.scene === b.scene) continue
            if (a.depth !== b.depth) continue
            const key = canonKey(a.id, b.id)
            if (seen.has(key)) continue
            seen.add(key)
            pairs.push({ a, b, reason: `${obj} \u2014 ${a.scene} vs ${b.scene}` })
            break
          }
        }
      }
      return pairs
    },
  },
  {
    id: 'monochrome',
    name: 'Monochrome',
    subtitle: 'Color meets its shadow',
    icon: '\u25AB\u25AA',
    type: 'tension',
    needsDrift: false,
    build(photos) {
      const monos = photos.filter(
        (p) => p.mono && p.scene && p.composition && (p.aesthetic || 0) >= 9.5
      )
      const colorByScene: Record<string, Photo[]> = {}
      for (const p of photos) {
        if (p.mono || !p.scene || !p.composition || (p.aesthetic || 0) < 9.5) continue
        ;(colorByScene[p.scene] = colorByScene[p.scene] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      const shuffledM = shuffleArray([...monos])
      for (const a of shuffledM) {
        const candidates = colorByScene[a.scene!]
        if (!candidates) continue
        for (const b of shuffleArray([...candidates])) {
          if (a.composition !== b.composition) continue
          const key = canonKey(a.id, b.id)
          if (seen.has(key)) continue
          seen.add(key)
          pairs.push({ a, b, reason: `mono \u00D7 color \u2014 ${a.scene}, ${a.composition}` })
          break
        }
        if (pairs.length >= 500) break
      }
      return pairs
    },
  },
  {
    id: 'bento',
    name: 'Bento',
    subtitle: 'Portrait meets landscape',
    icon: '\uD83C\uDFDE\uFE0F',
    type: 'tension',
    needsDrift: false,
    build(photos) {
      const portraits = photos.filter(
        (p) =>
          p.orientation === 'portrait' &&
          p.scene &&
          p.style &&
          (p.aesthetic || 0) >= 9.5
      )
      const lsBySceneStyle: Record<string, Photo[]> = {}
      for (const p of photos) {
        if (
          p.orientation !== 'landscape' ||
          !p.scene ||
          !p.style ||
          (p.aesthetic || 0) < 9.5
        )
          continue
        const key = p.scene + '|' + p.style
        ;(lsBySceneStyle[key] = lsBySceneStyle[key] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      const shuffledP = shuffleArray([...portraits])
      for (const a of shuffledP) {
        const k = a.scene + '|' + a.style
        const candidates = lsBySceneStyle[k]
        if (!candidates) continue
        for (const b of shuffleArray([...candidates])) {
          const key = canonKey(a.id, b.id)
          if (seen.has(key)) continue
          seen.add(key)
          pairs.push({
            a,
            b,
            reason: `portrait \u00D7 landscape \u2014 ${a.scene}, ${a.style}`,
          })
          break
        }
        if (pairs.length >= 500) break
      }
      return pairs
    },
  },

  /* --- Special --- */
  {
    id: 'focal',
    name: 'Focal Point',
    subtitle: 'Same gaze, different frame',
    icon: '\uD83C\uDFAF',
    type: 'special',
    needsDrift: false,
    build(photos) {
      const withSaliency = photos.filter(
        (p) => (p.aesthetic || 0) >= 9.5 && p.saliency && p.depth && p.scene
      )
      const buckets: Record<string, Photo[]> = {}
      for (const p of withSaliency) {
        const qx = p.saliency!.px < 0.5 ? 'L' : 'R'
        const qy = p.saliency!.py < 0.5 ? 'T' : 'B'
        const key = qx + qy + '|' + p.depth
        ;(buckets[key] = buckets[key] || []).push(p)
      }
      const pairs: GamePair[] = []
      const seen = new Set<string>()
      for (const group of Object.values(buckets)) {
        if (group.length < 2) continue
        const shuffled = shuffleArray([...group])
        for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
          const a = shuffled[i]
          for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
            const b = shuffled[j]
            if (a.scene === b.scene) continue
            const spDist = Math.hypot(
              a.saliency!.px - b.saliency!.px,
              a.saliency!.py - b.saliency!.py
            )
            if (spDist > 0.2) continue
            if (Math.abs((a.brightness || 50) - (b.brightness || 50)) > 20) continue
            const key = canonKey(a.id, b.id)
            if (seen.has(key)) continue
            seen.add(key)
            pairs.push({ a, b, reason: `focal match \u2014 ${a.depth}` })
            break
          }
        }
      }
      return pairs
    },
  },
]

/* ===== Build All Pairs ===== */

async function buildAllPairs(
  data: { photos: Photo[] },
  photoMap: Record<string, Photo>,
  drift: Record<string, DriftNeighbor[]>
): Promise<GamePair[]> {
  const rejects = getRejects()
  const allPhotos = data.photos.filter((p) => p.thumb && !rejects.has(p.id))

  /* Camera-diverse sampling: cap each camera at CAM_CAP photos */
  const byCam: Record<string, Photo[]> = {}
  for (const p of allPhotos) {
    const cam = p.camera || 'unknown'
    ;(byCam[cam] = byCam[cam] || []).push(p)
  }
  const photos: Photo[] = []
  for (const group of Object.values(byCam)) {
    if (group.length <= CAM_CAP) {
      photos.push(...group)
    } else {
      photos.push(...shuffleArray([...group]).slice(0, CAM_CAP))
    }
  }

  const all: GamePair[] = []

  /* Yield between strategies to avoid blocking the main thread */
  for (const strat of STRATEGIES) {
    await new Promise((r) => setTimeout(r, 0))
    const pool = strat.build(photos, photoMap, strat.needsDrift ? drift : null)
    for (const pair of pool) pair.strategy = strat.id
    all.push(...pool)
  }

  /* Global dedup: cap each photo to max MAX_APPEARANCES across all pairs */
  const appearances: Record<string, number> = {}
  const deduped = shuffleArray(all).filter((pair) => {
    const cA = (appearances[pair.a.id] = (appearances[pair.a.id] || 0) + 1)
    const cB = (appearances[pair.b.id] = (appearances[pair.b.id] || 0) + 1)
    return cA <= MAX_APPEARANCES && cB <= MAX_APPEARANCES
  })

  return deduped
}

/* ===== Image Card ===== */

function JeuCard({
  photo,
  mixed,
  onReject,
  onClickImg,
}: {
  photo: Photo
  mixed: boolean
  onReject: (id: string) => void
  onClickImg: (photo: Photo) => void
}) {
  const [rejected, setRejected] = useState(false)
  const [approved, setApproved] = useState(false)
  const approveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const imgRef = useCallback(
    (el: HTMLImageElement | null) => {
      if (el) loadProgressive(el, photo, 'display')
    },
    [photo]
  )

  useEffect(() => {
    return () => {
      if (approveTimer.current) clearTimeout(approveTimer.current)
    }
  }, [])

  const orient =
    photo.orientation === 'portrait' ? 'jeu-img-portrait' : 'jeu-img-landscape'

  return (
    <div
      className={`jeu-card${rejected ? ' jeu-card-rejected' : ''}${approved ? ' jeu-card-approved' : ''}`}
      style={{
        backgroundColor:
          photo.palette && photo.palette[0] ? photo.palette[0] + '40' : undefined,
      }}
    >
      <img
        ref={imgRef}
        className={`jeu-img clickable-img${mixed ? ' ' + orient : ''}`}
        alt=""
        onClick={() => onClickImg(photo)}
      />
      <div className="jeu-card-actions">
        <button
          className="jeu-card-btn jeu-card-reject"
          title="Reject this photo"
          onClick={(e) => {
            e.stopPropagation()
            setRejected(true)
            onReject(photo.id)
          }}
        >
          {'\u2715'}
        </button>
        <button
          className="jeu-card-btn jeu-card-approve"
          title="Good photo"
          onClick={(e) => {
            e.stopPropagation()
            setApproved(true)
            addApprove(photo.id)
            approveTimer.current = setTimeout(() => setApproved(false), 600)
          }}
        >
          {'\u2713'}
        </button>
      </div>
    </div>
  )
}

/* ===== Favorites Overlay ===== */

function FavsOverlay({
  onClose,
  photoMap,
}: {
  onClose: () => void
  photoMap: Record<string, Photo>
}) {
  const openLightbox = useAppStore((s) => s.openLightbox)
  const [favs, setFavsState] = useState(getFavs)

  const handleRemove = useCallback(
    (idx: number) => {
      const updated = favs.filter((_, i) => i !== idx)
      setFavs(updated)
      setFavsState(updated)
    },
    [favs]
  )

  const handleClearAll = useCallback(() => {
    setFavs([])
    setFavsState([])
    onClose()
  }, [onClose])

  return (
    <div className="jeu-favs-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="jeu-favs-inner">
        <div className="jeu-favs-header">
          <span>Saved Pairs ({favs.length})</span>
          <button className="jeu-favs-close" onClick={onClose}>
            {'\u2715'}
          </button>
        </div>

        {favs.length === 0 ? (
          <div className="jeu-favs-empty">
            No saved pairs yet. Tap \uD83D\uDC4D to save pairs you like!
          </div>
        ) : (
          <div className="jeu-favs-list">
            {[...favs].reverse().map((fav, ri) => {
              const idx = favs.length - 1 - ri
              const photoA = photoMap[fav.a]
              const photoB = photoMap[fav.b]
              if (!photoA || !photoB) return null
              return (
                <FavRow
                  key={`${fav.a}-${fav.b}`}
                  photoA={photoA}
                  photoB={photoB}
                  onRemove={() => handleRemove(idx)}
                  onClickThumb={(photo) => openLightbox(photo)}
                />
              )
            })}
          </div>
        )}

        {favs.length > 0 && (
          <button className="jeu-favs-clear" onClick={handleClearAll}>
            Clear All
          </button>
        )}
      </div>
    </div>
  )
}

function FavRow({
  photoA,
  photoB,
  onRemove,
  onClickThumb,
}: {
  photoA: Photo
  photoB: Photo
  onRemove: () => void
  onClickThumb: (photo: Photo) => void
}) {
  const imgRefA = useCallback(
    (el: HTMLImageElement | null) => {
      if (el) loadProgressive(el, photoA, 'thumb')
    },
    [photoA]
  )
  const imgRefB = useCallback(
    (el: HTMLImageElement | null) => {
      if (el) loadProgressive(el, photoB, 'thumb')
    },
    [photoB]
  )

  return (
    <div className="jeu-fav-row">
      <img
        ref={imgRefA}
        className="jeu-fav-thumb"
        alt=""
        onClick={() => onClickThumb(photoA)}
      />
      <img
        ref={imgRefB}
        className="jeu-fav-thumb"
        alt=""
        onClick={() => onClickThumb(photoB)}
      />
      <button
        className="jeu-fav-remove"
        onClick={(e) => {
          e.stopPropagation()
          onRemove()
        }}
      >
        {'\u2715'}
      </button>
    </div>
  )
}

/* ===== Main Component ===== */

export function GameView() {
  const data = useAppStore((s) => s.data)
  const photoMap = useAppStore((s) => s.photoMap)
  const loadDriftNeighbors = useAppStore((s) => s.loadDriftNeighbors)
  const openLightbox = useAppStore((s) => s.openLightbox)

  const [pool, setPool] = useState<GamePair[]>([])
  const [index, setIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showFavs, setShowFavs] = useState(false)
  const [favCount, setFavCount] = useState(() => getFavs().length)
  const [animClass, setAnimClass] = useState<'enter' | 'exit' | ''>('enter')

  const pairRef = useRef<HTMLDivElement>(null)
  const touchStartRef = useRef({ x: 0, y: 0 })
  const upBtnRef = useRef<HTMLButtonElement>(null)

  /* Build pairs on mount */
  useEffect(() => {
    if (!data) return
    let cancelled = false

    async function init() {
      const drift = await loadDriftNeighbors()
      if (cancelled) return
      const pairs = await buildAllPairs(data!, photoMap, drift)
      if (cancelled) return
      setPool(pairs)
      setIndex(0)
      setLoading(false)
      /* Trigger enter animation */
      setAnimClass('enter')
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setAnimClass('')
        })
      })
    }

    init()
    return () => {
      cancelled = true
    }
  }, [data, photoMap, loadDriftNeighbors])

  /* Navigate to next pair */
  const nextPair = useCallback(() => {
    setAnimClass('exit')
    setTimeout(() => {
      setIndex((prev) => {
        let next = prev + 1
        if (next >= pool.length) {
          /* Reshuffle when exhausted */
          setPool((p) => shuffleArray([...p]))
          next = 0
        }
        return next
      })
      setAnimClass('enter')
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setAnimClass('')
        })
      })
    }, 300)
  }, [pool.length])

  /* Save current pair as favorite */
  const saveFav = useCallback(() => {
    const pair = pool[index]
    if (!pair) return

    const favs = getFavs()
    const exists = favs.some(
      (f) =>
        (f.a === pair.a.id && f.b === pair.b.id) ||
        (f.a === pair.b.id && f.b === pair.a.id)
    )
    if (!exists) {
      favs.push({ a: pair.a.id, b: pair.b.id })
      setFavs(favs)
    }
    setFavCount(getFavs().length)

    fireAndForget('couple-likes', {
      a: pair.a.id,
      b: pair.b.id,
      strategy: pair.strategy || 'unknown',
    })

    /* Pulse animation on thumbs-up button */
    if (upBtnRef.current) {
      upBtnRef.current.classList.add('jeu-btn-pulse')
      upBtnRef.current.addEventListener(
        'animationend',
        () => upBtnRef.current?.classList.remove('jeu-btn-pulse'),
        { once: true }
      )
    }

    nextPair()
  }, [pool, index, nextPair])

  /* Handle reject: remove all pairs with this photo from pool */
  const handleReject = useCallback(
    (photoId: string) => {
      addReject(photoId)
      setPool((prev) => {
        const filtered = prev.filter((p) => p.a.id !== photoId && p.b.id !== photoId)
        return filtered
      })
      setTimeout(() => nextPair(), 400)
    },
    [nextPair]
  )

  /* Touch swipe support */
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartRef.current = {
      x: e.touches[0].clientX,
      y: e.touches[0].clientY,
    }
  }, [])

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const dx = e.changedTouches[0].clientX - touchStartRef.current.x
      const dy = e.changedTouches[0].clientY - touchStartRef.current.y
      if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 50) {
        nextPair()
      }
    },
    [nextPair]
  )

  /* Refresh fav count when overlay closes */
  const handleCloseFavs = useCallback(() => {
    setShowFavs(false)
    setFavCount(getFavs().length)
  }, [])

  /* Determine layout for current pair */
  const pair = pool[index]
  const layout = useMemo(() => {
    if (!pair) return { mixed: false, bothPortrait: false, portraitFirst: false, ordered: [] as Photo[] }
    const oA = pair.a.orientation
    const oB = pair.b.orientation
    const mixed = !!(oA && oB && oA !== oB)
    const bothPortrait = oA === 'portrait' && oB === 'portrait'
    let ordered: Photo[]
    let portraitFirst = false

    if (mixed) {
      portraitFirst = Math.random() < 0.5
      const portrait = oA === 'portrait' ? pair.a : pair.b
      const landscape = oA === 'portrait' ? pair.b : pair.a
      ordered = portraitFirst ? [portrait, landscape] : [landscape, portrait]
    } else {
      ordered = [pair.a, pair.b]
    }

    return { mixed, bothPortrait, portraitFirst, ordered }
  }, [pair])

  if (loading) {
    return <div className="loading">Building pairs...</div>
  }

  if (pool.length === 0) {
    return <div className="loading">No pairs available</div>
  }

  /* Build pair class names */
  const pairClasses = ['jeu-pair']
  if (animClass === 'exit') pairClasses.push('jeu-pair-exit')
  if (animClass === 'enter') pairClasses.push('jeu-pair-enter')
  if (layout.mixed) {
    pairClasses.push('jeu-pair-bento')
    if (!layout.portraitFirst) pairClasses.push('jeu-pair-bento-flip')
  }
  if (layout.bothPortrait) pairClasses.push('jeu-pair-portrait')

  return (
    <div
      className="jeu-container"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <div className={pairClasses.join(' ')} ref={pairRef}>
        {layout.ordered.map((photo) => (
          <JeuCard
            key={photo.id}
            photo={photo}
            mixed={layout.mixed}
            onReject={handleReject}
            onClickImg={(p) => openLightbox(p)}
          />
        ))}
      </div>

      {/* Fixed glass bar */}
      <div className="jeu-bar">
        <button className="jeu-btn" onClick={nextPair}>
          {'\uD83D\uDC4E'}
        </button>
        <button className="jeu-btn jeu-fav-btn" onClick={() => setShowFavs(true)}>
          {'\u2764\uFE0F'}
          <span
            className="jeu-fav-badge"
            style={{ display: favCount > 0 ? undefined : 'none' }}
          >
            {favCount}
          </span>
        </button>
        <button className="jeu-btn" ref={upBtnRef} onClick={saveFav}>
          {'\uD83D\uDC4D'}
        </button>
      </div>

      {/* Favorites overlay */}
      {showFavs && <FavsOverlay onClose={handleCloseFavs} photoMap={photoMap} />}
    </div>
  )
}
