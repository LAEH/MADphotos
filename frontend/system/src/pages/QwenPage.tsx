import { useState, type ImgHTMLAttributes } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { PageShell } from '../components/layout/PageShell'

function FadeImg({ style, className, ...props }: ImgHTMLAttributes<HTMLImageElement> & { className?: string }) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}${className ? ' ' + className : ''}`} style={{ width: '100%', height: '100%', ...style }}>
      <img {...props} onLoad={() => setLoaded(true)} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
    </div>
  )
}

interface QwenAnalysis {
  alt_text?: string
  people_count?: number
  objects_inventory?: { object: string; count: number; prominence: string }[]
  focal_point?: { x: number; y: number; strength: number; what: string }
  spatial_layers?: { foreground: string; midground: string; background: string }
  relationships?: { subject: string; relation: string; object: string }[]
  text_present?: boolean
  text_content?: string
  text_type?: string
  bokeh_quality?: string
  focus_description?: string
  motion_blur?: string
  noise_grain?: string
  symmetry?: { type: string; strength: number }
  leading_lines?: boolean
  repetition_pattern?: boolean
  environmental_order?: number
  era_feeling?: string
  narrative_tension?: string
  crops?: Record<string, { center_x: number; center_y: number; coverage: number }>
  variant_prompts?: { style: string; prompt: string; mood: string; color_palette?: string }[]
  raw?: string
}

interface QwenResult {
  uuid: string
  qwen: QwenAnalysis
  processed_at: string
  orientation: string
}

interface QwenData {
  total: number
  processed: number
  results: QwenResult[]
}

/* ── Helpers ────────────────────────────────────────────── */

/** Safe array coercion — protects against model returning wrong types */
function safeArray<T>(val: unknown): T[] {
  return Array.isArray(val) ? val : []
}

function safeObj<T>(val: unknown): T | null {
  return (val && typeof val === 'object' && !Array.isArray(val)) ? val as T : null
}

function Field({ label, value }: { label: string; value?: string | number }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{
        fontSize: 'var(--text-xs)', textTransform: 'uppercase',
        letterSpacing: '0.08em', color: 'var(--muted)', fontWeight: 500,
      }}>{label}</span>
      <span style={{ fontSize: 'var(--text-sm)', color: 'var(--fg)', lineHeight: 1.4 }}>{String(value)}</span>
    </div>
  )
}

function LabelPill({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: '4px',
      fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
      background: color, color: '#fff', fontWeight: 500,
    }}>{label}</span>
  )
}

function Collapsible({ title, defaultOpen, children }: {
  title: string; defaultOpen?: boolean; children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen ?? false)
  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: '10px',
      overflow: 'hidden', marginBottom: '16px',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
          padding: '12px 16px', background: 'var(--surface)', border: 'none',
          cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600,
          color: 'var(--fg)', textAlign: 'left',
        }}
      >
        <span style={{
          transition: 'transform 150ms', transform: open ? 'rotate(90deg)' : 'none',
          fontSize: '12px',
        }}>&#9654;</span>
        {title}
      </button>
      {open && (
        <div style={{ padding: '16px', borderTop: '1px solid var(--border)' }}>
          {children}
        </div>
      )}
    </div>
  )
}

/* ── Label colors ───────────────────────────────────────── */

const LABEL_COLORS: Record<string, string> = {
  bokeh: '#5856D6',
  motion: '#FF9500',
  grain: '#34C759',
  era: '#FF2D55',
  order: '#007AFF',
  symmetry: '#AF52DE',
  text: '#FF6B35',
}

/* ── QwenCard ──────────────────────────────────────────── */

function QwenCard({ result }: { result: QwenResult }) {
  const raw = result.qwen
  // Sanitize: coerce all array/object fields to safe types
  const q = {
    ...raw,
    objects_inventory: safeArray<{ object: string; count: number; prominence: string }>(raw.objects_inventory),
    relationships: safeArray<{ subject: string; relation: string; object: string }>(raw.relationships),
    variant_prompts: safeArray<{ style: string; prompt: string; mood: string; color_palette?: string }>(raw.variant_prompts),
    focal_point: safeObj<{ x: number; y: number; strength: number; what: string }>(raw.focal_point),
    spatial_layers: safeObj<{ foreground: string; midground: string; background: string }>(raw.spatial_layers),
    symmetry: safeObj<{ type: string; strength: number }>(raw.symmetry),
    crops: (raw.crops && typeof raw.crops === 'object' && !Array.isArray(raw.crops)) ? raw.crops as Record<string, { center_x: number; center_y: number; coverage: number }> : null,
  }

  return (
    <div className="gemma-card">
      <div className="gemma-card-left">
        <div className="gemma-card-img">
          <FadeImg
            src={imageUrl(`/rendered/thumb/jpeg/${result.uuid}.jpg`)}
            alt={q.alt_text || ''} loading="lazy"
          />
        </div>

        <div className="gemma-card-meta">
          {q.alt_text && <span className="gemma-meta-subject">{q.alt_text}</span>}

          {/* People + objects summary */}
          {q.people_count !== undefined && (
            <span className="gemma-meta-mood">
              {q.people_count} {q.people_count === 1 ? 'person' : 'people'}
            </span>
          )}

          {/* Structured pills */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px' }}>
            {q.bokeh_quality && q.bokeh_quality !== 'absent' && q.bokeh_quality !== 'na' && (
              <LabelPill label={`bokeh: ${q.bokeh_quality}`} color={LABEL_COLORS.bokeh} />
            )}
            {q.motion_blur && q.motion_blur !== 'none' && (
              <LabelPill label={`motion: ${q.motion_blur}`} color={LABEL_COLORS.motion} />
            )}
            {q.noise_grain && q.noise_grain !== 'clean' && (
              <LabelPill label={q.noise_grain} color={LABEL_COLORS.grain} />
            )}
            {q.era_feeling && (
              <LabelPill label={q.era_feeling} color={LABEL_COLORS.era} />
            )}
            {q.text_present && (
              <LabelPill label={`text: ${q.text_type || 'yes'}`} color={LABEL_COLORS.text} />
            )}
          </div>

          {/* Symmetry + order */}
          <div style={{ display: 'flex', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
            {q.symmetry?.type && q.symmetry.type !== 'none' && (
              <span style={{
                fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--muted)',
              }}>{q.symmetry.type} symmetry {q.symmetry.strength}/10</span>
            )}
            {q.environmental_order !== undefined && q.environmental_order !== null && (
              <span style={{
                fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--muted)',
              }}>order {q.environmental_order}/10</span>
            )}
          </div>

          {q.leading_lines && (
            <span style={{ fontSize: 'var(--text-xs)', color: '#007AFF' }}>Leading lines</span>
          )}
          {q.repetition_pattern && (
            <span style={{ fontSize: 'var(--text-xs)', color: '#5856D6' }}>Repetition pattern</span>
          )}

          <span className="gemma-card-uuid">{result.uuid.slice(0, 8)} / {result.orientation}</span>
        </div>
      </div>

      <div className="gemma-card-body">
        {/* Narrative tension */}
        {q.narrative_tension && (
          <p className="gemma-lead">{q.narrative_tension}</p>
        )}

        {/* Focus */}
        {q.focus_description && (
          <Field label="Focus" value={q.focus_description} />
        )}

        {/* Text content */}
        {q.text_present && q.text_content && (
          <div style={{
            background: 'var(--surface)', padding: '10px 14px', borderRadius: '8px',
            fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)',
          }}>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', fontWeight: 600 }}>
              TEXT ({q.text_type})
            </span>
            <div style={{ marginTop: '4px' }}>{q.text_content}</div>
          </div>
        )}

        {/* Focal point */}
        {q.focal_point && (
          <div style={{
            background: 'var(--surface)', padding: '10px 14px', borderRadius: '8px',
          }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)', marginBottom: '6px' }}>
              FOCAL POINT
            </div>
            <div style={{ fontSize: 'var(--text-sm)' }}>
              <strong>{q.focal_point.what}</strong>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--muted)', marginLeft: '8px' }}>
                ({q.focal_point.x}, {q.focal_point.y}) strength {q.focal_point.strength}/10
              </span>
            </div>
          </div>
        )}

        {/* Spatial layers */}
        {q.spatial_layers && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)' }}>SPATIAL LAYERS</div>
            <div style={{ borderLeft: '3px solid #34C759', paddingLeft: '12px' }}>
              <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600 }}>FG</div>
              <div style={{ fontSize: 'var(--text-sm)' }}>{q.spatial_layers.foreground}</div>
            </div>
            <div style={{ borderLeft: '3px solid #FF9500', paddingLeft: '12px' }}>
              <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600 }}>MID</div>
              <div style={{ fontSize: 'var(--text-sm)' }}>{q.spatial_layers.midground}</div>
            </div>
            <div style={{ borderLeft: '3px solid #5856D6', paddingLeft: '12px' }}>
              <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600 }}>BG</div>
              <div style={{ fontSize: 'var(--text-sm)' }}>{q.spatial_layers.background}</div>
            </div>
          </div>
        )}

        {/* Objects inventory */}
        {q.objects_inventory.length > 0 && (
          <div>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)', marginBottom: '6px' }}>
              OBJECTS
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {q.objects_inventory.map((obj, i) => (
                <span key={i} style={{
                  fontSize: 'var(--text-xs)', padding: '3px 10px',
                  borderRadius: '4px', border: '1px solid var(--border)',
                  color: 'var(--fg)', background: obj.prominence === 'high'
                    ? 'rgba(52,199,89,0.1)' : obj.prominence === 'medium'
                    ? 'rgba(255,149,0,0.08)' : 'transparent',
                }}>
                  {obj.object} {obj.count > 1 ? `x${obj.count}` : ''}
                  <span style={{ color: 'var(--muted)', marginLeft: '4px' }}>{obj.prominence}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Relationships */}
        {q.relationships.length > 0 && (
          <div>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)', marginBottom: '6px' }}>
              RELATIONSHIPS
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {q.relationships.map((rel, i) => (
                <div key={i} style={{
                  fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)',
                }}>
                  <strong>{rel.subject}</strong>
                  <span style={{ color: '#AF52DE', margin: '0 6px' }}>{rel.relation}</span>
                  <strong>{rel.object}</strong>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Variant prompts */}
        {q.variant_prompts.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)' }}>
              VARIANT DREAMS ({q.variant_prompts.length})
            </div>
            {q.variant_prompts.map((v, i) => {
              const colors = ['#FF2D55', '#5856D6', '#FF9500', '#34C759', '#007AFF']
              return (
                <div key={i} style={{
                  borderLeft: `3px solid ${colors[i % 5]}`,
                  paddingLeft: '12px',
                }}>
                  <div style={{
                    display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '4px', flexWrap: 'wrap',
                  }}>
                    <span style={{
                      fontSize: 'var(--text-xs)', fontWeight: 700,
                      textTransform: 'uppercase', letterSpacing: '0.05em',
                      color: colors[i % 5],
                    }}>{v.style}</span>
                    {v.mood && (
                      <span style={{
                        fontSize: 'var(--text-xs)', fontStyle: 'italic',
                        color: 'var(--muted)',
                      }}>{v.mood}</span>
                    )}
                    {v.color_palette && (
                      <span style={{
                        fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
                        color: 'var(--muted)', opacity: 0.7,
                      }}>{v.color_palette}</span>
                    )}
                  </div>
                  <div style={{ fontSize: 'var(--text-sm)', lineHeight: 1.5 }}>{v.prompt}</div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Prompt display ─────────────────────────────────────── */

const PROMPT_SUMMARY = `Single JSON prompt per image requesting:
- Spatial: alt_text, focal_point (x,y,strength), spatial_layers (fg/mid/bg), relationships (S-R-O triples)
- Inventory: objects_inventory (name, count, prominence), people_count
- Text detection: text_present, text_content, text_type
- Technical: bokeh_quality, focus_description, motion_blur, noise_grain
- Composition: symmetry (type, strength), leading_lines, repetition_pattern, environmental_order
- Feeling: era_feeling, narrative_tension
- Variants: 5 wildly different creative image generation prompts (style, 2-3 sentence prompt, mood, color_palette)
  Must preserve exact composition/layout — same subjects, same positions, only style changes.
  Styles: oil painting, watercolor, cyberpunk, film noir, anime, ukiyo-e, art deco, impressionist,
  infrared, double exposure, paper cutout, stained glass, pixel art, vaporwave, gothic,
  soviet poster, kodachrome, daguerreotype, risograph, botanical, blueprint, embroidery, cave painting, pop art, isometric 3D

