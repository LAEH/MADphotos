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

interface Variant {
  variant_id: string
  parent: string
  style: string
  category: string
  exported_at: string
}

interface VariantsData {
  variants: Variant[]
  total: number
  styles: Record<string, number>
}

const PAGE_SIZE = 80

export function VariantsPage() {
  const [data, setData] = useState<VariantsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [styleFilter, setStyleFilter] = useState('all')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [lightbox, setLightbox] = useState<Variant | null>(null)

  const fetchData = useCallback(() => {
    setLoading(true)
    fetch('/api/show/variants')
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then((d: VariantsData) => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const styles = useMemo(() => {
    if (!data) return []
    return Object.entries(data.styles)
      .sort((a, b) => b[1] - a[1])
      .map(([name]) => name)
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    if (styleFilter === 'all') return data.variants
    return data.variants.filter(v => v.style === styleFilter)
  }, [data, styleFilter])

  const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount])

  useEffect(() => { setVisibleCount(PAGE_SIZE) }, [styleFilter])

  // Keyboard: Escape closes lightbox
  useEffect(() => {
    if (!lightbox) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setLightbox(null) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [lightbox])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading variants...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  const subtitle = `${data.total.toLocaleString()} variants \u00b7 ${styles.length} styles`

  return (
    <PageShell title="Variants" subtitle={subtitle}>
      {/* Style filter chips */}
      <div style={{
        display: 'flex', gap: 'var(--space-2)', alignItems: 'center',
        flexWrap: 'wrap', marginBottom: 'var(--space-5)',
      }}>
        <button onClick={() => setStyleFilter('all')} style={filterBtnStyle(styleFilter === 'all')}>
          All ({data.total.toLocaleString()})
        </button>
        {styles.map(s => (
          <button key={s} onClick={() => setStyleFilter(s)} style={filterBtnStyle(styleFilter === s)}>
            {s} ({data.styles[s]})
          </button>
        ))}
      </div>

      {/* Count */}
      <div style={{
        fontSize: 'var(--text-sm)', color: 'var(--muted)',
        marginBottom: 'var(--space-4)',
      }}>
        Showing {visible.length.toLocaleString()} of {filtered.length.toLocaleString()}
      </div>

      {/* Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: 'var(--space-2)',
      }}>
        {visible.map(v => (
          <div
            key={v.variant_id}
            onClick={() => setLightbox(v)}
            style={{
              position: 'relative', cursor: 'pointer',
              borderRadius: 'var(--radius-sm)', overflow: 'hidden',
              background: 'var(--card-bg)',
            }}
          >
            <FadeImg
              src={imageUrl(`/rendered/variants/thumb/webp/${v.variant_id}.webp`)}
              alt={v.style}
              loading="lazy"
              decoding="async"
              style={{ aspectRatio: '16 / 9' }}
            />
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 0,
              padding: '4px 8px',
              background: 'linear-gradient(transparent, rgba(0,0,0,0.7))',
              fontSize: 'var(--text-xs)', color: 'rgba(255,255,255,0.8)',
              fontWeight: 500,
            }}>
              {v.style}
            </div>
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

      {/* Lightbox — side by side: original + variant */}
      {lightbox && (
        <div
          onClick={() => setLightbox(null)}
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.92)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: 'var(--space-4)', cursor: 'zoom-out',
            padding: 'var(--space-6)',
          }}
        >
          <div style={{ flex: 1, maxWidth: '45vw', textAlign: 'center' }}>
            <img
              src={imageUrl(`/rendered/display/webp/${lightbox.parent}.webp`)}
              alt="Original"
              style={{
                maxWidth: '100%', maxHeight: '80vh',
                objectFit: 'contain', borderRadius: 'var(--radius-sm)',
              }}
            />
            <div style={labelStyle}>Original</div>
          </div>
          <div style={{ flex: 1, maxWidth: '45vw', textAlign: 'center' }}>
            <img
              src={imageUrl(`/rendered/variants/display/webp/${lightbox.variant_id}.webp`)}
              alt={lightbox.style}
              style={{
                maxWidth: '100%', maxHeight: '80vh',
                objectFit: 'contain', borderRadius: 'var(--radius-sm)',
              }}
            />
            <div style={labelStyle}>{lightbox.style}</div>
          </div>
        </div>
      )}
    </PageShell>
  )
}

function filterBtnStyle(active: boolean): React.CSSProperties {
  return {
    padding: '5px 12px', fontSize: 'var(--text-xs)',
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

const labelStyle: React.CSSProperties = {
  marginTop: 'var(--space-2)', fontSize: 'var(--text-sm)',
  color: 'rgba(255,255,255,0.6)', fontWeight: 500,
}
