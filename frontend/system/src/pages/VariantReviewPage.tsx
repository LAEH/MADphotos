import { useState, useEffect, useCallback, useRef, type CSSProperties } from 'react'

function emojiCursor(emoji: string, size = 32): string {
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  ctx.font = `${size - 4}px serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(emoji, size / 2, size / 2)
  return `url(${canvas.toDataURL()}) ${size / 2} ${size / 2}, pointer`
}

interface Variant {
  variant_id: string
  uuid: string
  style_key: string
  variant_type: string
  original_path: string
  variant_path: string
}

const PAGE_SIZE = 10

export function VariantReviewPage() {
  const [variants, setVariants] = useState<Variant[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [totalPicked, setTotalPicked] = useState(0)
  const [saving, setSaving] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const cursorAccept = useRef('')
  if (!cursorAccept.current) cursorAccept.current = emojiCursor('😍')

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const scroll = el.closest('.main-scroll') as HTMLElement | null
    const content = el.closest('.main-content') as HTMLElement | null
    if (scroll) { scroll.style.overflow = 'hidden'; scroll.style.height = '100vh' }
    if (content) { content.style.padding = '0'; content.style.maxWidth = 'none'; content.style.height = '100%' }
    return () => {
      if (scroll) { scroll.style.overflow = ''; scroll.style.height = '' }
      if (content) { content.style.padding = ''; content.style.maxWidth = ''; content.style.height = '' }
    }
  }, [])

  useEffect(() => {
    fetch('/api/variant-review')
      .then(r => r.json())
      .then(d => { setVariants(d.variants || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const toggle = useCallback((id: string) => {
    setPicked(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  const totalPages = Math.ceil(variants.length / PAGE_SIZE)
  const pageVariants = variants.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const done = page >= totalPages - 1

  const goNext = useCallback(async () => {
    if (done || saving) return
    // Reject unpicked from this page
    const rejectIds = pageVariants
      .filter(v => !picked.has(v.variant_id))
      .map(v => v.variant_id)

    setSaving(true)
    console.log(`[VariantReview] Page ${page}: rejecting ${rejectIds.length}, keeping ${picked.size}`)
    try {
      const res = await fetch('/api/variant-review/reject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant_ids: rejectIds }),
      })
      const data = await res.json()
      console.log(`[VariantReview] Rejected: ${data.count}`)
    } catch (e) { console.error('[VariantReview] reject failed', e) }
    setSaving(false)

    // Remove all reviewed variants (both picked and rejected) from local list
    const reviewedIds = new Set(pageVariants.map(v => v.variant_id))
    setVariants(prev => prev.filter(v => !reviewedIds.has(v.variant_id)))
    setTotalPicked(prev => prev + picked.size)
    setPicked(new Set())
    setPage(0) // Always show from start of remaining list
  }, [picked, pageVariants, done, saving])

  if (loading) return <div ref={containerRef} style={{ color: '#888', padding: '80px', textAlign: 'center' }}>Loading...</div>

  const col1 = pageVariants.slice(0, 5)
  const col2 = pageVariants.slice(5, 10)
  const remaining = variants.length - (page + 1) * PAGE_SIZE

  return (
    <div ref={containerRef} style={wrapStyle}>
      <div style={gridStyle}>
        {[col1, col2].map((col, ci) => (
          <div key={ci} style={colStyle}>
            {col.map(v => {
              const on = picked.has(v.variant_id)
              return (
                <div key={v.variant_id}
                  style={{ ...rowStyle, background: on ? 'rgba(48,209,88,0.06)' : 'transparent' }}
                  onClick={() => toggle(v.variant_id)}>
                  <div style={d}><img src={v.original_path} alt="" style={dImg} /></div>
                  <div style={d}>
                    <div style={hWrap}>
                      <img src={v.original_path} alt="" style={hL} />
                      <img src={v.variant_path} alt="" style={hR} />
                    </div>
                  </div>
                  <div style={{ ...d, boxShadow: on ? '0 0 0 3px #30D158' : 'none' }}>
                    <img src={v.variant_path} alt="" style={dImg} />
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>

      <div style={footerStyle}>
        <span style={stat}>{totalPicked + picked.size} picked</span>
        <span style={stat}>{page + 1} / {totalPages}{remaining > 0 ? ` · ${remaining} left` : ''}</span>
        <button
          style={{ ...nextBtn, opacity: done || saving ? 0.3 : 1, cursor: done ? 'default' : 'pointer' }}
          onClick={goNext} disabled={done || saving}>
          {saving ? 'Saving...' : done ? 'Done' : `Next →`}
        </button>
      </div>
    </div>
  )
}

const wrapStyle: CSSProperties = {
  width: '100%', height: '100vh',
  display: 'flex', flexDirection: 'column',
  overflow: 'hidden', background: '#0a0a0a',
}

const gridStyle: CSSProperties = {
  flex: 1, display: 'flex', gap: '2px',
  minHeight: 0, overflow: 'hidden',
}

const colStyle: CSSProperties = {
  flex: 1, display: 'flex', flexDirection: 'column', gap: '2px',
}

const rowStyle: CSSProperties = {
  flex: 1, minHeight: 0,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  gap: '2px', borderRadius: '6px',
  transition: 'background 0.15s',
  cursor: 'pointer',
}

const d: CSSProperties = {
  height: '85%', aspectRatio: '1', borderRadius: '50%',
  overflow: 'hidden', background: '#181818', flexShrink: 0,
  transition: 'box-shadow 0.15s',
}

const dImg: CSSProperties = {
  width: '100%', height: '100%', objectFit: 'cover', display: 'block',
}

const hWrap: CSSProperties = {
  width: '100%', height: '100%', display: 'flex', overflow: 'hidden',
}

const hL: CSSProperties = {
  width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center',
  marginLeft: 0, clipPath: 'inset(0 50% 0 0)',
}

const hR: CSSProperties = {
  width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center',
  marginLeft: '-100%', clipPath: 'inset(0 0 0 50%)',
}

const footerStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '6px 12px', borderTop: '1px solid #1a1a1a', flexShrink: 0,
}

const stat: CSSProperties = {
  fontSize: '12px', color: '#555', fontVariantNumeric: 'tabular-nums',
}

const nextBtn: CSSProperties = {
  padding: '6px 18px', background: '#222', color: '#fff',
  border: 'none', borderRadius: '8px', fontSize: '13px', fontWeight: 600,
}
