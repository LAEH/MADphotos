import { useState, useEffect, useCallback, useRef } from 'react'
import './LovedView.css'

interface LovedBento {
  id: string
  timestamp: number
  layout_id: string
  cols: number
  rows: number
  photo_count: number
  width: number
  height: number
  preview_url: string
  png_url: string
  curator: string
}

function formatDate(ts: number): string {
  const d = new Date(ts * 1000)
  const month = d.toLocaleDateString('en-US', { month: 'short' })
  const day = d.getDate()
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${month} ${day}, ${time}`
}

export function LovedView() {
  const [bentos, setBentos] = useState<LovedBento[]>([])
  const [loading, setLoading] = useState(true)
  const [viewerIdx, setViewerIdx] = useState(-1) // -1 = gallery mode

  // Zoom state
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, startPanX: 0, startPanY: 0 })
  const viewerRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)

  // Fetch loved bentos from server
  useEffect(() => {
    fetch('/api/bento/loved')
      .then(r => r.json())
      .then(data => {
        setBentos(data.bentos || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  // Open viewer
  const openViewer = useCallback((idx: number) => {
    setViewerIdx(idx)
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }, [])

  // Close viewer
  const closeViewer = useCallback(() => {
    setViewerIdx(-1)
  }, [])

  // Navigate between bentos
  const navigate = useCallback((dir: number) => {
    setViewerIdx(prev => {
      const next = prev + dir
      if (next < 0 || next >= bentos.length) return prev
      setZoom(1)
      setPan({ x: 0, y: 0 })
      return next
    })
  }, [bentos.length])

  // Zoom controls
  const zoomIn = useCallback(() => {
    setZoom(z => Math.min(4, z * 1.5))
  }, [])

  const zoomOut = useCallback(() => {
    setZoom(z => Math.max(0.25, z / 1.5))
  }, [])

  const resetZoom = useCallback(() => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }, [])

  // Mouse wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
    setZoom(z => Math.max(0.25, Math.min(4, z * factor)))
  }, [])

  // Pan (drag)
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (zoom <= 1) return
    e.preventDefault()
    dragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      startPanX: pan.x,
      startPanY: pan.y,
    }
  }, [zoom, pan])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragRef.current.dragging) return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    setPan({
      x: dragRef.current.startPanX + dx / zoom,
      y: dragRef.current.startPanY + dy / zoom,
    })
  }, [zoom])

  const handleMouseUp = useCallback(() => {
    dragRef.current.dragging = false
  }, [])

  // Keyboard
  useEffect(() => {
    if (viewerIdx < 0) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeViewer()
      else if (e.key === 'ArrowLeft') navigate(-1)
      else if (e.key === 'ArrowRight') navigate(1)
      else if (e.key === '=' || e.key === '+') { e.preventDefault(); zoomIn() }
      else if (e.key === '-') { e.preventDefault(); zoomOut() }
      else if (e.key === '0') { e.preventDefault(); resetZoom() }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [viewerIdx, closeViewer, navigate, zoomIn, zoomOut, resetZoom])

  // Touch zoom (pinch)
  const touchRef = useRef({ dist: 0, baseZoom: 1 })
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX
      const dy = e.touches[0].clientY - e.touches[1].clientY
      touchRef.current = { dist: Math.hypot(dx, dy), baseZoom: zoom }
    }
  }, [zoom])

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      e.preventDefault()
      const dx = e.touches[0].clientX - e.touches[1].clientX
      const dy = e.touches[0].clientY - e.touches[1].clientY
      const dist = Math.hypot(dx, dy)
      const scale = dist / (touchRef.current.dist || 1)
      setZoom(Math.max(0.25, Math.min(4, touchRef.current.baseZoom * scale)))
    }
  }, [])

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

  const activeBento = viewerIdx >= 0 ? bentos[viewerIdx] : null

  return (
    <div className="loved-wrap">
      {/* Gallery grid */}
      <div className="loved-gallery">
        {bentos.map((bento, i) => (
          <div
            key={bento.id}
            className="loved-card"
            onClick={() => openViewer(i)}
          >
            <img
              src={bento.preview_url}
              alt={`Bento ${bento.layout_id}`}
              loading="lazy"
            />
            <div className="loved-card-meta">
              <span>{formatDate(bento.timestamp)}</span>
              <span>{bento.photo_count} photos</span>
              {bento.curator && <span>{bento.curator}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* Full-screen zoom viewer */}
      {activeBento && (
        <div
          ref={viewerRef}
          className="loved-viewer"
          onClick={(e) => { if (e.target === viewerRef.current) closeViewer() }}
          onWheel={handleWheel}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
        >
          <img
            ref={imgRef}
            className={`loved-viewer-img${dragRef.current.dragging ? ' dragging' : ''}`}
            src={activeBento.png_url}
            alt=""
            style={{
              transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
              maxWidth: zoom <= 1 ? '90vw' : 'none',
              maxHeight: zoom <= 1 ? '85vh' : 'none',
            }}
            onMouseDown={handleMouseDown}
            draggable={false}
          />

          {/* Close */}
          <button className="loved-close" onClick={closeViewer} aria-label="Close">
            {'\u2715'}
          </button>

          {/* Counter */}
          <div className="loved-counter">
            {viewerIdx + 1} / {bentos.length}
          </div>

          {/* Nav arrows */}
          {viewerIdx > 0 && (
            <button className="loved-nav loved-nav-prev" onClick={() => navigate(-1)} aria-label="Previous">
              {'\u2039'}
            </button>
          )}
          {viewerIdx < bentos.length - 1 && (
            <button className="loved-nav loved-nav-next" onClick={() => navigate(1)} aria-label="Next">
              {'\u203A'}
            </button>
          )}

          {/* Zoom controls */}
          <div className="loved-zoom-controls">
            <button className="loved-zoom-btn" onClick={zoomOut} aria-label="Zoom out">{'\u2212'}</button>
            <button className="loved-zoom-btn" onClick={resetZoom} aria-label="Reset zoom">
              <span className="loved-zoom-label">{Math.round(zoom * 100)}%</span>
            </button>
            <button className="loved-zoom-btn" onClick={zoomIn} aria-label="Zoom in">{'\u002B'}</button>
          </div>
        </div>
      )}
    </div>
  )
}
