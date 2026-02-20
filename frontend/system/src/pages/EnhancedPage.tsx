import { useState, useCallback, useEffect, type ImgHTMLAttributes } from 'react'
import { PageShell } from '../components/layout/PageShell'
import { Card } from '../components/layout/Card'

function FadeImg({ style, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}`} style={{ width: '100%', height: '100%', ...style }}>
      <img {...props} onLoad={() => setLoaded(true)} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
    </div>
  )
}

interface Proposal {
  id: number
  uuid: string
  type: string
  params: Record<string, unknown>
  original_url: string
  preview_url: string | null
  feedback: string | null
}

interface Stats {
  pending: number; accepted: number; rejected: number
  deployed: number; undeployed: number; feedback: number
}

interface LearningRate {
  rate: number; accepted: number; rejected: number
}

interface BatchData {
  batch_id: number | null
  proposals: Proposal[]
  stats: Stats
  learning: Record<string, LearningRate>
}

const TYPE_LABELS: Record<string, string> = {
  border_crop: 'CROP',
  exposure: 'LIGHT',
  gemma_crop: 'REFRAME',
  rotation: 'ROTATE',
}

const TYPE_COLORS: Record<string, { bg: string; fg: string }> = {
  border_crop: { bg: 'rgba(245,158,11,0.15)', fg: '#f59e0b' },
  exposure: { bg: 'rgba(56,132,244,0.15)', fg: '#3884f4' },
  gemma_crop: { bg: 'rgba(168,85,247,0.15)', fg: '#a855f7' },
  rotation: { bg: 'rgba(34,197,94,0.15)', fg: '#22c55e' },
}

const FEEDBACK_OPTIONS = [
  { key: 'more_light', label: 'More Light' },
  { key: 'more_contrast', label: 'More Contrast' },
  { key: 'fix_tint', label: 'Fix Tint' },
  { key: 'rotate', label: 'Rotate' },
  { key: 'crop_tighter', label: 'Crop Tighter' },
  { key: 'crop_looser', label: 'Crop Looser' },
]

function Stat({ value, label, dim }: { value: number | string; label: string; dim?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
      <span style={{
        fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)',
        opacity: dim ? 0.4 : 1, lineHeight: 1,
      }}>
        {value}
      </span>
      <span style={{
        fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-caps)',
      }}>
        {label}
      </span>
    </div>
  )
}

function LearningBadges({ learning }: { learning: Record<string, LearningRate> }) {
  const entries = Object.entries(learning).sort(([,a],[,b]) => b.rate - a.rate)
  if (entries.length === 0) return null
  return (
    <div style={{
      display: 'flex', gap: 'var(--space-3)', justifyContent: 'center',
      flexWrap: 'wrap', marginTop: 'var(--space-4)',
    }}>
      {entries.map(([type, lr]) => (
        <div key={type} style={{
          padding: 'var(--space-1) var(--space-3)',
          borderRadius: 'var(--radius-sm)',
          background: (TYPE_COLORS[type] ?? { bg: 'var(--surface-2)' }).bg,
          fontSize: 'var(--text-xs)',
        }}>
          <span style={{ fontWeight: 700, color: (TYPE_COLORS[type] ?? { fg: 'var(--muted)' }).fg }}>
            {TYPE_LABELS[type] ?? type.toUpperCase()}
          </span>
          <span style={{ color: 'var(--muted)', marginLeft: 6 }}>
            {Math.round(lr.rate * 100)}% ({lr.accepted}A/{lr.rejected}R)
          </span>
        </div>
      ))}
    </div>
  )
}

interface AcceptedItem {
  uuid: string; type: string; preview_url: string | null
  original_url: string; deployed: boolean
}

export function EnhancedPage() {
  const [batch, setBatch] = useState<BatchData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [batchAccepted, setBatchAccepted] = useState(0)
  const [batchRejected, setBatchRejected] = useState(0)
  const [batchFeedback, setBatchFeedback] = useState(0)
  const [batchDone, setBatchDone] = useState(false)
  const [voting, setVoting] = useState(false)
  const [deploying, setDeploying] = useState(false)
  const [deployMsg, setDeployMsg] = useState('')
  const [generating, setGenerating] = useState(false)
  const [autoDeployed, setAutoDeployed] = useState(0)
  const [showAccepted, setShowAccepted] = useState(false)
  const [acceptedList, setAcceptedList] = useState<AcceptedItem[]>([])

  const fetchAccepted = useCallback(() => {
    fetch('/api/enhance/accepted')
      .then(r => r.json())
      .then(d => setAcceptedList(d.accepted ?? []))
      .catch(() => {})
  }, [])

  const fetchBatch = useCallback(() => {
    setLoading(true)
    setError(null)
    fetch('/api/enhance/batch')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: BatchData) => {
        setBatch(data)
        // If batch has proposals, enter review mode
        if (data.proposals.length > 0) {
          setIndex(0)
          setBatchAccepted(0)
          setBatchRejected(0)
          setBatchFeedback(0)
          setBatchDone(false)
          setAutoDeployed(0)
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchBatch() }, [fetchBatch])

  const proposal = batch?.proposals[index] ?? null

  const [picked, setPicked] = useState<'original' | 'proposed' | null>(null)

  const advance = useCallback(() => {
    setPicked(null)
    setVoting(false)
    if (batch && index < batch.proposals.length - 1) {
      setIndex(i => i + 1)
    } else {
      setBatchDone(true)
    }
  }, [batch, index])

  const vote = useCallback((status: 'accepted' | 'rejected') => {
    if (!proposal || !batch || voting) return
    setVoting(true)
    setPicked(status === 'accepted' ? 'proposed' : 'original')

    fetch('/api/enhance/vote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proposal_id: proposal.id, status, batch_id: batch.batch_id }),
    })
      .then(r => r.json())
      .then((data: { ok: boolean; batch_completed?: boolean; auto_deploy?: number }) => {
        if (status === 'accepted') setBatchAccepted(n => n + 1)
        else setBatchRejected(n => n + 1)
        if (data.auto_deploy) setAutoDeployed(data.auto_deploy)
        setTimeout(advance, 350)
      })
      .catch(() => { setPicked(null); setVoting(false) })
  }, [proposal, batch, voting, advance])

  const sendFeedback = useCallback((feedbackKey: string) => {
    if (!proposal || !batch || voting) return
    setVoting(true)

    fetch('/api/enhance/vote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proposal_id: proposal.id,
        status: 'feedback',
        feedback: feedbackKey,
        batch_id: batch.batch_id,
      }),
    })
      .then(r => r.json())
      .then(() => {
        setBatchFeedback(n => n + 1)
        setTimeout(advance, 200)
      })
      .catch(() => setVoting(false))
  }, [proposal, batch, voting, advance])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (batchDone || !batch || batch.proposals.length === 0) return
      if (e.key === 'ArrowRight' || e.key === 'a') vote('accepted')
      if (e.key === 'ArrowLeft' || e.key === 'd') vote('rejected')
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [vote, batchDone, batch])

  const handleDeploy = () => {
    setDeploying(true)
    setDeployMsg('')
    fetch('/api/enhance/deploy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) setDeployMsg(d.error)
        else {
          setDeployMsg(`Deployed ${d.count} enhancements`)
          setTimeout(fetchBatch, 1500)
        }
      })
      .catch(() => setDeployMsg('Failed'))
      .finally(() => setDeploying(false))
  }

  const handleGenerate = () => {
    setGenerating(true)
    setDeployMsg('')
    fetch('/api/enhance/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
      .then(r => r.json())
      .then(() => {
        setBatchDone(false)
        fetchBatch()
      })
      .catch(() => {})
      .finally(() => setGenerating(false))
  }

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!batch) return null

  const stats = batch.stats
  const hasLearning = batch.learning && Object.keys(batch.learning).length > 0
  const totalEnhanced = stats.accepted + stats.deployed
  const totalUndeployed = stats.undeployed ?? 0

  // ── Empty state or batch complete: show Generate 30 ──
  if (batchDone || batch.proposals.length === 0) {
    return (
      <PageShell title="Enhanced" hideFooter>
        <Card>
          <div style={{ textAlign: 'center', padding: 'var(--space-12) var(--space-6)' }}>

            {/* Batch results (only after completing a review) */}
            {batchDone && (
              <>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-4)' }}>
                  Batch {batch.batch_id} complete
                </div>
                <div style={{ display: 'flex', gap: 'var(--space-8)', justifyContent: 'center', marginBottom: 'var(--space-8)' }}>
                  <Stat value={batchAccepted} label="accepted" />
                  <Stat value={batchRejected} label="rejected" />
                  {batchFeedback > 0 && <Stat value={batchFeedback} label="feedback" dim />}
                </div>
              </>
            )}

            {/* Overall stats (only if there's history) */}
            {totalEnhanced > 0 && (
              <div style={{
                display: 'flex', gap: 'var(--space-8)', justifyContent: 'center', marginBottom: 'var(--space-6)',
                paddingTop: batchDone ? 'var(--space-4)' : 0,
                borderTop: batchDone ? '1px solid var(--border)' : 'none',
              }}>
                <Stat value={totalEnhanced} label="enhanced" />
                <Stat value={stats.rejected} label="rejected" dim={stats.rejected === 0} />
              </div>
            )}

            {/* Learning badges */}
            {hasLearning && (
              <div style={{ marginBottom: 'var(--space-8)' }}>
                <LearningBadges learning={batch.learning} />
              </div>
            )}

            {/* Primary action: Generate 30 */}
            <button
              onClick={handleGenerate}
              disabled={generating}
              style={{
                padding: 'var(--space-4) var(--space-10)',
                borderRadius: 'var(--radius-md)',
                background: generating ? 'var(--surface-2)' : 'rgba(56,132,244,0.15)',
                color: generating ? 'var(--muted)' : '#3884f4',
                border: `1px solid ${generating ? 'var(--border)' : '#3884f4'}`,
                cursor: generating ? 'default' : 'pointer',
                fontWeight: 700,
                fontSize: 'var(--text-lg)',
                letterSpacing: 'var(--tracking-caps)',
                transition: 'all 0.2s',
              }}
            >
              {generating ? 'Generating...' : 'Generate 30'}
            </button>

            {/* Auto-deploy notice */}
            {autoDeployed > 0 && (
              <div style={{
                marginTop: 'var(--space-4)', padding: 'var(--space-3) var(--space-6)',
                borderRadius: 'var(--radius-md)', background: 'rgba(34,197,94,0.12)',
                color: '#22c55e', fontSize: 'var(--text-sm)', fontWeight: 600,
              }}>
                Auto-deploying {autoDeployed} accepted enhancements...
              </div>
            )}

            {/* Secondary actions */}
            <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'center', marginTop: 'var(--space-6)', flexWrap: 'wrap' }}>
              {totalUndeployed > 0 && !autoDeployed && (
                <button onClick={handleDeploy} disabled={deploying} style={btnGhost}>
                  {deploying ? 'Deploying...' : `Deploy ${totalUndeployed}`}
                </button>
              )}
              {totalEnhanced > 0 && (
                <button onClick={() => { setShowAccepted(!showAccepted); if (!showAccepted) fetchAccepted() }} style={btnGhost}>
                  {showAccepted ? 'Hide' : 'View'} Enhanced
                </button>
              )}
            </div>
            {deployMsg && <div style={{ marginTop: 'var(--space-2)', fontSize: 'var(--text-sm)', color: 'var(--muted)' }}>{deployMsg}</div>}
          </div>

          {/* Accepted gallery */}
          {showAccepted && acceptedList.length > 0 && (
            <div style={{
              marginTop: 'var(--space-6)', paddingTop: 'var(--space-6)',
              borderTop: '1px solid var(--border)',
            }}>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase',
                letterSpacing: 'var(--tracking-caps)', marginBottom: 'var(--space-4)', textAlign: 'center',
              }}>
                {acceptedList.length} enhanced images
              </div>
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
                gap: 'var(--space-2)',
              }}>
                {acceptedList.map(item => (
                  <div key={item.uuid} style={{ position: 'relative', aspectRatio: '3/2', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                    <img
                      src={item.preview_url ?? item.original_url}
                      alt={item.uuid.slice(0, 8)}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      loading="lazy"
                    />
                    {item.deployed && (
                      <span style={{
                        position: 'absolute', top: 2, right: 2,
                        fontSize: '9px', fontWeight: 700, padding: '1px 4px',
                        borderRadius: 'var(--radius-sm)',
                        background: 'rgba(34,197,94,0.3)', color: '#22c55e',
                      }}>
                        LIVE
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </PageShell>
    )
  }

  // ── Review mode ──
  if (!proposal) return null

  const remaining = batch.proposals.length - index
  const transforms = Array.isArray(proposal.params.transforms)
    ? proposal.params.transforms as string[]
    : [proposal.type]
  const typeColor = TYPE_COLORS[proposal.type] ?? { bg: 'var(--surface-2)', fg: 'var(--muted)' }

  return (
    <PageShell
      title="Enhanced"
      subtitle="Click image to choose. Feedback tags re-queue for next batch."
      hideFooter
    >
      <Card>
        {/* Stats bar */}
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)',
          marginBottom: 'var(--space-6)', paddingBottom: 'var(--space-4)',
          borderBottom: '1px solid var(--border)',
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{
              fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase',
              letterSpacing: 'var(--tracking-caps)', marginBottom: 2,
            }}>
              Batch {batch.batch_id} {'\u00B7'} {batch.proposals.length} proposals
            </span>
            <Stat value={remaining} label="remaining" />
            <div style={{ display: 'flex', gap: 'var(--space-6)' }}>
              <Stat value={batchAccepted} label="accepted" />
              <Stat value={batchRejected} label="rejected" dim={batchRejected === 0} />
            </div>
          </div>

          <div style={{
            display: 'flex', flexDirection: 'column', gap: 4,
            borderLeft: '1px solid var(--border)', paddingLeft: 'var(--space-6)',
          }}>
            <span style={{
              fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase',
              letterSpacing: 'var(--tracking-caps)',
            }}>
              Overall
            </span>
            <Stat value={totalEnhanced} label="enhanced" />
            <div style={{ display: 'flex', gap: 'var(--space-6)' }}>
              <Stat value={totalUndeployed} label="to deploy" dim={totalUndeployed === 0} />
              <Stat value={stats.pending + stats.feedback} label="to review" dim={stats.pending + stats.feedback === 0} />
            </div>
          </div>
        </div>

        {/* Type badges + feedback tag */}
        <div style={{ marginBottom: 'var(--space-3)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {transforms.map(t => {
            const tc = TYPE_COLORS[t] ?? { bg: 'var(--surface-2)', fg: 'var(--muted)' }
            return (
              <span key={t} style={{
                fontSize: 'var(--text-xs)', fontWeight: 700, padding: 'var(--space-1) var(--space-3)',
                borderRadius: 'var(--radius-sm)',
                background: tc.bg, color: tc.fg,
                letterSpacing: 'var(--tracking-caps)',
              }}>
                {TYPE_LABELS[t] ?? t.toUpperCase()}
              </span>
            )
          })}
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
            {proposal.uuid.slice(0, 8)}
          </span>
          {proposal.feedback && (
            <span style={{
              fontSize: 'var(--text-xs)', fontWeight: 600, padding: 'var(--space-1) var(--space-3)',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(239,68,68,0.15)', color: '#ef4444',
            }}>
              {proposal.feedback.replace('_', ' ').toUpperCase()}
            </span>
          )}
        </div>

        {/* Comparison grid */}
        <div className="bt-grid">
          <div
            className="bt-cell"
            data-clickable={!voting ? 'true' : undefined}
            onClick={() => vote('rejected')}
            style={{
              position: 'relative', cursor: voting ? 'default' : 'pointer',
              outline: picked === 'original' ? '3px solid var(--system-blue)' : 'none',
              outlineOffset: '-3px',
            }}
          >
            <FadeImg src={proposal.original_url} alt="Original" />
            <span style={{
              position: 'absolute', top: 'var(--space-2)', left: 'var(--space-2)',
              fontSize: 'var(--text-xs)', fontWeight: 600, padding: 'var(--space-1) var(--space-3)',
              borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
              background: 'rgba(0,0,0,0.5)', color: '#fff', zIndex: 2,
              opacity: picked ? 1 : 0.3, transition: 'opacity 0.2s',
            }}>
              Original
            </span>
          </div>
          <div
            className="bt-cell"
            data-clickable={!voting ? 'true' : undefined}
            onClick={() => vote('accepted')}
            style={{
              position: 'relative', cursor: voting ? 'default' : 'pointer',
              outline: picked === 'proposed' ? '3px solid var(--system-blue)' : 'none',
              outlineOffset: '-3px',
            }}
          >
            {proposal.preview_url ? (
              <FadeImg src={proposal.preview_url} alt="Proposed" />
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--muted)' }}>
                No preview
              </div>
            )}
            <span style={{
              position: 'absolute', top: 'var(--space-2)', right: 'var(--space-2)',
              fontSize: 'var(--text-xs)', fontWeight: 600, padding: 'var(--space-1) var(--space-3)',
              borderRadius: 'var(--radius-sm)',
              background: typeColor.bg, color: typeColor.fg, zIndex: 2,
              opacity: picked ? 1 : 0.3, transition: 'opacity 0.2s',
            }}>
              Proposed
            </span>
          </div>
        </div>

        {/* Feedback bar */}
        <div style={{
          display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-3)',
          justifyContent: 'center', flexWrap: 'wrap',
        }}>
          {FEEDBACK_OPTIONS.map(fb => (
            <button
              key={fb.key}
              onClick={() => sendFeedback(fb.key)}
              disabled={voting}
              style={{
                padding: 'var(--space-1) var(--space-3)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface-2)',
                color: 'var(--muted)',
                border: '1px solid var(--border)',
                cursor: voting ? 'default' : 'pointer',
                fontSize: 'var(--text-xs)',
                fontWeight: 500,
                opacity: voting ? 0.4 : 1,
                transition: 'opacity 0.15s',
              }}
            >
              {fb.label}
            </button>
          ))}
        </div>
      </Card>
    </PageShell>
  )
}

const btnGhost: React.CSSProperties = {
  padding: 'var(--space-2) var(--space-6)', borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-2)', color: 'var(--muted)',
  border: '1px solid var(--border)', cursor: 'pointer', fontSize: 'var(--text-sm)',
}
