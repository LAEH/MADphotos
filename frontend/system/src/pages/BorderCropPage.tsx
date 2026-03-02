import { useState, useEffect, useCallback, useRef } from 'react'

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
  const [idx, setIdx] = useState(0)
  const [choices, setChoices] = useState<Map<string, 'original' | 'cropped'>>(new Map())
  const [applying, setApplying] = useState(false)
  const [done, setDone] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Take over layout
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
    fetch('/api/border-crops')
      .then(r => r.json())
      .then(d => { setCrops(d.crops || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const current = crops[idx] as CropEntry | undefined

  const advance = useCallback(() => {
    if (idx < crops.length - 1) setIdx(i => i + 1)
    else setDone(true)
  }, [idx, crops.length])

  const pickOriginal = useCallback(() => {
    if (!current) return
    setChoices(prev => new Map(prev).set(current.uuid, 'original'))
    advance()
  }, [current, advance])

  const pickCropped = useCallback(() => {
    if (!current) return
    setChoices(prev => new Map(prev).set(current.uuid, 'cropped'))
    advance()
  }, [current, advance])

  // Keyboard: left = original, right = cropped, up = go back
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' || e.key === 'o' || e.key === 'O') pickOriginal()
      else if (e.key === 'ArrowRight' || e.key === 'c' || e.key === 'C') pickCropped()
      else if (e.key === 'ArrowUp' && idx > 0) { setIdx(i => i - 1); setDone(false) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [pickOriginal, pickCropped, idx])

  const applyCrops = async () => {
    const toCrop = crops.filter(c => choices.get(c.uuid) === 'cropped')
    if (!toCrop.length) return
    setApplying(true)
    try {
      const res = await fetch('/api/border-crops/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          crops: toCrop.map(c => ({
            uuid: c.uuid, left: c.left, right: c.right,
            top: c.top, bottom: c.bottom, w: c.w, h: c.h,
          })),
        }),
      })
      const data = await res.json()
      alert(`Cropped ${data.total_cropped || 0} files` +
        (data.errors?.length ? ` (${data.errors.length} errors)` : ''))
    } catch (e) {
      alert(`Error: ${e}`)
    }
    setApplying(false)
  }

  if (loading) {
    return <div ref={containerRef} style={wrap}><span style={{ color: '#888', fontSize: 13 }}>Loading...</span></div>
  }
  if (crops.length === 0) {
    return <div ref={containerRef} style={wrap}><span style={{ color: '#888', fontSize: 13 }}>No borders detected.</span></div>
  }

  const clipInset = current
    ? `inset(${(current.top / current.h) * 100}% ${(current.right / current.w) * 100}% ${(current.bottom / current.h) * 100}% ${(current.left / current.w) * 100}%)`
    : undefined

  const croppedCount = [...choices.values()].filter(v => v === 'cropped').length

  return (
    <div ref={containerRef} style={wrap}>
      {/* Counter */}
      <div style={counter}>
        <span style={counterNum}>{idx + 1}</span>
        <span style={counterSlash}>/</span>
        <span style={counterTotal}>{crops.length}</span>
        {croppedCount > 0 && <span style={{ ...counterTag, color: '#30D158' }}>{croppedCount} crop</span>}
      </div>

      {/* Side by side */}
      {current && !done && (
        <div style={pair}>
          <button style={card} onClick={pickOriginal} title="Keep original (O / Left)">
            <img
              key={current.uuid + '_orig'}
              src={`/rendered/variants/display/jpeg/${current.uuid}.jpg`}
              alt="Original"
              style={cardImg}
            />
            <span style={label}>Original</span>
          </button>

          <button style={card} onClick={pickCropped} title="Use cropped (C / Right)">
            <img
              key={current.uuid + '_crop'}
              src={`/rendered/variants/display/jpeg/${current.uuid}.jpg`}
              alt="Cropped"
              style={{ ...cardImg, clipPath: clipInset }}
            />
            <span style={label}>Cropped</span>
          </button>
        </div>
      )}

      {/* Done */}
      {done && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
          <span style={{ color: '#e0e0e0', fontSize: 14 }}>
            {croppedCount} to crop, {choices.size - croppedCount} kept original
          </span>
          {croppedCount > 0 && (
            <button style={applyBtn} onClick={applyCrops} disabled={applying}>
              {applying ? 'Applying...' : `Apply ${croppedCount} Crops`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

const wrap: React.CSSProperties = {
  width: '100%', height: '100vh',
  display: 'flex', flexDirection: 'column',
  alignItems: 'center', justifyContent: 'center',
  background: '#888',
  gap: 20,
  userSelect: 'none',
}

const counter: React.CSSProperties = {
  display: 'flex', alignItems: 'baseline', gap: 4,
  position: 'absolute', top: 16, right: 24,
}
const counterNum: React.CSSProperties = {
  fontSize: 14, fontWeight: 600, color: '#fff',
  fontFamily: 'SF Mono, monospace', fontVariantNumeric: 'tabular-nums',
}
const counterSlash: React.CSSProperties = { fontSize: 12, color: '#666', fontFamily: 'SF Mono, monospace' }
const counterTotal: React.CSSProperties = {
  fontSize: 12, color: '#555', fontFamily: 'SF Mono, monospace', fontVariantNumeric: 'tabular-nums',
}
const counterTag: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, fontFamily: 'SF Mono, monospace',
  fontVariantNumeric: 'tabular-nums', marginLeft: 12,
}

const pair: React.CSSProperties = {
  display: 'flex', gap: 32,
  alignItems: 'center', justifyContent: 'center',
  maxWidth: '90vw',
}

const card: React.CSSProperties = {
  background: 'none', border: 'none', padding: 0,
  cursor: 'pointer',
  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
  transition: 'transform 0.15s ease-out',
  outline: 'none',
}

const cardImg: React.CSSProperties = {
  maxWidth: '42vw', maxHeight: '65vh',
  objectFit: 'contain',
  borderRadius: 4,
  display: 'block',
}

const label: React.CSSProperties = {
  fontSize: 11, color: '#333', fontWeight: 500,
  letterSpacing: '0.03em',
}

const applyBtn: React.CSSProperties = {
  padding: '10px 28px', background: '#30D158', color: '#000',
  border: 'none', borderRadius: 8,
  fontSize: 13, fontWeight: 600, cursor: 'pointer',
}
