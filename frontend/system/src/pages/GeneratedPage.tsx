import { useState, useEffect, useMemo, useCallback, useRef, type CSSProperties } from 'react'

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

interface StylePair {
  variant_id: string
  uuid: string
  original_path: string
  variant_path: string
  style_name: string
  style_prompt: string
  strength: number
  why: string
  rotation: number
  review: string | null
  variant_type?: string
}

interface StyleData {
  pairs: StylePair[]
  run_dir: string | null
  accepted: number
  rejected: number
}

export function GeneratedPage() {
  const [data, setData] = useState<StyleData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const filter = 'unreviewed'
  const [reviews, setReviews] = useState<Record<string, string>>({})
  const [currentIdx, setCurrentIdx] = useState(0)
  const [aspectRatio, setAspectRatio] = useState<number>(1.5)
  const [generating, setGenerating] = useState(false)
  const [batchProgress, setBatchProgress] = useState<{ completed: number; expected: number } | null>(null)
  const [exporting, setExporting] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [generateCount, setGenerateCount] = useState(20)
  const [exportedIds, setExportedIds] = useState<Set<string>>(new Set())
  const cursorReject = useRef('')
  const cursorAccept = useRef('')
  const progressTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  if (!cursorReject.current) cursorReject.current = emojiCursor('😒')
  if (!cursorAccept.current) cursorAccept.current = emojiCursor('😍')

  const fetchData = useCallback(() => {
    fetch('/api/generated')
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then((d: StyleData) => {
        setData(prev => {
          if (!prev) return d
          const existing = new Set(prev.pairs.map(p => p.variant_id))
          const newPairs = d.pairs.filter(p => !existing.has(p.variant_id))
          if (newPairs.length === 0) return { ...prev, accepted: d.accepted, rejected: d.rejected }
          return { ...d, pairs: [...prev.pairs, ...newPairs] }
        })
        setLoading(false)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  // On mount: detect if generate/export is already running (survives refresh)
  useEffect(() => {
    fetch('/api/generated/progress')
      .then(r => r.json())
      .then((p: { completed: number; expected: number; done: boolean }) => {
        if (!p.done) {
          setGenerating(true)
          setBatchProgress({ completed: p.completed, expected: p.expected })
          stopProgressPoll()
          progressTimer.current = setInterval(pollProgress, 3000)
        }
      })
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Auto-poll only when NOT generating a batch
  useEffect(() => {
    fetchData()
    if (!generating) {
      const id = setInterval(fetchData, 30_000)
      return () => clearInterval(id)
    }
  }, [fetchData, generating])

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2000)
  }, [])

  // Stop progress polling
  const stopProgressPoll = useCallback(() => {
    if (progressTimer.current) {
      clearInterval(progressTimer.current)
      progressTimer.current = null
    }
  }, [])

  // Batch generation complete — fetch new data and exit batch mode
  const finishBatch = useCallback(() => {
    stopProgressPoll()
    fetchData()
    setBatchProgress(null)
    setGenerating(false)
    setCurrentIdx(0)
  }, [stopProgressPoll, fetchData])

  // Poll progress endpoint
  const pollProgress = useCallback(() => {
    fetch('/api/generated/progress')
      .then(r => r.json())
      .then((p: { completed: number; expected: number; done: boolean }) => {
        setBatchProgress({ completed: p.completed, expected: p.expected })
        if (p.done && p.completed > 0) finishBatch()
      })
      .catch(() => {})
  }, [finishBatch])

  // Cleanup progress timer on unmount
  useEffect(() => stopProgressPoll, [stopProgressPoll])

  const handleGenerate = useCallback(async () => {
    setGenerating(true)
    setBatchProgress({ completed: 0, expected: generateCount })
    try {
      const r = await fetch('/api/generated/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: generateCount }),
      })
      if (!r.ok) {
        showToast('Failed to launch')
        setGenerating(false)
        setBatchProgress(null)
        return
      }
    } catch {
      showToast('Failed to launch')
      setGenerating(false)
      setBatchProgress(null)
      return
    }
    // Start polling progress every 3s
    stopProgressPoll()
    progressTimer.current = setInterval(pollProgress, 3000)
  }, [showToast, stopProgressPoll, pollProgress, generateCount])

  const handleExport = useCallback(async () => {
    setExporting(true)
    try {
      const r = await fetch('/api/generated/export', { method: 'POST' })
      if (r.ok) {
        const d = await r.json()
        showToast(`Exporting ${d.count} variants in Terminal...`)
        setExportedIds(new Set(Object.keys(reviews)))
      } else {
        showToast('No accepted variants')
        setExporting(false)
      }
    } catch {
      showToast('Failed to launch')
      setExporting(false)
    }
  }, [showToast, reviews])

  const getReview = useCallback((pair: StylePair) => {
    return reviews[pair.variant_id] ?? pair.review
  }, [reviews])

  const handleReview = useCallback(async (variantId: string, status: string) => {
    setReviews(r => ({ ...r, [variantId]: status }))
    try {
      await fetch('/api/generated/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant_id: variantId, status }),
      })
    } catch {
      setReviews(r => {
        const next = { ...r }
        delete next[variantId]
        return next
      })
    }
  }, [])

  const filtered = useMemo(() => {
    if (!data) return []
    return data.pairs.filter(p => !getReview(p))
  }, [data, getReview])

  const safeIdx = Math.min(currentIdx, Math.max(0, filtered.length - 1))
  const current = filtered[safeIdx] ?? null

  const reviewAndAdvance = useCallback((status: string) => {
    if (!current) return
    handleReview(current.variant_id, status)
  }, [current, handleReview])

  // Keyboard: A = accept, R = reject (disabled while generating)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (generating) return
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      switch (e.key) {
        case 'a': case 'A':
          e.preventDefault(); reviewAndAdvance('accepted'); break
        case 'r': case 'R':
          e.preventDefault(); reviewAndAdvance('rejected'); break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [reviewAndAdvance, generating])

  if (loading) return <div style={{ color: 'var(--muted)', padding: '80px', textAlign: 'center' }}>Loading...</div>
  if (error) return <div style={{ color: 'var(--red)', padding: '80px', textAlign: 'center' }}>Error: {error}</div>
  if (!data) return null

  const review = current ? getReview(current) : null
  // Count accepts done this session that haven't been exported yet
  const newAccepts = Object.entries(reviews).filter(
    ([id, v]) => v === 'accepted' && !exportedIds.has(id)
  ).length
  const exportReady = newAccepts > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Top bar — single row of chips */}
      <div className="filter-bar" style={{
        flexShrink: 0, padding: '10px 16px', margin: 0,
        borderBottom: '1px solid var(--border)',
        alignItems: 'center',
      }}>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
          {filtered.length} to review {data.accepted > 0 && `· ${data.accepted} accepted · ${data.rejected} rejected`}
        </span>

        <div style={{ flex: 1 }} />

        {toast && (
          <span style={{ color: '#30D158', fontSize: 'var(--text-xs)' }}>{toast}</span>
        )}

        {current && !generating && (
          <>
            <button className="filter-btn" onClick={() => reviewAndAdvance('rejected')}
              style={{ borderColor: review === 'rejected' ? '#FF453A' : undefined,
                       color: review === 'rejected' ? '#FF453A' : undefined }}>
              R
            </button>
            <button className="filter-btn" onClick={() => reviewAndAdvance('accepted')}
              style={{ borderColor: review === 'accepted' ? '#30D158' : undefined,
                       color: review === 'accepted' ? '#30D158' : undefined }}>
              A
            </button>
          </>
        )}

        {!generating && (
          <span style={{ display: 'inline-flex', gap: '2px' }}>
            {[10, 20, 40, 80].map(n => (
              <button key={n} className="filter-btn"
                onClick={() => setGenerateCount(n)}
                style={{
                  minWidth: '28px', padding: '4px 6px',
                  borderColor: generateCount === n ? '#0A84FF' : undefined,
                  color: generateCount === n ? '#0A84FF' : undefined,
                  fontSize: 'var(--text-xs)',
                }}>
                {n}
              </button>
            ))}
          </span>
        )}
        <button className="filter-btn" onClick={handleGenerate} disabled={generating || exporting}
          style={{
            borderColor: generating ? '#FF9F0A' : undefined,
            color: generating ? '#FF9F0A' : undefined,
            opacity: generating || exporting ? 0.8 : 1,
          }}>
          {generating && batchProgress
            ? `⏳ ${batchProgress.completed}/${batchProgress.expected}`
            : `Generate ${generateCount}`}
        </button>

        <button className="filter-btn" onClick={handleExport}
          disabled={exporting || (!exportReady && !exporting) || generating}
          style={{
            borderColor: exporting ? '#FF9F0A' : exportReady && !generating ? '#30D158' : undefined,
            color: exporting ? '#FF9F0A' : exportReady && !generating ? '#30D158' : undefined,
            opacity: exportReady || exporting ? 1 : 0.3,
          }}>
          {exporting ? '⏳ Exporting...' : `Export ${newAccepts}`}
        </button>
      </div>

      {/* Images */}
      <div style={{
        flex: 1, minHeight: 0,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        gap: '4px', padding: '8px',
        transition: 'opacity 0.12s',
        background: '#0a0a0a',
      }}>
        {(generating && batchProgress) || exporting ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: '20px', paddingTop: '20vh',
          }}>
            <div style={{
              width: '32px', height: '32px',
              border: '2.5px solid #333',
              borderTopColor: exporting ? '#FF9F0A' : '#30D158',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }} />
            <span style={{ color: '#888', fontSize: '13px', fontVariantNumeric: 'tabular-nums' }}>
              {exporting
                ? 'Exporting variants in Terminal...'
                : batchProgress && batchProgress.completed > 0
                  ? `Generating ${batchProgress.completed}/${batchProgress.expected}`
                  : 'Starting generation...'}
            </span>
            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
          </div>
        ) : current ? (
          <>
            <div
              onClick={() => reviewAndAdvance('rejected')}
              style={{
                ...imgBox,
                aspectRatio: `${aspectRatio}`,
                outline: review === 'rejected' ? '3px solid #FF453A' : 'none',
                cursor: cursorReject.current,
              }}
            >
              <img
                key={`orig-${current.variant_id}`}
                src={current.original_path}
                alt="Original"
                onLoad={e => {
                  const el = e.currentTarget
                  if (el.naturalWidth && el.naturalHeight) {
                    setAspectRatio(el.naturalWidth / el.naturalHeight)
                  }
                }}
                style={imgFill}
              />
            </div>
            <div
              onClick={() => reviewAndAdvance('accepted')}
              style={{
                ...imgBox,
                aspectRatio: `${aspectRatio}`,
                outline: review === 'accepted' ? '3px solid #30D158' : 'none',
                cursor: cursorAccept.current,
              }}
            >
              <img
                key={`var-${current.variant_id}`}
                src={current.variant_path}
                alt="Variant"
                style={imgFill}
              />
            </div>
          </>
        ) : (
          <span style={{ color: '#666', fontSize: '14px', paddingTop: '120px' }}>
            {filter === 'unreviewed' ? 'All reviewed.' : 'No images.'}
          </span>
        )}
      </div>
    </div>
  )
}

const imgBox: CSSProperties = {
  maxWidth: 'calc(50% - 4px)',
  maxHeight: 'calc(100vh - 70px)',
  borderRadius: '6px',
  overflow: 'hidden',
  cursor: 'pointer',
  outlineOffset: '2px',
  transition: 'outline 0.15s',
}

const imgFill: CSSProperties = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  objectPosition: 'top',
  display: 'block',
}
