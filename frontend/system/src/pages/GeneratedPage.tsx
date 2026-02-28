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

/* Cost estimate per variant (Imagen 3 standard) */
const COST_PER_VARIANT = 0.04

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
  const [exportedIds, setExportedIds] = useState<Set<string>>(new Set())
  const [comment, setComment] = useState('')
  const [generateModalOpen, setGenerateModalOpen] = useState(false)
  const [generateCount, setGenerateCount] = useState(20)
  const commentRef = useRef<HTMLInputElement>(null)
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

  const launchGenerate = useCallback(async (count: number) => {
    setGenerateModalOpen(false)
    setGenerating(true)
    setBatchProgress({ completed: 0, expected: count })
    try {
      const r = await fetch('/api/generated/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count }),
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
  }, [showToast, stopProgressPoll, pollProgress])

  const handleExport = useCallback(async () => {
    setExporting(true)
    try {
      const r = await fetch('/api/generated/export', { method: 'POST' })
      if (r.ok) {
        const d = await r.json()
        showToast(`Exporting ${d.count} variants in Terminal...`)
        setExportedIds(new Set(Object.keys(reviews)))
        setExporting(false)
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
    const text = comment.trim() || undefined
    setReviews(r => ({ ...r, [variantId]: status }))
    setComment('')
    try {
      await fetch('/api/generated/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant_id: variantId, status, comment: text }),
      })
    } catch {
      setReviews(r => {
        const next = { ...r }
        delete next[variantId]
        return next
      })
    }
  }, [comment])

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

  // Keyboard: A = accept, R = reject (disabled while generating or modal open)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (generating || generateModalOpen) return
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
  }, [reviewAndAdvance, generating, generateModalOpen])

  // Close modal on Escape
  useEffect(() => {
    if (!generateModalOpen) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setGenerateModalOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [generateModalOpen])

  if (loading) return <div style={{ color: 'var(--muted)', padding: '80px', textAlign: 'center' }}>Loading...</div>
  if (error) return <div style={{ color: 'var(--red)', padding: '80px', textAlign: 'center' }}>Error: {error}</div>
  if (!data) return null

  const review = current ? getReview(current) : null
  // Count accepts done this session that haven't been exported yet
  const newAccepts = Object.entries(reviews).filter(
    ([, v]) => v === 'accepted' && !exportedIds.has(v)
  ).length
  const exportReady = newAccepts > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Top bar */}
      <div className="filter-bar" style={{
        flexShrink: 0, padding: '10px 16px', margin: 0,
        borderBottom: '1px solid var(--border)',
        alignItems: 'center', gap: '8px',
      }}>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
          {filtered.length} to review {data.accepted > 0 && `· ${data.accepted} accepted · ${data.rejected} rejected`}
        </span>

        {/* Comment input — inline in top bar */}
        {current && !generating && !exporting && (
          <input
            ref={commentRef}
            type="text"
            value={comment}
            onChange={e => setComment(e.target.value)}
            placeholder="Comment..."
            style={{
              flex: '1 1 120px',
              minWidth: '80px',
              maxWidth: '300px',
              padding: '5px 10px',
              background: '#1a1a1a',
              border: '1px solid #333',
              borderRadius: '6px',
              color: '#ccc',
              fontSize: '12px',
              outline: 'none',
            }}
            onFocus={e => (e.target.style.borderColor = '#555')}
            onBlur={e => (e.target.style.borderColor = '#333')}
          />
        )}

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

        <button className="filter-btn"
          onClick={() => generating ? undefined : setGenerateModalOpen(true)}
          disabled={generating || exporting}
          style={{
            borderColor: generating ? '#FF9F0A' : undefined,
            color: generating ? '#FF9F0A' : undefined,
            opacity: generating || exporting ? 0.8 : 1,
          }}>
          {generating && batchProgress
            ? `⏳ ${batchProgress.completed}/${batchProgress.expected}`
            : 'Generate'}
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
        flex: '1 1 0', minHeight: 0,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        gap: '4px', padding: '8px',
        transition: 'opacity 0.12s',
        background: '#0a0a0a',
        overflow: 'hidden',
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

      {/* Generate modal */}
      {generateModalOpen && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(0, 0, 0, 0.6)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={() => setGenerateModalOpen(false)}
        >
          <div
            style={{
              background: '#1c1c1e',
              borderRadius: '14px',
              padding: '28px 32px',
              minWidth: '320px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ fontSize: '16px', fontWeight: 600, color: '#fff', marginBottom: '20px' }}>
              Generate Variants
            </div>

            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              {[10, 20, 40, 80].map(n => (
                <button
                  key={n}
                  onClick={() => setGenerateCount(n)}
                  style={{
                    flex: 1,
                    padding: '10px 0',
                    background: generateCount === n ? '#0A84FF' : '#2c2c2e',
                    color: generateCount === n ? '#fff' : '#999',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '15px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                >
                  {n}
                </button>
              ))}
            </div>

            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 14px',
              background: '#2c2c2e',
              borderRadius: '8px',
              marginBottom: '20px',
            }}>
              <span style={{ color: '#999', fontSize: '13px' }}>Estimated cost</span>
              <span style={{ color: '#fff', fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                ${(generateCount * COST_PER_VARIANT).toFixed(2)}
              </span>
            </div>

            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 14px',
              background: '#2c2c2e',
              borderRadius: '8px',
              marginBottom: '24px',
              fontSize: '12px', color: '#666',
            }}>
              <span>~{Math.ceil(generateCount / 4)} min at 4 req/min</span>
              <span>Imagen 3</span>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => setGenerateModalOpen(false)}
                style={{
                  flex: 1, padding: '10px',
                  background: '#2c2c2e', color: '#999',
                  border: 'none', borderRadius: '8px',
                  fontSize: '14px', fontWeight: 500, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => launchGenerate(generateCount)}
                style={{
                  flex: 1, padding: '10px',
                  background: '#30D158', color: '#000',
                  border: 'none', borderRadius: '8px',
                  fontSize: '14px', fontWeight: 600, cursor: 'pointer',
                }}
              >
                Generate {generateCount}
              </button>
            </div>
          </div>
        </div>
      )}
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
