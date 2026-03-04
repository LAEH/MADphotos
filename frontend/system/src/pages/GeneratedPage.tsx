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
  unexported: number
}

const COST_PER_VARIANT = 0.04

type ProcessStatus = 'idle' | 'running' | 'done' | 'error'

export function GeneratedPage() {
  const [data, setData] = useState<StyleData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reviews, setReviews] = useState<Record<string, string>>({})
  const [aspectRatio, setAspectRatio] = useState<number>(1.5)
  const [toast, setToast] = useState<string | null>(null)
  const [comment, setComment] = useState('')
  const [generateModalOpen, setGenerateModalOpen] = useState(false)
  const [generateCount, setGenerateCount] = useState(20)
  const commentRef = useRef<HTMLInputElement>(null)
  const cursorReject = useRef('')
  const cursorAccept = useRef('')
  if (!cursorReject.current) cursorReject.current = emojiCursor('\u{1F612}')
  if (!cursorAccept.current) cursorAccept.current = emojiCursor('\u{1F60D}')

  // Process state — generate
  const [genStatus, setGenStatus] = useState<ProcessStatus>('idle')
  const [genLog, setGenLog] = useState('')
  const [genProgress, setGenProgress] = useState<{ completed: number; expected: number } | null>(null)

  // Process state — export
  const [exportStatus, setExportStatus] = useState<ProcessStatus>('idle')
  const [exportLog, setExportLog] = useState('')

  // GCP auth state
  const [gcpAuth, setGcpAuth] = useState<'unknown' | 'authenticated' | 'unauthenticated'>('unknown')
  const [authWaiting, setAuthWaiting] = useState(false)
  const pendingAction = useRef<{ action: 'generate'; count: number } | { action: 'export' } | null>(null)

  // DB lock state
  const [dbLocked, setDbLocked] = useState(false)
  const [dbHolder, setDbHolder] = useState('')

  const logEndRef = useRef<HTMLDivElement>(null)

  const fetchData = useCallback(() => {
    fetch('/api/generated')
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then((d: StyleData) => {
        setData(prev => {
          if (!prev) return d
          const existing = new Set(prev.pairs.map(p => p.variant_id))
          const newPairs = d.pairs.filter(p => !existing.has(p.variant_id))
          if (newPairs.length === 0) return { ...prev, accepted: d.accepted, rejected: d.rejected, unexported: d.unexported }
          return { ...d, pairs: [...prev.pairs, ...newPairs] }
        })
        setLoading(false)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }, [])

  // Poll generate progress
  useEffect(() => {
    if (genStatus !== 'running') return
    const poll = () => {
      fetch('/api/generated/progress')
        .then(r => r.json())
        .then(p => {
          setGenProgress({ completed: p.completed, expected: p.expected })
          setGenLog(p.log || '')
          if (p.status === 'done' || p.status === 'error') {
            setGenStatus(p.status)
            fetchData()
          }
        })
        .catch(() => {})
    }
    poll()
    const id = setInterval(poll, 3000)
    return () => clearInterval(id)
  }, [genStatus, fetchData])

  // Poll export progress
  useEffect(() => {
    if (exportStatus !== 'running') return
    const poll = () => {
      fetch('/api/generated/export/progress')
        .then(r => r.json())
        .then(p => {
          setExportLog(p.log || '')
          if (p.status === 'done' || p.status === 'error') {
            setExportStatus(p.status)
            fetchData()
          }
        })
        .catch(() => {})
    }
    poll()
    const id = setInterval(poll, 2000)
    return () => clearInterval(id)
  }, [exportStatus, fetchData])

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [genLog, exportLog])

  // On mount: detect if generate is already running
  useEffect(() => {
    fetch('/api/generated/progress')
      .then(r => r.json())
      .then(p => {
        if (!p.done && p.status !== 'error') {
          setGenStatus('running')
          setGenProgress({ completed: p.completed, expected: p.expected })
          setGenLog(p.log || '')
        }
      })
      .catch(() => {})
    fetch('/api/generated/export/progress')
      .then(r => r.json())
      .then(p => {
        if (p.status === 'running') {
          setExportStatus('running')
          setExportLog(p.log || '')
        }
      })
      .catch(() => {})
  }, [])

  // Check GCP auth on mount
  useEffect(() => {
    fetch('/api/gcp-auth')
      .then(r => r.json())
      .then(d => setGcpAuth(d.authenticated ? 'authenticated' : 'unauthenticated'))
      .catch(() => {})
  }, [])

  // Poll auth when waiting for browser OAuth
  useEffect(() => {
    if (!authWaiting) return
    const poll = setInterval(() => {
      fetch('/api/gcp-auth')
        .then(r => r.json())
        .then(d => {
          if (d.authenticated) {
            setGcpAuth('authenticated')
            setAuthWaiting(false)
            // Auto-retry pending action
            const pending = pendingAction.current
            pendingAction.current = null
            if (pending?.action === 'generate') {
              launchGenerate(pending.count)
            } else if (pending?.action === 'export') {
              handleExport()
            }
          }
        })
        .catch(() => {})
    }, 3000)
    return () => clearInterval(poll)
  }, [authWaiting]) // eslint-disable-line react-hooks/exhaustive-deps

  // Poll DB lock when waiting for it to clear
  useEffect(() => {
    if (!dbLocked) return
    const poll = setInterval(() => {
      fetch('/api/db-status')
        .then(r => r.json())
        .then(d => {
          if (!d.locked) {
            setDbLocked(false)
            setDbHolder('')
            // Auto-retry pending action
            const pending = pendingAction.current
            pendingAction.current = null
            if (pending?.action === 'generate') {
              launchGenerate(pending.count)
            } else if (pending?.action === 'export') {
              handleExport()
            }
          } else {
            setDbHolder(d.holder || '')
          }
        })
        .catch(() => {})
    }, 3000)
    return () => clearInterval(poll)
  }, [dbLocked]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-poll data
  useEffect(() => {
    fetchData()
    const busy = genStatus === 'running' || exportStatus === 'running'
    const id = setInterval(fetchData, busy ? 5_000 : 30_000)
    return () => clearInterval(id)
  }, [fetchData, genStatus, exportStatus])

  const startAuth = useCallback((pending: typeof pendingAction.current) => {
    pendingAction.current = pending
    setGcpAuth('unauthenticated')
    setAuthWaiting(true)
    fetch('/api/gcp-auth', { method: 'POST' }).catch(() => {})
  }, [])

  const launchGenerate = useCallback(async (count: number) => {
    setGenerateModalOpen(false)
    setGenStatus('running')
    setGenLog('')
    setGenProgress({ completed: 0, expected: count })
    try {
      const r = await fetch('/api/generated/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count }),
      })
      const d = await r.json()
      if (d.auth_required) {
        setGenStatus('idle')
        setGenProgress(null)
        startAuth({ action: 'generate', count })
        return
      }
      if (d.db_locked) {
        setGenStatus('idle')
        setGenProgress(null)
        pendingAction.current = { action: 'generate', count }
        setDbLocked(true)
        setDbHolder(d.holder || '')
        return
      }
      if (!r.ok || d.ok === false) {
        showToast(d.error || 'Failed to launch')
        setGenStatus('idle')
        setGenProgress(null)
      }
    } catch {
      showToast('Failed to launch')
      setGenStatus('idle')
      setGenProgress(null)
    }
  }, [showToast, startAuth])

  const handleExport = useCallback(async () => {
    setExportStatus('running')
    setExportLog('')
    try {
      const r = await fetch('/api/generated/export', { method: 'POST' })
      const d = await r.json()
      if (d.auth_required) {
        setExportStatus('idle')
        startAuth({ action: 'export' })
        return
      }
      if (d.db_locked) {
        setExportStatus('idle')
        pendingAction.current = { action: 'export' }
        setDbLocked(true)
        setDbHolder(d.holder || '')
        return
      }
      if (!r.ok || d.ok === false) {
        showToast(d.error || 'Nothing to export')
        setExportStatus('idle')
      }
    } catch {
      showToast('Export failed')
      setExportStatus('idle')
    }
  }, [showToast, startAuth])

  const getReview = useCallback((pair: StylePair) => {
    return reviews[pair.variant_id] ?? pair.review
  }, [reviews])

  const handleReview = useCallback(async (variantId: string, status: string) => {
    const text = comment.trim() || undefined
    setReviews(r => ({ ...r, [variantId]: status }))
    if (status === 'accepted') {
      setData(prev => prev ? { ...prev, unexported: prev.unexported + 1, accepted: prev.accepted + 1 } : prev)
    } else if (status === 'rejected') {
      setData(prev => prev ? { ...prev, rejected: prev.rejected + 1 } : prev)
    }
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
      fetchData()
    }
  }, [comment, fetchData])

  const filtered = useMemo(() => {
    if (!data) return []
    return data.pairs.filter(p => !getReview(p))
  }, [data, getReview])

  const current = filtered[0] ?? null

  const reviewAndAdvance = useCallback((status: string) => {
    if (!current) return
    handleReview(current.variant_id, status)
  }, [current, handleReview])

  // Keyboard: A = accept, R = reject
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (genStatus === 'running' || exportStatus === 'running' || generateModalOpen) return
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
  }, [reviewAndAdvance, genStatus, exportStatus, generateModalOpen])

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
  const unexported = typeof data.unexported === 'number' ? data.unexported : 0
  const exportReady = unexported > 0
  const generating = genStatus === 'running'
  const exporting = exportStatus === 'running'
  const busy = generating || exporting

  // Block Generate: must have all reviewed AND all exported
  const canGenerate = !busy && filtered.length === 0 && unexported === 0

  // Active process log to display
  const activeLog = exporting ? exportLog : generating ? genLog : ''
  const activeLabel = exporting
    ? 'Exporting variants...'
    : generating && genProgress
      ? `Generating ${genProgress.completed}/${genProgress.expected}...`
      : ''

  // Just finished a process — show done state briefly
  const justDone = (genStatus === 'done' || exportStatus === 'done' || genStatus === 'error' || exportStatus === 'error') && !busy
  const doneLog = genStatus === 'done' || genStatus === 'error' ? genLog : exportLog
  const doneIsError = genStatus === 'error' || exportStatus === 'error'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Top bar */}
      <div className="filter-bar" style={{
        flexShrink: 0, padding: '10px 16px', margin: 0,
        borderBottom: '1px solid var(--border)',
        alignItems: 'center', gap: '8px',
      }}>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
          {filtered.length} to review {data.accepted > 0 && `\u00b7 ${data.accepted} accepted \u00b7 ${data.rejected} rejected`}
        </span>

        {/* Comment input */}
        {current && !busy && (
          <input
            ref={commentRef}
            type="text"
            value={comment}
            onChange={e => setComment(e.target.value)}
            placeholder="Comment..."
            style={{
              flex: '1 1 120px', minWidth: '80px', maxWidth: '300px',
              padding: '5px 10px', background: '#1a1a1a',
              border: '1px solid #333', borderRadius: '6px',
              color: '#ccc', fontSize: '12px', outline: 'none',
            }}
            onFocus={e => (e.target.style.borderColor = '#555')}
            onBlur={e => (e.target.style.borderColor = '#333')}
          />
        )}

        <div style={{ flex: 1 }} />

        {toast && (
          <span style={{ color: '#30D158', fontSize: 'var(--text-xs)' }}>{toast}</span>
        )}

        {current && !busy && (
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
          onClick={() => canGenerate ? setGenerateModalOpen(true) : undefined}
          disabled={!canGenerate}
          style={{
            borderColor: generating ? '#FF9F0A' : undefined,
            color: generating ? '#FF9F0A' : undefined,
            opacity: canGenerate ? 1 : generating ? 1 : 0.3,
            cursor: canGenerate ? 'pointer' : 'default',
          }}>
          {generating && genProgress
            ? `\u23f3 ${genProgress.completed}/${genProgress.expected}`
            : 'Generate'}
        </button>

        <button className="filter-btn" onClick={handleExport}
          disabled={exporting || !exportReady || generating}
          style={{
            borderColor: exporting ? '#FF9F0A' : exportReady && !busy ? '#30D158' : undefined,
            color: exporting ? '#FF9F0A' : exportReady && !busy ? '#30D158' : undefined,
            opacity: exportReady || exporting ? 1 : 0.3,
            cursor: exportReady && !busy ? 'pointer' : 'default',
          }}>
          {exporting ? '\u23f3 Exporting...' : `Export ${unexported}`}
        </button>
      </div>

      {/* Main content area */}
      <div style={{
        flex: '1 1 0', minHeight: 0,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        gap: '4px', padding: '8px',
        background: '#0a0a0a', overflow: 'hidden',
      }}>
        {/* Auth required banner */}
        {gcpAuth === 'unauthenticated' && authWaiting ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: '16px', paddingTop: '8vh', width: '100%', maxWidth: '480px',
          }}>
            <div style={{
              width: '100%', padding: '24px 28px',
              background: '#111', borderRadius: '12px',
              border: '1px solid rgba(255, 159, 10, 0.3)',
            }}>
              <div style={{
                fontSize: '15px', fontWeight: 600, color: '#FF9F0A',
                marginBottom: '8px',
              }}>
                GCP authentication required
              </div>
              <div style={{
                fontSize: '12px', color: '#888', lineHeight: '1.6',
                marginBottom: '12px',
              }}>
                Run in terminal:
              </div>
              <div style={{
                padding: '8px 12px', background: '#0a0a0a', borderRadius: '6px',
                fontFamily: 'var(--font-mono, monospace)', fontSize: '12px',
                color: '#ccc', marginBottom: '16px', userSelect: 'all',
              }}>
                gcloud auth login && gcloud auth application-default login
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '16px', height: '16px',
                  border: '2px solid #333',
                  borderTopColor: '#FF9F0A',
                  borderRadius: '50%',
                  animation: 'spin 0.8s linear infinite',
                }} />
                <span style={{ fontSize: '12px', color: '#666' }}>
                  Polling until authenticated...
                </span>
              </div>
            </div>
            <button
              className="filter-btn"
              onClick={() => { setAuthWaiting(false); pendingAction.current = null }}
              style={{ color: '#666', fontSize: '12px' }}
            >
              Cancel
            </button>
            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
          </div>

        ) : dbLocked ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: '16px', paddingTop: '8vh', width: '100%', maxWidth: '480px',
          }}>
            <div style={{
              width: '100%', padding: '24px 28px',
              background: '#111', borderRadius: '12px',
              border: '1px solid rgba(255, 69, 58, 0.3)',
            }}>
              <div style={{
                fontSize: '15px', fontWeight: 600, color: '#FF453A',
                marginBottom: '8px',
              }}>
                Database locked
              </div>
              <div style={{
                fontSize: '12px', color: '#888', lineHeight: '1.6',
                marginBottom: '20px',
              }}>
                {dbHolder
                  ? <>Another process is writing to the database: <span style={{ color: '#ccc', fontFamily: 'var(--font-mono, monospace)' }}>{dbHolder}</span></>
                  : 'Another process is writing to the database.'}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '16px', height: '16px',
                  border: '2px solid #333',
                  borderTopColor: '#FF453A',
                  borderRadius: '50%',
                  animation: 'spin 0.8s linear infinite',
                }} />
                <span style={{ fontSize: '12px', color: '#666' }}>
                  Waiting for lock to clear...
                </span>
              </div>
            </div>
            <button
              className="filter-btn"
              onClick={() => { setDbLocked(false); pendingAction.current = null }}
              style={{ color: '#666', fontSize: '12px' }}
            >
              Cancel
            </button>
            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
          </div>

        ) : busy ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: '16px', paddingTop: '8vh', width: '100%', maxWidth: '640px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{
                width: '20px', height: '20px',
                border: '2px solid #333',
                borderTopColor: exporting ? '#FF9F0A' : '#30D158',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite',
              }} />
              <span style={{
                color: exporting ? '#FF9F0A' : '#30D158',
                fontSize: '13px', fontWeight: 500, fontVariantNumeric: 'tabular-nums',
              }}>
                {activeLabel}
              </span>
            </div>
            <div style={{
              width: '100%', maxHeight: 'calc(100vh - 200px)', overflow: 'auto',
              background: '#111', borderRadius: '8px', padding: '14px 16px',
              fontFamily: 'var(--font-mono, "SF Mono", monospace)',
              fontSize: '11px', lineHeight: '1.7', color: '#888',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: `1px solid ${exporting ? 'rgba(255,159,10,0.15)' : 'rgba(48,209,88,0.15)'}`,
            }}>
              {activeLog || 'Starting...'}
              <div ref={logEndRef} />
            </div>
            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
          </div>

        ) : justDone && doneLog ? (
          /* Just finished — show final log */
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: '16px', paddingTop: '24px', width: '100%', maxWidth: '640px',
            maxHeight: '100%', overflow: 'hidden',
          }}>
            <span style={{
              flexShrink: 0,
              color: doneIsError ? '#FF453A' : '#30D158',
              fontSize: '13px', fontWeight: 500,
            }}>
              {doneIsError ? 'Process failed' : 'Complete'}
            </span>
            <div style={{
              width: '100%', flex: '1 1 0', minHeight: 0, overflow: 'auto',
              background: '#111', borderRadius: '8px', padding: '14px 16px',
              fontFamily: 'var(--font-mono, "SF Mono", monospace)',
              fontSize: '11px', lineHeight: '1.7',
              color: doneIsError ? '#FF6961' : '#888',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: `1px solid ${doneIsError ? 'rgba(255,69,58,0.2)' : 'rgba(48,209,88,0.15)'}`,
            }}>
              {doneLog}
            </div>
            <button
              className="filter-btn"
              onClick={() => { setGenStatus('idle'); setExportStatus('idle'); setGenLog(''); setExportLog('') }}
              style={{ flexShrink: 0, color: '#999', marginTop: '8px', marginBottom: '16px' }}
            >
              Dismiss
            </button>
          </div>

        ) : current ? (
          /* Review images */
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
          /* All reviewed — idle state */
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: '12px', paddingTop: '20vh', color: '#666', fontSize: '14px',
          }}>
            <span>
              All reviewed.{exportReady
                ? ` ${unexported} ready to export.`
                : canGenerate
                  ? ' Ready to generate.'
                  : ''}
            </span>
            {!canGenerate && !exportReady && filtered.length === 0 && (
              <span style={{ fontSize: '12px', color: '#444' }}>
                Export accepted variants before generating more.
              </span>
            )}
          </div>
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
              background: '#1c1c1e', borderRadius: '14px',
              padding: '28px 32px', minWidth: '320px',
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
                    flex: 1, padding: '10px 0',
                    background: generateCount === n ? '#0A84FF' : '#2c2c2e',
                    color: generateCount === n ? '#fff' : '#999',
                    border: 'none', borderRadius: '8px',
                    fontSize: '15px', fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  {n}
                </button>
              ))}
            </div>

            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 14px', background: '#2c2c2e', borderRadius: '8px', marginBottom: '20px',
            }}>
              <span style={{ color: '#999', fontSize: '13px' }}>Estimated cost</span>
              <span style={{ color: '#fff', fontSize: '15px', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                ${(generateCount * COST_PER_VARIANT).toFixed(2)}
              </span>
            </div>

            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 14px', background: '#2c2c2e', borderRadius: '8px', marginBottom: '24px',
              fontSize: '12px', color: '#666',
            }}>
              <span>~{Math.ceil(generateCount / 4)} min at 4 req/min</span>
              <span>Imagen 3</span>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => setGenerateModalOpen(false)}
                style={{
                  flex: 1, padding: '10px', background: '#2c2c2e', color: '#999',
                  border: 'none', borderRadius: '8px', fontSize: '14px', fontWeight: 500, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => launchGenerate(generateCount)}
                style={{
                  flex: 1, padding: '10px', background: '#30D158', color: '#000',
                  border: 'none', borderRadius: '8px', fontSize: '14px', fontWeight: 600, cursor: 'pointer',
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
