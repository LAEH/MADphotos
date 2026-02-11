import { useState, type ImgHTMLAttributes } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { PageShell } from '../components/layout/PageShell'
import { Card } from '../components/layout/Card'

function FadeImg({ style, className, ...props }: ImgHTMLAttributes<HTMLImageElement> & { className?: string }) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}${className ? ' ' + className : ''}`} style={{ width: '100%', height: '100%', ...style }}>
      <img {...props} onLoad={() => setLoaded(true)} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
    </div>
  )
}

interface GemmaAnalysis {
  description?: string
  subject?: string
  mood?: string
  story?: string
  lighting?: string
  composition?: string
  colors?: string
  texture?: string
  technical?: string
  strength?: string
  tags?: string[]
  print_worthy?: boolean
  raw?: string
}

interface TopLabel {
  label: string
  category: string
  confidence: number
}

interface GemmaResult {
  uuid: string
  gemma: GemmaAnalysis
  processed_at: string
  camera_body?: string
  film_stock?: string
  medium?: string
  top_labels: TopLabel[]
}

interface GemmaData {
  total: number
  processed: number
  results: GemmaResult[]
}

function Field({ label, value }: { label: string; value?: string }) {
  if (!value) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{
        fontSize: 'var(--text-xs)', textTransform: 'uppercase',
        letterSpacing: '0.08em', color: 'var(--muted)', fontWeight: 500,
      }}>
        {label}
      </span>
      <span style={{ fontSize: 'var(--text-sm)', color: 'var(--fg)', lineHeight: 1.4 }}>
        {value}
      </span>
    </div>
  )
}

function GemmaCard({ result }: { result: GemmaResult }) {
  const g = result.gemma
  const pw = g.print_worthy

  // Build 5 gorgeous pills: camera + top 4 labels
  const pills: { label: string; category: string; primary?: boolean }[] = []

  // Pill 1: Camera (always first if available)
  if (result.camera_body) {
    const cameraLabel = result.film_stock
      ? `${result.camera_body} \u2022 ${result.film_stock}`
      : result.camera_body
    pills.push({ label: cameraLabel, category: 'camera', primary: true })
  }

  // Pills 2-5: Top 4 labels by confidence
  ;(result.top_labels || []).slice(0, 4).forEach(l => {
    pills.push({ label: l.label, category: l.category })
  })

  return (
    <div className="gemma-card">
      <div className="gemma-card-left">
        <div className="gemma-card-img">
          <FadeImg
            src={imageUrl(`/rendered/thumb/jpeg/${result.uuid}.jpg`)}
            alt=""
            loading="lazy"
          />
        </div>

        {/* Gorgeous Pills */}
        {pills.length > 0 && (
          <div className="gemma-pills">
            {pills.map((pill, i) => (
              <span key={i} className={`gorgeous-pill${pill.primary ? ' primary' : ''}`} data-category={pill.category}>
                {pill.label}
              </span>
            ))}
          </div>
        )}

        <div className="gemma-card-meta">
          {g.subject && <span className="gemma-meta-subject">{g.subject}</span>}
          {g.mood && <span className="gemma-meta-mood">{g.mood}</span>}
          {pw !== undefined && (
            <span className={`gemma-badge ${pw ? 'pw' : ''}`}>
              {pw ? 'Print-worthy' : 'Not print-worthy'}
            </span>
          )}
          {g.tags && g.tags.length > 0 && (
            <div className="gemma-tags">
              {g.tags.map(tag => (
                <span key={tag} className="gemma-tag">{tag}</span>
              ))}
            </div>
          )}
          <span className="gemma-card-uuid">{result.uuid.slice(0, 8)}</span>
        </div>
      </div>
      <div className="gemma-card-body">
        {(g.description || g.raw) && (
          <p className="gemma-lead">{g.description || g.raw}</p>
        )}

        {g.story && g.story !== g.description && (
          <p className="gemma-story">{g.story}</p>
        )}

        <div className="gemma-fields">
          <Field label="Lighting" value={g.lighting} />
          <Field label="Composition" value={g.composition} />
          <Field label="Colors" value={g.colors} />
          <Field label="Texture" value={g.texture} />
          <Field label="Technical" value={g.technical} />
          <Field label="Strength" value={g.strength} />
        </div>
      </div>
    </div>
  )
}

export function GemmaPage() {
  const { data, loading, error } = useFetch<GemmaData>('/api/gemma')

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading Gemma analysis...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  const pct = data.total > 0 ? (data.processed / data.total * 100) : 0
  const done = data.processed === data.total && data.total > 0

  return (
    <PageShell title="Gemma Analysis" subtitle="Gemma 3 4B vision analysis of curated picks">
      {/* Progress card */}
      <Card>
        <div style={{
          display: 'flex', alignItems: 'center', gap: '12px',
        }}>
          <div style={{
            flex: 1, height: '4px', background: 'var(--border)',
            borderRadius: '2px', overflow: 'hidden',
          }}>
            <div style={{
              height: '100%', width: `${pct.toFixed(1)}%`,
              background: done ? 'var(--system-green)' : 'var(--system-blue)',
              borderRadius: '2px', transition: 'width 0.6s ease',
            }} />
          </div>
          <span style={{
            fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)',
            color: 'var(--muted)', whiteSpace: 'nowrap',
          }}>
            <strong style={{ color: 'var(--fg)' }}>{data.processed}</strong> / {data.total}
          </span>
        </div>
      </Card>

      {/* Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {data.results.map(r => (
          <GemmaCard key={r.uuid} result={r} />
        ))}
      </div>

      {data.results.length === 0 && (
        <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '60px 20px' }}>
          No Gemma analysis results yet. Run the Gemma pipeline first.
        </p>
      )}
    </PageShell>
  )
}
