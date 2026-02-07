import { useState, useEffect, useCallback, useRef } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { Footer } from '../components/layout/Footer'

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
      }}>
        Every photograph in the collection, tiled into ~4K square mosaics.
        Each mosaic sorts the images by a different dimension. Click to zoom.
        <span style={{ opacity: 0.6 }}> Scroll to zoom, drag to pan. Keys: +/- zoom, F fit, 1 actual size, Esc close.</span>
      </p>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
        gap: 'var(--space-6)', marginTop: 'var(--space-4)',
      }}>
        {data.mosaics.map(m => (
          <div
            key={m.filename}
            onClick={() => openMosaic(imageUrl(`/rendered/mosaics/${m.filename}`), m.title)}
            style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', cursor: 'pointer', overflow: 'hidden',
              transition: 'transform var(--duration-fast), box-shadow var(--duration-fast)',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.12)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'none'
              e.currentTarget.style.boxShadow = 'none'
            }}
          >
            <img
              src={imageUrl(`/rendered/mosaics/${m.filename}`)}
              alt={m.title}
              loading="lazy"
              decoding="async"
              width={400}
              height={400}
              style={{ width: '100%', display: 'block', aspectRatio: '1', objectFit: 'cover' }}
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

  const fit = useCallback(() => {
    const img = imgRef.current
    const vp = viewportRef.current
    if (!img?.naturalWidth || !vp) return
    const s = Math.min(vp.clientWidth / img.naturalWidth, (vp.clientHeight - 48) / img.naturalHeight, 1)
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

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.92)', display: 'flex',
      justifyContent: 'center', alignItems: 'center', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: 'var(--space-4) var(--space-5)',
        background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(12px)',
        zIndex: 10001,
      }}>
        <div style={{
          fontSize: 'var(--text-sm)', fontWeight: 700, color: 'rgba(255,255,255,0.95)',
          textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)',
        }}>
          {title}
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <ModalBtn onClick={() => zoom(-1)}>-</ModalBtn>
          <span style={{
            fontSize: 'var(--text-xs)', color: 'rgba(255,255,255,0.6)',
            minWidth: 48, textAlign: 'center', fontVariantNumeric: 'tabular-nums',
          }}>
            {Math.round(scale * 100)}%
          </span>
          <ModalBtn onClick={() => zoom(1)}>+</ModalBtn>
          <ModalBtn onClick={fit}>Fit</ModalBtn>
          <ModalBtn onClick={() => setScale(1)}>1:1</ModalBtn>
          <ModalBtn onClick={onClose}>Close</ModalBtn>
        </div>
      </div>

      {/* Viewport */}
      <div
        ref={viewportRef}
        onMouseDown={onMouseDown}
        style={{
          position: 'fixed', inset: 0, overflow: 'auto',
          cursor: isDragging.current ? 'grabbing' : 'grab',
          zIndex: 10000, paddingTop: 48,
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

function ModalBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.25)',
        color: 'rgba(255,255,255,0.95)', padding: 'var(--space-1) var(--space-3)',
        fontFamily: 'var(--font-sans)', fontSize: 'var(--text-sm)', cursor: 'pointer',
        borderRadius: 'var(--radius-sm)', transition: 'background var(--duration-fast)',
      }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
      onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
    >
      {children}
    </button>
  )
}
