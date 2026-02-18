import { useState, useEffect, useCallback, useMemo, type ImgHTMLAttributes } from 'react'
import { imageUrl } from '../config'
import { PageShell } from '../components/layout/PageShell'

function FadeImg({ className, style, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}`} style={style}>
      <img {...props} onLoad={() => setLoaded(true)} style={{ width: '100%', display: 'block' }} />
    </div>
  )
}

interface UnpickedImage {
  uuid: string
  category: string
  orientation: string
  width: number
  height: number
  vote_status: 'unreviewed' | 'rejected' | 'accepted_not_picked'
}

interface UnpickedData {
  images: UnpickedImage[]
  total: number
  picked_count: number
}

type FilterStatus = 'all' | 'unreviewed' | 'rejected'

const PAGE_SIZE = 50

export function UnpickedPage() {
  const [data, setData] = useState<UnpickedData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterStatus>('all')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [picking, setPicking] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [lightbox, setLightbox] = useState<UnpickedImage | null>(null)

  const fetchData = useCallback(() => {
    setLoading(true)
    setError(null)
    fetch('/api/unpicked')
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then((d: UnpickedData) => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  // Derived data
  const categories = useMemo(() => {
    if (!data) return []
    const set = new Set(data.images.map(i => i.category))
    return Array.from(set).sort()
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    return data.images.filter(img => {
      if (filter === 'unreviewed' && img.vote_status !== 'unreviewed') return false
      if (filter === 'rejected' && img.vote_status !== 'rejected') return false
      if (categoryFilter !== 'all' && img.category !== categoryFilter) return false
      return true
    })
  }, [data, filter, categoryFilter])

  const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount])

  // Counts for filter labels
  const counts = useMemo(() => {
    if (!data) return { all: 0, unreviewed: 0, rejected: 0 }
    const base = categoryFilter === 'all'
      ? data.images
      : data.images.filter(i => i.category === categoryFilter)
    return {
      all: base.length,
      unreviewed: base.filter(i => i.vote_status === 'unreviewed').length,
      rejected: base.filter(i => i.vote_status === 'rejected').length,
    }
  }, [data, categoryFilter])

  // Reset visible count when filters change
  useEffect(() => { setVisibleCount(PAGE_SIZE) }, [filter, categoryFilter])

  const toggleSelect = useCallback((uuid: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid); else next.add(uuid)
      return next
    })
  }, [])

  const selectAll = useCallback(() => {
    setSelected(new Set(visible.map(i => i.uuid)))
  }, [visible])

  const clearSelection = useCallback(() => setSelected(new Set()), [])

  const doPick = useCallback(async () => {
    if (selected.size === 0) return
    setPicking(true)
    try {
      const res = await fetch('/api/pick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uuids: Array.from(selected) }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      const result = await res.json()
      const count = selected.size

      setData(prev => {
        if (!prev) return prev
        return {
          ...prev,
          images: prev.images.filter(i => !selected.has(i.uuid)),
          total: prev.total - count,
          picked_count: result.new_total,
        }
      })
      setSelected(new Set())
      setToast(`Picked ${count} image${count > 1 ? 's' : ''}`)
      setTimeout(() => setToast(null), 3000)
    } catch (e: any) {
      setToast(`Error: ${e.message}`)
      setTimeout(() => setToast(null), 4000)
    } finally {
      setPicking(false)
    }
  }, [selected])

  // Keyboard: Escape closes lightbox
  useEffect(() => {
    if (!lightbox) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setLightbox(null) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [lightbox])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading unpicked images...</div>
  if (error) return <div style={{ color: 'var(--red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  const subtitle = `${data.total.toLocaleString()} unpicked \u00b7 ${data.picked_count.toLocaleString()} picked`

  return (
    <PageShell title="Unpicked" subtitle={subtitle}>
      {/* Filter bar */}
      <div style={{
        display: 'flex', gap: 'var(--space-3)', alignItems: 'center',
        flexWrap: 'wrap', marginBottom: 'var(--space-5)',
      }}>
        {(['all', 'unreviewed', 'rejected'] as FilterStatus[]).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '6px 14px',
              fontSize: 'var(--text-sm)',
              fontWeight: filter === f ? 700 : 500,
              borderRadius: 'var(--radius-full)',
              border: `1px solid ${filter === f ? 'var(--accent)' : 'var(--border)'}`,
              background: filter === f ? 'var(--accent)' : 'transparent',
              color: filter === f ? '#fff' : 'var(--text)',
              cursor: 'pointer',
              transition: 'all var(--duration-fast)',
            }}
          >
            {f === 'all' ? 'All' : f === 'unreviewed' ? 'Unreviewed' : 'Rejected'}
            {' '}({counts[f].toLocaleString()})
          </button>
        ))}

        <select
          value={categoryFilter}
          onChange={e => setCategoryFilter(e.target.value)}
          style={{
            padding: '6px 12px',
            fontSize: 'var(--text-sm)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)',
            background: 'var(--surface)',
            color: 'var(--text)',
            cursor: 'pointer',
            marginLeft: 'auto',
          }}
        >
          <option value="all">All categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {/* Selection toolbar — sticky at top */}
      {filtered.length > 0 && (
        <div style={{
          position: 'sticky', top: 0, zIndex: 50,
          background: 'var(--bg)', borderBottom: '1px solid var(--border)',
          padding: 'var(--space-3) 0',
          marginBottom: 'var(--space-4)',
          display: 'flex', gap: 'var(--space-3)', alignItems: 'center',
          fontSize: 'var(--text-sm)', color: 'var(--muted)',
        }}>
          <button onClick={selectAll} style={linkBtnStyle}>Select visible ({visible.length})</button>
          {selected.size > 0 && (
            <>
              <button onClick={clearSelection} style={linkBtnStyle}>Clear ({selected.size})</button>
              <span style={{ fontWeight: 600, color: 'var(--text)' }}>
                {selected.size} selected
              </span>
              <button
                onClick={() => doPick()}
                disabled={picking}
                style={pickBtnStyle}
              >
                {picking ? 'Picking...' : 'Pick'}
              </button>
            </>
          )}
          <span style={{ marginLeft: 'auto' }}>
            Showing {visible.length.toLocaleString()} of {filtered.length.toLocaleString()}
          </span>
        </div>
      )}

      {/* Image grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: 'var(--space-4)',
      }}>
        {visible.map(img => (
          <div
            key={img.uuid}
            style={{
              position: 'relative',
              background: 'var(--card-bg)',
              border: `2px solid ${selected.has(img.uuid) ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 'var(--radius-md)',
              overflow: 'hidden',
              cursor: 'pointer',
              transition: 'border-color var(--duration-fast)',
            }}
          >
            {/* Checkbox */}
            <div
              onClick={e => { e.stopPropagation(); toggleSelect(img.uuid) }}
              style={{
                position: 'absolute', top: 8, left: 8, zIndex: 2,
                width: 22, height: 22,
                borderRadius: 'var(--radius-sm)',
                border: `2px solid ${selected.has(img.uuid) ? 'var(--accent)' : 'rgba(255,255,255,0.5)'}`,
                background: selected.has(img.uuid) ? 'var(--accent)' : 'rgba(0,0,0,0.3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: '14px', fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              {selected.has(img.uuid) && '\u2713'}
            </div>

            {/* Image */}
            <div onClick={() => setLightbox(img)}>
              <FadeImg
                src={imageUrl(`/rendered/display/webp/${img.uuid}.webp`)}
                alt={img.uuid}
                loading="lazy"
                decoding="async"
                style={{ aspectRatio: `${img.width} / ${img.height}` }}
              />
            </div>

            {/* Badges */}
            <div style={{
              display: 'flex', gap: 4, padding: '6px 8px',
              fontSize: 'var(--text-xs)', color: 'var(--muted)',
            }}>
              <span style={badgeStyle}>{img.category}</span>
              <span style={badgeStyle}>{img.orientation}</span>
              <span style={{
                ...badgeStyle,
                color: img.vote_status === 'unreviewed' ? 'var(--orange)' : 'var(--text-3)',
              }}>
                {img.vote_status === 'unreviewed' ? 'new' : img.vote_status === 'rejected' ? 'rej' : 'acc'}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Load more */}
      {visibleCount < filtered.length && (
        <div style={{ textAlign: 'center', marginTop: 'var(--space-8)' }}>
          <button
            onClick={() => setVisibleCount(v => v + PAGE_SIZE)}
            style={{
              padding: '10px 28px',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              borderRadius: 'var(--radius-full)',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              cursor: 'pointer',
            }}
          >
            Load more ({Math.min(PAGE_SIZE, filtered.length - visibleCount)} more)
          </button>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, left: '50%',
          transform: 'translateX(-50%)', zIndex: 200,
          background: 'var(--green)', color: '#000',
          padding: '10px 24px', borderRadius: 'var(--radius-full)',
          fontWeight: 600, fontSize: 'var(--text-sm)',
          boxShadow: 'var(--shadow-lg)',
        }}>
          {toast}
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
            alt={lightbox.uuid}
            style={{
              maxWidth: '90vw', maxHeight: '90vh',
              objectFit: 'contain', borderRadius: 'var(--radius-md)',
            }}
          />
          <div style={{
            position: 'absolute', bottom: 24, left: '50%', transform: 'translateX(-50%)',
            display: 'flex', gap: 'var(--space-3)', alignItems: 'center',
          }}>
            <span style={{
              ...badgeStyle, fontSize: 'var(--text-sm)',
              padding: '4px 12px', background: 'rgba(0,0,0,0.6)',
            }}>
              {lightbox.category} \u00b7 {lightbox.orientation} \u00b7 {lightbox.width}\u00d7{lightbox.height}
            </span>
          </div>
        </div>
      )}
    </PageShell>
  )
}

const badgeStyle: React.CSSProperties = {
  padding: '2px 6px',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-2)',
  fontSize: 'var(--text-xs)',
  fontWeight: 500,
}

const linkBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--accent)',
  cursor: 'pointer', fontSize: 'var(--text-sm)', padding: 0,
  textDecoration: 'underline',
}

const pickBtnStyle: React.CSSProperties = {
  padding: '8px 20px',
  fontSize: 'var(--text-sm)',
  fontWeight: 600,
  borderRadius: 'var(--radius-full)',
  border: 'none',
  background: 'var(--accent)',
  color: '#fff',
  cursor: 'pointer',
}
