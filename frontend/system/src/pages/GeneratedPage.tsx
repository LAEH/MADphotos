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
  const [filter, setFilter] = useState('unreviewed')
  const [reviews, setReviews] = useState<Record<string, string>>({})
  const [currentIdx, setCurrentIdx] = useState(0)
  const [transitioning, setTransitioning] = useState(false)
  const [aspectRatio, setAspectRatio] = useState<number>(1.5)
  const [generating, setGenerating] = useState(false)
  const [batchProgress, setBatchProgress] = useState<{ completed: number; expected: number } | null>(null)
  const [exporting, setExporting] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
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
    setFilter('unreviewed')
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
    setBatchProgress({ completed: 0, expected: 20 })
    try {
      const r = await fetch('/api/generated/generate', { method: 'POST' })
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
  }, [showToast, stopProgressPoll, pollProgress])

  const handleExport = useCallback(async () => {
    setExporting(true)
    try {
      const r = await fetch('/api/generated/export', { method: 'POST' })
      if (r.ok) {
        showToast('Export launched in Terminal')
        setExportedIds(new Set(Object.keys(reviews)))
      } else showToast('No accepted variants')
    } catch { showToast('Failed to launch') }
    setTimeout(() => setExporting(false), 5000)
  }, [showToast])

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

  const categories = useMemo(() => {
    if (!data) return []
    return [
      { key: 'unreviewed', label: 'Unreviewed', count: data.pairs.filter(p => !getReview(p)).length },
      { key: 'accepted', label: 'Accepted', count: data.pairs.filter(p => getReview(p) === 'accepted').length },
      { key: 'rejected', label: 'Rejected', count: data.pairs.filter(p => getReview(p) === 'rejected').length },
      { key: 'all', label: 'All', count: data.pairs.length },
    ]
  }, [data, getReview])

  const filtered = useMemo(() => {
    if (!data) return []
    if (filter === 'all') return data.pairs
    if (filter === 'unreviewed') return data.pairs.filter(p => !getReview(p))
    if (filter === 'accepted') return data.pairs.filter(p => getReview(p) === 'accepted')
    if (filter === 'rejected') return data.pairs.filter(p => getReview(p) === 'rejected')
    return data.pairs
  }, [data, filter, getReview])

  useEffect(() => { setCurrentIdx(0) }, [filter])

  const safeIdx = Math.min(currentIdx, Math.max(0, filtered.length - 1))
  const current = filtered[safeIdx] ?? null

  const advance = useCallback((dir: 1 | -1) => {
    setTransitioning(true)
    setTimeout(() => {
      setCurrentIdx(prev => Math.max(0, Math.min(prev + dir, filtered.length - 1)))
      setTransitioning(false)
    }, 120)
  }, [filtered.length])

  const reviewAndAdvance = useCallback((status: string) => {
    if (!current) return
    handleReview(current.variant_id, status)
    if (filter !== 'unreviewed') advance(1)
  }, [current, handleReview, filter, advance])

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
        {categories.map(c => (
          <button key={c.key} className={`filter-btn${filter === c.key ? ' active' : ''}`}
            onClick={() => setFilter(c.key)}
            disabled={generating} style={{ opacity: generating ? 0.35 : undefined }}>
            {c.label} ({c.count})
          </button>
        ))}

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

        <button className="filter-btn" onClick={handleGenerate} disabled={generating}
          style={{ opacity: generating ? 0.35 : 1 }}>
          {generating && batchProgress
            ? `${batchProgress.completed}/${batchProgress.expected}`
            : 'Generate 20'}
        </button>

        <button className="filter-btn" onClick={handleExport}
          disabled={exporting || !exportReady || generating}
          style={{
            borderColor: exportReady && !generating ? '#30D158' : undefined,
            color: exportReady && !generating ? '#30D158' : undefined,
            opacity: exportReady && !generating ? 1 : 0.3,
          }}>
          {exporting ? 'Launching...' : `Export ${newAccepts}`}
        </button>
      </div>

      {/* Images */}
      <div style={{
        flex: 1, minHeight: 0,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        gap: '4px', padding: '8px',
        opacity: transitioning ? 0 : 1,
        transition: 'opacity 0.12s',
        background: '#0a0a0a',
      }}>
        {generating && batchProgress ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: '20px', paddingTop: '20vh',
          }}>
            <div style={{
              width: '32px', height: '32px',
              border: '2.5px solid #333',
              borderTopColor: '#30D158',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }} />
            <span style={{ color: '#888', fontSize: '13px', fontVariantNumeric: 'tabular-nums' }}>
              {batchProgress.completed}/{batchProgress.expected}
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
