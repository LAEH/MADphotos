import { useState, useEffect, useRef, type CSSProperties } from 'react'

interface CropEntry {
  uuid: string
  w: number
  h: number
  left: number
  right: number
  top: number
  bottom: number
}

export function BorderCropPage() {
  const [crops, setCrops] = useState<CropEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [skipped, setSkipped] = useState<Set<string>>(new Set())
  const [applying, setApplying] = useState(false)
  const [result, setResult] = useState<{ total: number; errors: string[] } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Take over the layout — full viewport, no padding
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const scroll = el.closest('.main-scroll') as HTMLElement | null
    const content = el.closest('.main-content') as HTMLElement | null
    if (scroll) { scroll.style.overflow = 'auto'; scroll.style.height = '100vh' }
    if (content) { content.style.padding = '0'; content.style.maxWidth = 'none'; content.style.height = '100%' }
    return () => {
      if (scroll) { scroll.style.overflow = ''; scroll.style.height = '' }
      if (content) { content.style.padding = ''; content.style.maxWidth = ''; content.style.height = '' }
    }
  }, [])

  useEffect(() => {
    fetch('/api/border-crops')
      .then(r => r.json())
      .then(d => { setCrops(d.crops || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const toggleSkip = (uuid: string) => {
    setSkipped(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid); else next.add(uuid)
      return next
    })
  }

  const applyCrops = async () => {
    const approved = crops.filter(c => !skipped.has(c.uuid))
    if (!approved.length) return
    setApplying(true)
    setResult(null)
    try {
      const res = await fetch('/api/border-crops/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          crops: approved.map(c => ({
            uuid: c.uuid, left: c.left, right: c.right,
            top: c.top, bottom: c.bottom, w: c.w, h: c.h,
          })),
        }),
      })
      const data = await res.json()
      setResult({ total: data.total_cropped || 0, errors: data.errors || [] })
    } catch (e) {
      setResult({ total: 0, errors: [String(e)] })
    }
    setApplying(false)
  }

  if (loading) {
    return (
      <div ref={containerRef} style={{ color: '#888', padding: '80px', textAlign: 'center', background: '#0a0a0a', minHeight: '100vh' }}>
        Loading...
      </div>
    )
  }

  const approvedCount = crops.length - skipped.size
  const skippedCount = skipped.size

  return (
    <div ref={containerRef} style={wrapStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <span style={titleStyle}>Border Crops</span>
        <span style={countStyle}>{crops.length} variants detected</span>
        <span style={{ ...countStyle, color: '#30D158' }}>{approvedCount} to crop</span>
        {skippedCount > 0 && <span style={{ ...countStyle, color: '#FF453A' }}>{skippedCount} skipped</span>}
      </div>

      {/* Grid */}
      <div style={gridStyle}>
        {crops.map(c => {
          const isSkipped = skipped.has(c.uuid)
          const borderParts: string[] = []
          if (c.left > 0) borderParts.push(`L:${c.left}px`)
          if (c.right > 0) borderParts.push(`R:${c.right}px`)
          if (c.top > 0) borderParts.push(`T:${c.top}px`)
          if (c.bottom > 0) borderParts.push(`B:${c.bottom}px`)
          const borderLabel = borderParts.join(' ')

          // Calculate overlay percentages for the red border highlight
          const leftPct = (c.left / c.w) * 100
          const rightPct = (c.right / c.w) * 100
          const topPct = (c.top / c.h) * 100
          const bottomPct = (c.bottom / c.h) * 100

          return (
            <div key={c.uuid} style={{
              ...cardStyle,
              opacity: isSkipped ? 0.35 : 1,
              border: isSkipped ? '2px solid #333' : '2px solid #30D158',
            }}>
              {/* Image container with overlay */}
              <div style={imgContainerStyle}>
                <img
                  src={`/rendered/variants/display/jpeg/${c.uuid}.jpg`}
                  alt={c.uuid}
                  style={imgStyle}
                  loading="lazy"
                />
                {/* Red overlay strips for each border edge */}
                {!isSkipped && (
                  <>
                    {c.left > 0 && (
                      <div style={{
                        ...overlayStrip,
                        left: 0, top: 0, bottom: 0,
                        width: `${leftPct}%`,
                      }} />
                    )}
                    {c.right > 0 && (
                      <div style={{
                        ...overlayStrip,
                        right: 0, top: 0, bottom: 0,
                        width: `${rightPct}%`,
                      }} />
                    )}
                    {c.top > 0 && (
                      <div style={{
                        ...overlayStrip,
                        top: 0, left: 0, right: 0,
                        height: `${topPct}%`,
                      }} />
                    )}
                    {c.bottom > 0 && (
                      <div style={{
                        ...overlayStrip,
                        bottom: 0, left: 0, right: 0,
                        height: `${bottomPct}%`,
                      }} />
                    )}
                  </>
                )}
              </div>

              {/* Info bar */}
              <div style={infoBarStyle}>
                <span style={dimLabel}>{c.w}x{c.h}</span>
                <span style={cropLabel}>{borderLabel}</span>
                <button
                  style={{
                    ...toggleBtn,
                    background: isSkipped ? '#FF453A' : '#30D158',
                    color: '#fff',
                  }}
                  onClick={() => toggleSkip(c.uuid)}
                >
                  {isSkipped ? 'Skip' : 'Crop'}
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div style={footerStyle}>
        {result && (
          <span style={{
            fontSize: '12px',
            color: result.errors.length ? '#FF9F0A' : '#30D158',
            marginRight: '12px',
          }}>
            {result.errors.length
              ? `Done with ${result.errors.length} error(s) -- ${result.total} files cropped`
              : `Done -- ${result.total} files cropped`}
          </span>
        )}
        <span style={stat}>{approvedCount} of {crops.length} will be cropped</span>
        <button
          style={{
            ...applyBtn,
            opacity: applying || approvedCount === 0 ? 0.3 : 1,
            cursor: applying || approvedCount === 0 ? 'default' : 'pointer',
          }}
          onClick={applyCrops}
          disabled={applying || approvedCount === 0}
        >
          {applying ? 'Applying...' : `Apply Crops (${approvedCount})`}
        </button>
      </div>
    </div>
  )
}

// ── Styles ──

const wrapStyle: CSSProperties = {
  width: '100%', minHeight: '100vh',
  display: 'flex', flexDirection: 'column',
  background: '#0a0a0a',
}

const headerStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: '16px',
  padding: '12px 16px', borderBottom: '1px solid #1a1a1a',
  flexShrink: 0,
}

const titleStyle: CSSProperties = {
  fontSize: '14px', fontWeight: 600, color: '#e0e0e0',
  letterSpacing: '0.02em',
}

const countStyle: CSSProperties = {
  fontSize: '12px', color: '#666',
  fontVariantNumeric: 'tabular-nums',
}

const gridStyle: CSSProperties = {
  flex: 1, display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: '8px', padding: '12px',
}

const cardStyle: CSSProperties = {
  borderRadius: '8px', overflow: 'hidden',
  background: '#141414',
  transition: 'opacity 0.15s, border-color 0.15s',
}

const imgContainerStyle: CSSProperties = {
  position: 'relative', width: '100%',
  overflow: 'hidden', background: '#000',
}

const imgStyle: CSSProperties = {
  width: '100%', display: 'block',
}

const overlayStrip: CSSProperties = {
  position: 'absolute',
  background: 'rgba(255, 69, 58, 0.40)',
  pointerEvents: 'none',
}

const infoBarStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '6px 10px', gap: '8px',
}

const dimLabel: CSSProperties = {
  fontSize: '10px', color: '#555',
  fontFamily: 'SF Mono, monospace',
  fontVariantNumeric: 'tabular-nums',
}

const cropLabel: CSSProperties = {
  fontSize: '11px', color: '#aaa',
  fontFamily: 'SF Mono, monospace',
  fontVariantNumeric: 'tabular-nums',
  flex: 1,
}

const toggleBtn: CSSProperties = {
  padding: '3px 10px', border: 'none', borderRadius: '4px',
  fontSize: '11px', fontWeight: 600, cursor: 'pointer',
  transition: 'background 0.15s',
}

const footerStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
  padding: '8px 16px', borderTop: '1px solid #1a1a1a',
  flexShrink: 0, gap: '12px',
  position: 'sticky', bottom: 0,
  background: '#0a0a0a',
}

const stat: CSSProperties = {
  fontSize: '12px', color: '#555',
  fontVariantNumeric: 'tabular-nums',
}

const applyBtn: CSSProperties = {
  padding: '8px 20px', background: '#30D158', color: '#000',
  border: 'none', borderRadius: '8px',
  fontSize: '13px', fontWeight: 600,
}
