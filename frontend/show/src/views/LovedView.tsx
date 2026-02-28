import { useState, useEffect, useCallback, useRef } from 'react'
import { useAppStore } from '../store/appStore'
import { getObjectPosition, BENTO_UNIT_RATIO } from '../lib/cropUtils'
import { loadProgressive } from '../lib/imageLoading'
import { db } from '../lib/firebase'
import { collection, query, orderBy, getDocs } from 'firebase/firestore'
import type { Photo } from '../types/photo'
import type { BentoCell } from '../lib/cropUtils'
import './LovedView.css'

interface SavedBento {
  layoutId: string
  cols: number
  rows: number
  cells: { r: number; c: number; rs: number; cs: number; orient: string }[]
  photos: string[]  // photo UUIDs
  gridMode: boolean
  density: number
  curator: string
  ts: number  // ms from localStorage, Firestore uses server timestamp
  device: string
}

function formatDate(ts: number): string {
  const d = new Date(ts)
  const month = d.toLocaleDateString('en-US', { month: 'short' })
  const day = d.getDate()
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${month} ${day}, ${time}`
}

function LovedBentoCard({
  bento,
  photoMap,
  onClick,
}: {
  bento: SavedBento
  photoMap: Record<string, Photo>
  onClick: () => void
}) {
  const containerRatio = (bento.cols * BENTO_UNIT_RATIO) / bento.rows

  return (
    <div className="loved-card" onClick={onClick}>
      <div
        className="loved-card-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${bento.cols}, 1fr)`,
          gridTemplateRows: `repeat(${bento.rows}, 1fr)`,
          gap: '2px',
          aspectRatio: containerRatio,
          borderRadius: '10px',
          overflow: 'hidden',
        }}
      >
        {bento.cells.map((cell, i) => {
          const photoId = bento.photos[i]
          const photo = photoId ? photoMap[photoId] : undefined
          if (!photo) return null
          const src = photo.thumb || photo.display
          if (!src) return null
          return (
            <div
              key={`${bento.ts}-${i}`}
              style={{
                gridRow: `${cell.r} / ${cell.r + cell.rs}`,
                gridColumn: `${cell.c} / ${cell.c + cell.cs}`,
                overflow: 'hidden',
              }}
            >
              <img
                src={src}
                alt=""
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  objectPosition: getObjectPosition(photo, cell as BentoCell),
                  display: 'block',
                }}
                loading="lazy"
              />
            </div>
          )
        })}
      </div>
      <div className="loved-card-meta">
        <span>{formatDate(bento.ts)}</span>
        <span>{bento.photos.length} photos</span>
        {bento.curator && bento.curator !== 'default' && <span>{bento.curator}</span>}
      </div>
    </div>
  )
}

function LovedBentoViewer({
  bento,
  photoMap,
  onClose,
}: {
  bento: SavedBento
  photoMap: Record<string, Photo>
  onClose: () => void
}) {
  const viewerRef = useRef<HTMLDivElement>(null)
  const containerRatio = (bento.cols * BENTO_UNIT_RATIO) / bento.rows

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      ref={viewerRef}
      className="loved-viewer"
      onClick={(e) => { if (e.target === viewerRef.current) onClose() }}
    >
      <div
        className="loved-viewer-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${bento.cols}, 1fr)`,
          gridTemplateRows: `repeat(${bento.rows}, 1fr)`,
          gap: '4px',
          aspectRatio: containerRatio,
          maxWidth: '90vw',
          maxHeight: '85vh',
          borderRadius: '12px',
          overflow: 'hidden',
        }}
      >
        {bento.cells.map((cell, i) => {
          const photoId = bento.photos[i]
          const photo = photoId ? photoMap[photoId] : undefined
          if (!photo) return null
          const src = photo.display || photo.thumb
          if (!src) return null
          return (
            <div
              key={`${bento.ts}-v-${i}`}
              style={{
                gridRow: `${cell.r} / ${cell.r + cell.rs}`,
                gridColumn: `${cell.c} / ${cell.c + cell.cs}`,
                overflow: 'hidden',
              }}
            >
              <LovedTileImg photo={photo} cell={cell as BentoCell} />
            </div>
          )
        })}
      </div>

      <button className="loved-close" onClick={onClose} aria-label="Close">
        {'\u2715'}
      </button>
    </div>
  )
}

function LovedTileImg({ photo, cell }: { photo: Photo; cell: BentoCell }) {
  const imgRef = useCallback((el: HTMLImageElement | null) => {
    if (!el) return
    loadProgressive(el, photo, 'display', '90vw')
    el.style.objectPosition = getObjectPosition(photo, cell)
  }, [photo, cell])

  return (
    <img
      ref={imgRef}
      alt=""
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        display: 'block',
      }}
    />
  )
}

export function LovedView() {
  const photoMap = useAppStore(s => s.photoMap)
  const [bentos, setBentos] = useState<SavedBento[]>([])
  const [loading, setLoading] = useState(true)
  const [viewerIdx, setViewerIdx] = useState(-1)

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

    // Show local immediately
    if (localBentos.length > 0) {
      setBentos(localBentos.sort((a, b) => (b.ts || 0) - (a.ts || 0)))
      setLoading(false)
    }

    // Also fetch from Firestore (may have loves from other devices/production)
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

        // Merge: dedupe by photo IDs (same composition)
        const seen = new Set<string>()
        const merged: SavedBento[] = []
        for (const b of [...firestoreBentos, ...localBentos]) {
          const key = b.photos.sort().join(',')
          if (!seen.has(key)) {
            seen.add(key)
            merged.push(b)
          }
        }
        merged.sort((a, b) => (b.ts || 0) - (a.ts || 0))
        setBentos(merged)
        setLoading(false)
      })
      .catch(() => {
        // Firestore unavailable — local only is fine
        setLoading(false)
      })
  }, [])

  const activeBento = viewerIdx >= 0 ? bentos[viewerIdx] : null

  // Keyboard nav between bentos
  useEffect(() => {
    if (viewerIdx < 0) return
    const handler = (e: KeyboardEvent) => {
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
          <LovedBentoCard
            key={`${bento.ts}-${i}`}
            bento={bento}
            photoMap={photoMap}
            onClick={() => setViewerIdx(i)}
          />
        ))}
      </div>

      {activeBento && (
        <LovedBentoViewer
          bento={activeBento}
          photoMap={photoMap}
          onClose={() => setViewerIdx(-1)}
        />
      )}
    </div>
  )
}
