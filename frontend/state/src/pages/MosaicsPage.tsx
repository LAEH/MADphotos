import { useState, useEffect, useCallback, useRef, type ImgHTMLAttributes } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { Footer } from '../components/layout/Footer'

function FadeImg({ className, style, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}`} style={{ aspectRatio: '1', ...style }}>
      <img {...props} onLoad={() => setLoaded(true)} />
    </div>
  )
}

interface Mosaic {
  title: string
  description: string
  filename: string
  count: number
}

interface MosaicsData {
  mosaics: Mosaic[]
}

export function MosaicsPage() {
  const { data, loading, error } = useFetch<MosaicsData>('/api/mosaics')
  const [modalSrc, setModalSrc] = useState<string | null>(null)
  const [modalTitle, setModalTitle] = useState('')

  const openMosaic = useCallback((src: string, title: string) => {
    setModalSrc(src)
    setModalTitle(title)
  }, [])

  const closeMosaic = useCallback(() => {
    setModalSrc(null)
    setModalTitle('')
  }, [])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading mosaics...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  return (
    <>
      <h1 style={{
        fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700,
        letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-2)',
      }}>
        Mosaics
      </h1>
      <p style={{
        fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-4)',
        lineHeight: 'var(--leading-relaxed)',
      }}>
        Every photograph in the collection, tiled into ~4K square mosaics.
        Each mosaic sorts the images by a different dimension. Tap to zoom.
      </p>

      <div className="mosaic-grid">
        {data.mosaics.map(m => (
          <div
            key={m.filename}
            className="mosaic-card"
            onClick={() => openMosaic(imageUrl(`/rendered/mosaics/${m.filename}`), m.title)}
          >
            <FadeImg
              src={imageUrl(`/rendered/mosaics/${m.filename}`)}
              alt={m.title}
              loading="lazy"
              decoding="async"
              width={400}
              height={400}
              style={{ aspectRatio: '1' }}
            />
            <div style={{ padding: 'var(--space-3) var(--space-4)' }}>
              <div style={{
                fontWeight: 700, fontSize: 'var(--text-sm)',
                textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)',
              }}>
                {m.title}
              </div>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--muted)',
                marginTop: 'var(--space-1)', lineHeight: 'var(--leading-normal)',
              }}>
                {m.description}
              </div>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--muted)',
                marginTop: 'var(--space-1)', fontWeight: 600,
              }}>
                {m.count.toLocaleString()} images
              </div>
            </div>
          </div>
        ))}
      </div>

      {modalSrc && <MosaicModal src={modalSrc} title={modalTitle} onClose={closeMosaic} />}

      <Footer />
    </>
  )
}

function MosaicModal({ src, title, onClose }: { src: string; title: string; onClose: () => void }) {
  const [scale, setScale] = useState(1)
  const viewportRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const isDragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const scrollStart = useRef({ x: 0, y: 0 })

  // Touch pinch state
  const lastPinchDist = useRef(0)
  const pinchActive = useRef(false)

  const steps = [0.25, 0.33, 0.5, 0.67, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4]

  const zoom = useCallback((dir: number) => {
    setScale(prev => {
      let idx = 0
      for (let i = 0; i < steps.length; i++) {
        if (Math.abs(steps[i] - prev) < 0.01) { idx = i; break }
        if (steps[i] > prev) { idx = dir > 0 ? i : Math.max(0, i - 1); break }
        idx = i
      }
      idx = Math.max(0, Math.min(steps.length - 1, idx + dir))
      return steps[idx]
    })
  }, [])

  const zoomTo = useCallback((newScale: number) => {
    setScale(Math.max(steps[0], Math.min(steps[steps.length - 1], newScale)))
  }, [])

  const fit = useCallback(() => {
    const img = imgRef.current
    const vp = viewportRef.current
    if (!img?.naturalWidth || !vp) return
    const s = Math.min(vp.clientWidth / img.naturalWidth, (vp.clientHeight - 52) / img.naturalHeight, 1)
    setScale(s)
  }, [])

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === '+' || e.key === '=') zoom(1)
      else if (e.key === '-') zoom(-1)
      else if (e.key === 'f' || e.key === 'F') fit()
      else if (e.key === '1') setScale(1)
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose, zoom, fit])

  // Mouse wheel zoom
  useEffect(() => {
    const vp = viewportRef.current
    if (!vp) return
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      zoom(e.deltaY < 0 ? 1 : -1)
    }
    vp.addEventListener('wheel', handleWheel, { passive: false })
    return () => vp.removeEventListener('wheel', handleWheel)
  }, [zoom])

  // Mouse drag
  const onMouseDown = (e: React.MouseEvent) => {
    isDragging.current = true
    dragStart.current = { x: e.clientX, y: e.clientY }
    const vp = viewportRef.current!
    scrollStart.current = { x: vp.scrollLeft, y: vp.scrollTop }
  }

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return
      const vp = viewportRef.current!
      vp.scrollLeft = scrollStart.current.x - (e.clientX - dragStart.current.x)
      vp.scrollTop = scrollStart.current.y - (e.clientY - dragStart.current.y)
    }
    const onMouseUp = () => { isDragging.current = false }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  // Touch pinch-to-zoom + drag
  useEffect(() => {
    const vp = viewportRef.current
    if (!vp) return

    const getTouchDist = (touches: TouchList) => {
      if (touches.length < 2) return 0
      const dx = touches[0].clientX - touches[1].clientX
      const dy = touches[0].clientY - touches[1].clientY
      return Math.sqrt(dx * dx + dy * dy)
    }

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 2) {
        e.preventDefault()
        pinchActive.current = true
        lastPinchDist.current = getTouchDist(e.touches)
      } else if (e.touches.length === 1) {
        isDragging.current = true
        dragStart.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
        scrollStart.current = { x: vp.scrollLeft, y: vp.scrollTop }
      }
    }

    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length === 2 && pinchActive.current) {
        e.preventDefault()
        const dist = getTouchDist(e.touches)
        if (lastPinchDist.current > 0) {
          const ratio = dist / lastPinchDist.current
          setScale(prev => Math.max(steps[0], Math.min(steps[steps.length - 1], prev * ratio)))
        }
        lastPinchDist.current = dist
      } else if (e.touches.length === 1 && isDragging.current && !pinchActive.current) {
        const dx = e.touches[0].clientX - dragStart.current.x
        const dy = e.touches[0].clientY - dragStart.current.y
        vp.scrollLeft = scrollStart.current.x - dx
        vp.scrollTop = scrollStart.current.y - dy
      }
    }

    const onTouchEnd = (e: TouchEvent) => {
      if (e.touches.length < 2) {
        pinchActive.current = false
        lastPinchDist.current = 0
      }
      if (e.touches.length === 0) {
        isDragging.current = false
      }
    }

    vp.addEventListener('touchstart', onTouchStart, { passive: false })
    vp.addEventListener('touchmove', onTouchMove, { passive: false })
    vp.addEventListener('touchend', onTouchEnd)
    return () => {
      vp.removeEventListener('touchstart', onTouchStart)
      vp.removeEventListener('touchmove', onTouchMove)
      vp.removeEventListener('touchend', onTouchEnd)
    }
  }, [zoomTo])

  return (
    <div className="mosaic-modal">
      {/* Header */}
      <div className="mosaic-modal-header">
        <div className="mosaic-modal-title">
          {title}
        </div>
        <div className="mosaic-modal-controls">
          <button className="modal-btn modal-zoom-step" onClick={() => zoom(-1)}>-</button>
          <span className="modal-zoom-label">
            {Math.round(scale * 100)}%
          </span>
          <button className="modal-btn modal-zoom-step" onClick={() => zoom(1)}>+</button>
          <button className="modal-btn" onClick={fit}>Fit</button>
          <button className="modal-btn" onClick={() => setScale(1)}>1:1</button>
          <button className="modal-btn" onClick={onClose}>Close</button>
        </div>
      </div>

      {/* Viewport */}
      <div
        ref={viewportRef}
        className="mosaic-modal-viewport"
        onMouseDown={onMouseDown}
        style={{
          cursor: isDragging.current ? 'grabbing' : 'grab',
        }}
      >
        <img
          ref={imgRef}
          src={src}
          alt={title}
          draggable={false}
          onLoad={fit}
          style={{
            display: 'block', transformOrigin: '0 0',
            width: imgRef.current?.naturalWidth ? imgRef.current.naturalWidth * scale : undefined,
            height: imgRef.current?.naturalHeight ? imgRef.current.naturalHeight * scale : undefined,
          }}
        />
      </div>
    </div>
  )
}
