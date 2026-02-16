import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import { loadProgressive } from '../lib/imageLoading'
import { shuffleArray, randomFrom } from '../lib/utils'
import { ViewBottom } from '../components/ui/ViewBottom'
import type { Photo } from '../types/photo'
import './ColorsView.css'

const NUM_BUCKETS = 24

interface ColorBucket {
  hueStart: number
  hueEnd: number
  color: string
  photos: Photo[]
}

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

export function ColorsView() {
  const data = useAppStore(s => s.data)
  const openLightbox = useAppStore(s => s.openLightbox)
  const [buckets, setBuckets] = useState<ColorBucket[]>([])
  const [activeIdx, setActiveIdx] = useState(0)
  const [selected, setSelected] = useState<Photo[]>([])

  useEffect(() => {
    if (!data) return
    const b = buildColorBuckets(data.photos)
    setBuckets(b)
    const nonEmpty = b.map((bucket, i) => ({ bucket, i })).filter(x => x.bucket.photos.length > 0)
    const startIdx = nonEmpty.length > 0 ? randomFrom(nonEmpty).i : 0
    setActiveIdx(startIdx)
  }, [data])

  useEffect(() => {
    if (buckets.length === 0) return
    const bucket = buckets[activeIdx]
    if (!bucket || bucket.photos.length === 0) {
      setSelected([])
      return
    }

    const sorted = [...bucket.photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))
    let picks = sorted.slice(0, 12)

    if (picks.length < 12) {
      const usedIds = new Set(picks.map(p => p.id))
      for (let offset = 1; offset <= 3 && picks.length < 12; offset++) {
        for (const dir of [-1, 1]) {
          const adjIdx = (activeIdx + dir * offset + buckets.length) % buckets.length
          const adj = buckets[adjIdx]
          if (!adj) continue
          const adjSorted = [...adj.photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0))
          for (const p of adjSorted) {
            if (picks.length >= 12) break
            if (!usedIds.has(p.id)) {
              picks.push(p)
              usedIds.add(p.id)
            }
          }
        }
      }
    }

    setSelected(shuffleArray(picks))
  }, [buckets, activeIdx])

  const selectBand = useCallback((idx: number) => {
    setActiveIdx(idx)
  }, [])

  const mobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches

  return (
    <div className="couleurs-wrap">
      <div className="couleurs-card" id="couleurs-card">
        {selected.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 14 }}>
            No photos in this range
          </div>
        ) : mobile ? (
          <MobileLayout photos={selected} onClickPhoto={(photo) => openLightbox(photo, selected)} />
        ) : (
          <DesktopLayout photos={selected} onClickPhoto={(photo) => openLightbox(photo, selected)} />
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

function CouleursTile({ photo, onClick }: { photo: Photo; onClick: () => void }) {
  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (el) loadProgressive(el, photo, 'display')
  }, [photo])

  return (
    <div
      className="couleurs-tile"
      style={{ backgroundColor: (photo.palette?.[2] || photo.palette?.[0] || '') + '4D' }}
      onClick={onClick}
    >
      <img ref={imgRef} alt="" />
    </div>
  )
}

function DesktopLayout({ photos, onClickPhoto }: { photos: Photo[]; onClickPhoto: (p: Photo) => void }) {
  const rows = [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]]
  return (
    <>
      {rows.map((indices, rowIdx) => (
        <div key={rowIdx} className="couleurs-row">
          {indices.map(i => photos[i] ? (
            <CouleursTile key={photos[i].id} photo={photos[i]} onClick={() => onClickPhoto(photos[i])} />
          ) : null)}
        </div>
      ))}
    </>
  )
}

function MobileLayout({ photos, onClickPhoto }: { photos: Photo[]; onClickPhoto: (p: Photo) => void }) {
  const patterns = [[2, 1, 1], [1, 1, 2], [1, 2, 1], [2, 1, 1]]
  let idx = 0
  return (
    <>
      {patterns.map((pattern, rowIdx) => (
        <div key={rowIdx} className="couleurs-row">
          {pattern.map((_flex, _colIdx) => {
            const photo = photos[idx]
            if (!photo) return null
            idx++
            return (
              <CouleursTile
                key={photo.id}
                photo={photo}
                onClick={() => onClickPhoto(photo)}
              />
            )
          })}
        </div>
      ))}
    </>
  )
}