Ollama settings: temperature 0.4, num_predict 3000, format json`

/* ── Page ───────────────────────────────────────────────── */

export function QwenPage() {
  const { data, loading, error } = useFetch<QwenData>('/api/qwen')
  const [visible, setVisible] = useState(60)

  if (loading) return <PageShell title="Qwen" subtitle="Loading..."><div style={{ color: 'var(--muted)', padding: '40px', textAlign: 'center' }}>Loading Qwen analysis...</div></PageShell>
  if (error) return <PageShell title="Qwen" subtitle="Error"><div style={{ color: 'var(--system-red)', padding: '40px' }}>Error: {error}</div></PageShell>
  if (!data) return null

  const sorted = [...data.results].sort((a, b) =>
    b.processed_at.localeCompare(a.processed_at)
  )

  // Stats
  const withVariants = sorted.filter(r => Array.isArray(r.qwen.variant_prompts) && r.qwen.variant_prompts.length > 0).length
  const withText = sorted.filter(r => r.qwen.text_present).length
  const avgPeople = sorted.length > 0
    ? (sorted.reduce((sum, r) => sum + (r.qwen.people_count || 0), 0) / sorted.length).toFixed(1)
    : '0'

  const shown = sorted.slice(0, visible)

  return (
    <PageShell title="Qwen" subtitle="qwen2.5vl:7b via Ollama — spatial + inventory + variants">

      {/* Stats bar */}
      <div style={{
        display: 'flex', gap: '24px', padding: '12px 16px',
        background: 'var(--surface)', borderRadius: '10px',
        marginBottom: '16px', fontSize: 'var(--text-sm)',
        fontFamily: 'var(--font-mono)', flexWrap: 'wrap',
      }}>
        <span><strong style={{ color: 'var(--fg)' }}>{data.processed}</strong> <span style={{ color: 'var(--muted)' }}>/ {data.total} processed</span></span>
        <span><strong style={{ color: '#FF2D55' }}>{withVariants}</strong> <span style={{ color: 'var(--muted)' }}>with variants</span></span>
        <span><strong style={{ color: '#FF6B35' }}>{withText}</strong> <span style={{ color: 'var(--muted)' }}>with text</span></span>
        <span><strong style={{ color: 'var(--muted)' }}>{avgPeople}</strong> <span style={{ color: 'var(--muted)' }}>avg people</span></span>
      </div>

      {/* Collapsible: Prompt */}
      <Collapsible title="Prompt design — spatial precision, crops, variant dreams">
        <pre style={{
          fontSize: '11px', fontFamily: 'var(--font-mono)',
          color: 'var(--fg)', background: 'var(--bg)',
          padding: '16px', borderRadius: '8px', overflow: 'auto',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          lineHeight: 1.5, border: '1px solid var(--border)',
        }}>{PROMPT_SUMMARY}</pre>
      </Collapsible>

      {/* Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {shown.map(r => (
          <QwenCard key={r.uuid} result={r} />
        ))}
      </div>

      {visible < sorted.length ? (
        <button
          onClick={() => setVisible(v => v + 60)}
          style={{
            display: 'block', margin: '24px auto', padding: '10px 32px',
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: '8px', color: 'var(--fg)', cursor: 'pointer',
            fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)',
          }}
        >
          Load more ({sorted.length - visible} remaining)
        </button>
      ) : sorted.length === 0 ? (
        <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '60px 20px' }}>
          No Qwen results yet. Run: python3 backend/image_signals/run_qwen_analysis.py --limit 100 --workers 4
        </p>
      ) : null}
    </PageShell>
  )
}
