import { useState, useEffect, useCallback, useMemo, type ImgHTMLAttributes } from 'react'
import { imageUrl } from '../config'
import { PageShell } from '../components/layout/PageShell'

function FadeImg({ style, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}`} style={style}>
      <img {...props} onLoad={() => setLoaded(true)} style={{ width: '100%', display: 'block' }} />
    </div>
  )
}

interface PickedPhoto {
  uuid: string
  category: string
  orientation: 'portrait' | 'landscape'
  w: number
  h: number
  camera: string
  quality: number | null
}

interface PhotographyData {
  photos: PickedPhoto[]
  portrait: number
  landscape: number
  cameras: Record<string, number>
}

type OrientationFilter = 'all' | 'portrait' | 'landscape'

const PAGE_SIZE = 80

export function PhotographyPage() {
  const [data, setData] = useState<PhotographyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [orientationFilter, setOrientationFilter] = useState<OrientationFilter>('all')
  const [cameraFilter, setCameraFilter] = useState('all')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [lightbox, setLightbox] = useState<PickedPhoto | null>(null)

  const fetchData = useCallback(() => {
    setLoading(true)
    fetch('/api/show/photography')
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then((d: PhotographyData) => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const cameras = useMemo(() => {
    if (!data) return []
    return Object.entries(data.cameras)
      .sort((a, b) => b[1] - a[1])
      .map(([name]) => name)
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    return data.photos.filter(p => {
      if (orientationFilter !== 'all' && p.orientation !== orientationFilter) return false
      if (cameraFilter !== 'all' && p.camera !== cameraFilter) return false
      return true
    })
  }, [data, orientationFilter, cameraFilter])

  const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount])

  useEffect(() => { setVisibleCount(PAGE_SIZE) }, [orientationFilter, cameraFilter])

  // Keyboard: Escape closes lightbox
  useEffect(() => {
    if (!lightbox) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setLightbox(null) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [lightbox])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading photography...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  const subtitle = `${data.photos.length.toLocaleString()} photos \u00b7 ${data.portrait.toLocaleString()} portrait \u00b7 ${data.landscape.toLocaleString()} landscape`

  return (
    <PageShell title="Photography" subtitle={subtitle}>
      {/* Filter bar */}
      <div style={{
        display: 'flex', gap: 'var(--space-3)', alignItems: 'center',
        flexWrap: 'wrap', marginBottom: 'var(--space-5)',
      }}>
        {(['all', 'portrait', 'landscape'] as OrientationFilter[]).map(f => {
          const count = f === 'all' ? data.photos.length
            : f === 'portrait' ? data.portrait : data.landscape
          return (
            <button key={f} onClick={() => setOrientationFilter(f)} style={filterBtnStyle(orientationFilter === f)}>
              {f === 'all' ? 'All' : f === 'portrait' ? 'Portrait' : 'Landscape'}
              {' '}({count.toLocaleString()})
            </button>
          )
        })}

        <select
          value={cameraFilter}
          onChange={e => setCameraFilter(e.target.value)}
          style={{
            padding: '6px 12px', fontSize: 'var(--text-sm)',
            borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
            background: 'var(--surface)', color: 'var(--text)',
            cursor: 'pointer', marginLeft: 'auto',
          }}
        >
          <option value="all">All cameras</option>
          {cameras.map(c => (
            <option key={c} value={c}>{c} ({data.cameras[c]})</option>
          ))}
        </select>
      </div>

      {/* Count */}
      <div style={{
        fontSize: 'var(--text-sm)', color: 'var(--muted)',
        marginBottom: 'var(--space-4)',
      }}>
        Showing {visible.length.toLocaleString()} of {filtered.length.toLocaleString()}
      </div>

      {/* Image grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
        gap: 'var(--space-2)',
      }}>
        {visible.map(p => (
          <div
            key={p.uuid}
            onClick={() => setLightbox(p)}
            style={{
              position: 'relative', cursor: 'pointer',
              borderRadius: 'var(--radius-sm)', overflow: 'hidden',
              background: 'var(--card-bg)',
            }}
          >
            <FadeImg
              src={imageUrl(`/rendered/thumb/webp/${p.uuid}.webp`)}
              alt={p.category}
              loading="lazy"
              decoding="async"
              style={{ aspectRatio: `${p.w} / ${p.h}` }}
            />
          </div>
        ))}
      </div>

      {/* Load more */}
      {visibleCount < filtered.length && (
        <div style={{ textAlign: 'center', marginTop: 'var(--space-8)' }}>
          <button
            onClick={() => setVisibleCount(v => v + PAGE_SIZE)}
            style={loadMoreStyle}
          >
            Load more ({Math.min(PAGE_SIZE, filtered.length - visibleCount)} more)
          </button>
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div
          onClick={() => setLightbox(null)}
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.92)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'zoom-out',
          }}
        >
          <img
            src={imageUrl(`/rendered/display/webp/${lightbox.uuid}.webp`)}
            alt={lightbox.category}
            style={{
              maxWidth: '92vw', maxHeight: '92vh',
              objectFit: 'contain', borderRadius: 'var(--radius-sm)',
            }}
          />
          <div style={{
            position: 'absolute', bottom: 24, left: '50%', transform: 'translateX(-50%)',
            display: 'flex', gap: 'var(--space-2)',
          }}>
            <span style={overlayBadge}>{lightbox.camera}</span>
            <span style={overlayBadge}>{lightbox.orientation}</span>
            <span style={overlayBadge}>{lightbox.w}&times;{lightbox.h}</span>
            {lightbox.quality != null && <span style={overlayBadge}>Q{lightbox.quality}</span>}
          </div>
        </div>
      )}
    </PageShell>
  )
}

function filterBtnStyle(active: boolean): React.CSSProperties {
  return {
    padding: '6px 14px', fontSize: 'var(--text-sm)',
    fontWeight: active ? 700 : 500,
    borderRadius: 'var(--radius-full)',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
    background: active ? 'var(--accent)' : 'transparent',
    color: active ? '#fff' : 'var(--text)',
    cursor: 'pointer', transition: 'all var(--duration-fast)',
  }
}

const loadMoreStyle: React.CSSProperties = {
  padding: '10px 28px', fontSize: 'var(--text-sm)', fontWeight: 600,
  borderRadius: 'var(--radius-full)', border: '1px solid var(--border)',
  background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer',
}

const overlayBadge: React.CSSProperties = {
  padding: '4px 12px', borderRadius: 'var(--radius-sm)',
  background: 'rgba(0,0,0,0.6)', fontSize: 'var(--text-sm)',
  color: 'rgba(255,255,255,0.8)', fontWeight: 500,
}
