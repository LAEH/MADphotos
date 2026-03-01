import { useState, useEffect, useCallback, useRef } from 'react'
import { useAppStore } from '../store/appStore'
import { getObjectPosition } from '../lib/cropUtils'
import { loadProgressive } from '../lib/imageLoading'
import { db } from '../lib/firebase'
import { collection, query, orderBy, getDocs } from 'firebase/firestore'
import { ShowControls } from '../components/controls/ShowControls'
import type { Photo } from '../types/photo'
import type { BentoCell } from '../lib/cropUtils'
import './LovedView.css'

interface SavedBento {
  layoutId: string
  cols: number
  rows: number
  cells: { r: number; c: number; rs: number; cs: number; orient: string }[]
  photos: string[]
  gridMode: boolean
  density: number
  curator: string
  ts: number
  device: string
}

function formatDate(ts: number): string {
  const d = new Date(ts)
  const month = d.toLocaleDateString('en-US', { month: 'short' })
  const day = d.getDate()
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${month} ${day}, ${time}`
}

/* Tile that mirrors BentoView's .bento-tile exactly */
function LovedTile({
  photo, cell, tier, gridCols, gridRows, containerRatio,
}: {
  photo: Photo
  cell: BentoCell
  tier: 'thumb' | 'display'
  gridCols: number
  gridRows: number
  containerRatio: number
}) {
  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (!el) return
    loadProgressive(el, photo, tier, tier === 'display' ? '90vw' : '50vw')
    el.style.objectPosition = getObjectPosition(photo, cell, gridCols, gridRows, containerRatio)
  }, [photo, cell, tier, gridCols, gridRows, containerRatio])

  const dominant = photo.palette?.[0]

  return (
    <div
      className="loved-tile"
      style={{
        gridRow: `${cell.r} / ${cell.r + cell.rs}`,
        gridColumn: `${cell.c} / ${cell.c + cell.cs}`,
        backgroundColor: dominant ? dominant + '99' : undefined,
      }}
    >
      <img ref={imgRef} alt="" />
    </div>
  )
}

/* Render a bento grid — used by both card and viewer */
function BentoGrid({
  bento, photoMap, tier, className,
}: {
  bento: SavedBento
  photoMap: Record<string, Photo>
  tier: 'thumb' | 'display'
  className: string
}) {
  const containerRatio = bento.device === 'mobile' ? (2 / 3) : (3 / 2)

  return (
    <div
      className={className}
      style={{
        '--bento-cols': bento.cols,
        '--bento-rows': bento.rows,
        aspectRatio: containerRatio,
      } as React.CSSProperties}
    >
      {bento.cells.map((cell, i) => {
        const photoId = bento.photos[i]
        const photo = photoId ? photoMap[photoId] : undefined
        if (!photo) return null
        return (
          <LovedTile
            key={`${bento.ts}-${i}`}
            photo={photo}
            cell={cell as BentoCell}
            tier={tier}
            gridCols={bento.cols}
            gridRows={bento.rows}
            containerRatio={containerRatio}
          />
        )
      })}
    </div>
  )
}

export function LovedView() {
  const photoMap = useAppStore(s => s.photoMap)
  const [bentos, setBentos] = useState<SavedBento[]>([])
  const [loading, setLoading] = useState(true)
  const [viewerIdx, setViewerIdx] = useState(-1)
  const viewerRef = useRef<HTMLDivElement>(null)

  // Load from localStorage + Firestore
  useEffect(() => {
    const localBentos: SavedBento[] = []
    try {
      const raw = localStorage.getItem('bento-loves')
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          for (const b of parsed) {
            if (b.photos && b.cells && b.cols && b.rows) {
              localBentos.push(b)
            }
          }
        }
      }
    } catch { /* corrupted localStorage */ }

    if (localBentos.length > 0) {
      setBentos(localBentos.sort((a, b) => (b.ts || 0) - (a.ts || 0)))
      setLoading(false)
    }

    getDocs(query(collection(db, 'bento-loves'), orderBy('ts', 'desc')))
      .then(snap => {
        const firestoreBentos: SavedBento[] = []
        snap.forEach(doc => {
          const d = doc.data()
          if (d.photos && d.cells && d.cols && d.rows) {
            firestoreBentos.push({
              layoutId: d.layoutId || '',
              cols: d.cols,
              rows: d.rows,
              cells: d.cells,
              photos: d.photos,
              gridMode: d.gridMode || false,
              density: d.density || 0,
              curator: d.curator || '',
              ts: d.ts?.toMillis?.() || d.ts || Date.now(),
              device: d.device || '',
            })
          }
        })

        const seen = new Set<string>()
        const merged: SavedBento[] = []
        for (const b of [...firestoreBentos, ...localBentos]) {
          const key = [...b.photos].sort().join(',')
          if (!seen.has(key)) {
            seen.add(key)
            merged.push(b)
          }
        }
        merged.sort((a, b) => (b.ts || 0) - (a.ts || 0))
        setBentos(merged)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const activeBento = viewerIdx >= 0 ? bentos[viewerIdx] : null

  // Keyboard
  useEffect(() => {
    if (viewerIdx < 0) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setViewerIdx(-1)
      if (e.key === 'ArrowLeft' && viewerIdx > 0) setViewerIdx(viewerIdx - 1)
      if (e.key === 'ArrowRight' && viewerIdx < bentos.length - 1) setViewerIdx(viewerIdx + 1)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [viewerIdx, bentos.length])

  if (loading) {
    return <div className="loved-wrap"><div className="loved-empty"><p>Loading...</p></div></div>
  }

  if (bentos.length === 0) {
    return (
      <div className="loved-wrap">
        <div className="loved-empty">
          <div className="loved-empty-icon">{'\u2764\uFE0F'}</div>
          <p>No loved bentos yet. Go to Bento and tap the heart.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="loved-wrap">
      <div className="loved-gallery">
        {bentos.map((bento, i) => (
          <div key={`${bento.ts}-${i}`} className="loved-card" onClick={() => setViewerIdx(i)}>
            <BentoGrid bento={bento} photoMap={photoMap} tier="thumb" className="loved-grid" />
            <div className="loved-card-meta">
              <span>{formatDate(bento.ts)}</span>
              <span>{bento.photos.length} photos</span>
            </div>
          </div>
        ))}
      </div>

      {activeBento && (
        <div
          ref={viewerRef}
          className="loved-viewer"
          onClick={(e) => { if (e.target === viewerRef.current) setViewerIdx(-1) }}
        >
          <BentoGrid bento={activeBento} photoMap={photoMap} tier="display" className="loved-grid loved-grid-viewer" />

          <button className="loved-close" onClick={() => setViewerIdx(-1)} aria-label="Close">
            {'\u2715'}
          </button>

          <div className="loved-viewer-controls">
            <ShowControls
              controls={['heart']}
              state={{
                activeColorIdx: -1,
                densityStepIdx: 0,
                displayMode: 'bento',
                imageTypeFilter: 'mixed',
                loved: true,
              }}
              config={{
                validDensities: [],
                colorBuckets: [],
                hasVariants: false,
              }}
              callbacks={{
                onColorChange: () => {},
                onDensityChange: () => {},
                onDisplayModeChange: () => {},
                onImageTypeChange: () => {},
                onGenie: () => {},
                onLove: () => {
                  // Unlove: remove from list
                  const updated = bentos.filter((_, i) => i !== viewerIdx)
                  setBentos(updated)
                  try { localStorage.setItem('bento-loves', JSON.stringify(updated)) } catch { /* */ }
                  if (viewerIdx >= updated.length) setViewerIdx(updated.length - 1)
                  if (updated.length === 0) setViewerIdx(-1)
                },
              }}
            />
          </div>

          <div className="loved-counter">
            {viewerIdx + 1} / {bentos.length}
          </div>

          {viewerIdx > 0 && (
            <button className="loved-nav loved-nav-prev" onClick={() => setViewerIdx(viewerIdx - 1)} aria-label="Previous">
              {'\u2039'}
            </button>
          )}
          {viewerIdx < bentos.length - 1 && (
            <button className="loved-nav loved-nav-next" onClick={() => setViewerIdx(viewerIdx + 1)} aria-label="Next">
              {'\u203A'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
