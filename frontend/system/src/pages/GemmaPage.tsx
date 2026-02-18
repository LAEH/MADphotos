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
  crop_square?: {
    x: number
    y: number
    size: number
    reason: string
  }
  stories?: {
    silly?: string
    poetic?: string
    surrealist?: string
    noir?: string
    romantic?: string
  }
  cartoon_style?: string
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

        {/* Enhanced stories */}
        {g.stories && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', margin: '16px 0' }}>
            {g.stories.silly && (
              <div style={{ borderLeft: '3px solid var(--system-yellow)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>
                  🤪 SILLY
                </div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.silly}</div>
              </div>
            )}
            {g.stories.poetic && (
              <div style={{ borderLeft: '3px solid var(--system-purple)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>
                  ✨ POETIC
                </div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.poetic}</div>
              </div>
            )}
            {g.stories.surrealist && (
              <div style={{ borderLeft: '3px solid var(--system-pink)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>
                  🌀 SURREALIST
                </div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.surrealist}</div>
              </div>
            )}
            {g.stories.noir && (
              <div style={{ borderLeft: '3px solid var(--muted)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>
                  🕵️ NOIR
                </div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.noir}</div>
              </div>
            )}
            {g.stories.romantic && (
              <div style={{ borderLeft: '3px solid var(--system-red)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>
                  💕 ROMANTIC
                </div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.romantic}</div>
              </div>
            )}
          </div>
        )}

        {/* Crop suggestion */}
        {g.crop_square && (
          <div style={{
            background: 'var(--surface)',
            padding: '12px',
            borderRadius: '8px',
            margin: '12px 0'
          }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)', marginBottom: '6px' }}>
              ✂️ SUGGESTED CROP
            </div>
            <div style={{ fontSize: 'var(--text-sm)', marginBottom: '4px' }}>{g.crop_square.reason}</div>
            <div style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--muted)' }}>
              {g.crop_square.x}%, {g.crop_square.y}% • {g.crop_square.size}%
            </div>
          </div>
        )}

        {/* Cartoon style */}
        {g.cartoon_style && (
          <div style={{
            background: 'var(--surface)',
            padding: '12px',
            borderRadius: '8px',
            margin: '12px 0'
          }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)', marginBottom: '6px' }}>
              🎨 CARTOON TRANSFORMATION
            </div>
            <div style={{ fontSize: 'var(--text-sm)' }}>{g.cartoon_style}</div>
          </div>
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

const GEMMA_PROMPT = `You are an expert photography critic and creative storyteller. Analyze this photograph in detail. Respond ONLY with valid JSON, no markdown, no backticks:
{"description":"2-3 sentence vivid description of what this photograph shows",
"subject":"primary subject(s) of the photograph",
"story":"what moment, narrative, or feeling this image captures",
"composition":"how the frame is arranged — technique, balance, eye flow",
"lighting":"quality, direction, and character of the light",
"colors":"dominant colors and their relationships described naturally",
"texture":"visible textures, materials, surfaces",
"mood":"emotional atmosphere in 2-3 words",
"technical":"assessment of exposure, focus, depth of field, sharpness",
"strength":"what makes this a strong photograph",
"tags":["up to 15 descriptive tags"],
"print_worthy":true or false,
"crop_square":{"x":0-100,"y":0-100,"size":0-100,"reason":"why this crop"},
"crops":{
"1:1":{"center_x":0-100,"center_y":0-100,"coverage":30-90,"reason":"best square crop"},
"2:3":{"center_x":0-100,"center_y":0-100,"coverage":30-90,"reason":"best tall portrait crop"},
"3:2":{"center_x":0-100,"center_y":0-100,"coverage":30-90,"reason":"best wide landscape crop"},
"16:9":{"center_x":0-100,"center_y":0-100,"coverage":30-90,"reason":"best cinematic wide crop"}},
"stories":{
"silly":"fun, childish, playful 1-sentence story",
"poetic":"lyrical, beautiful 1-sentence poetic interpretation",
"surrealist":"dreamlike, absurd 1-sentence surrealist narrative",
"noir":"mysterious, dramatic 1-sentence noir-style description",
"romantic":"tender, emotional 1-sentence romantic interpretation"},
"cartoon_style":"what cartoon/illustration transformation would work best and why"}`

export function GemmaPage() {
  const { data, loading, error } = useFetch<GemmaData>('/api/gemma')

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading Gemma analysis...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  // Filter for enhanced results only (those with stories)
  const enhancedResults = data.results.filter(r =>
    r.gemma.stories?.silly || r.gemma.crop_square || r.gemma.cartoon_style
  )

  return (
    <PageShell title="Gemma" subtitle="gemma3:27b via Ollama (madphotos-critic)">
      {/* Prompt + count card */}
      <Card title="Analysis Prompt">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{
            fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)',
            color: 'var(--muted)', whiteSpace: 'nowrap',
          }}>
            <strong style={{ color: 'var(--fg)' }}>{data.processed}</strong> / {data.total} picks processed
          </div>
          <pre style={{
            fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
            color: 'var(--fg)', background: 'var(--surface)',
            padding: '12px', borderRadius: '6px', overflow: 'auto',
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            lineHeight: 1.5, maxHeight: '300px',
            border: '1px solid var(--border)',
          }}>
            {GEMMA_PROMPT}
          </pre>
        </div>
      </Card>

      {/* Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {enhancedResults.map(r => (
          <GemmaCard key={r.uuid} result={r} />
        ))}
      </div>

      {enhancedResults.length === 0 && (
        <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '60px 20px' }}>
          No enhanced Gemma results yet.
        </p>
      )}
    </PageShell>
  )
}
