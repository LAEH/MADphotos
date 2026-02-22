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
  crop_square?: { x: number; y: number; size: number; reason: string }
  crops?: Record<string, { center_x: number; center_y: number; coverage: number; reason?: string }>
  stories?: {
    silly?: string; poetic?: string; surrealist?: string
    noir?: string; romantic?: string
  }
  cartoon_style?: string
  visual_weight?: number
  energy_direction?: string
  archetype?: string
  color_temp?: string
  setting?: string
  time_of_day?: string
  weather?: string
  grading_style?: string
  exposure_label?: string
  sharpness_label?: string
  vibes?: string[]
  faces_count?: number
  semantic_pops?: { color: string; object: string; impact: string }[]
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
  complete: boolean
}

interface GemmaData {
  total: number
  processed: number
  complete_v2: number
  results: GemmaResult[]
}

/* ── Helpers ────────────────────────────────────────────── */

function Field({ label, value }: { label: string; value?: string }) {
  if (!value) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{
        fontSize: 'var(--text-xs)', textTransform: 'uppercase',
        letterSpacing: '0.08em', color: 'var(--muted)', fontWeight: 500,
      }}>{label}</span>
      <span style={{ fontSize: 'var(--text-sm)', color: 'var(--fg)', lineHeight: 1.4 }}>{value}</span>
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
  setting: '#5856D6', time_of_day: '#FF9500', weather: '#34C759',
  grading_style: '#FF2D55', exposure_label: '#007AFF', sharpness_label: '#5AC8FA',
  archetype: '#AF52DE', energy_direction: '#FF3B30', color_temp: '#FF6B35',
}

/* ── GemmaCard ──────────────────────────────────────────── */

function GemmaCard({ result, isModel }: { result: GemmaResult; isModel?: boolean }) {
  const g = result.gemma
  const pw = g.print_worthy

  const pills: { label: string; category: string; primary?: boolean }[] = []
  if (result.camera_body) {
    const cameraLabel = result.film_stock
      ? `${result.camera_body} \u2022 ${result.film_stock}`
      : result.camera_body
    pills.push({ label: cameraLabel, category: 'camera', primary: true })
  }
  ;(result.top_labels || []).slice(0, 4).forEach(l => {
    pills.push({ label: l.label, category: l.category })
  })

  return (
    <div className="gemma-card" style={isModel ? {
      background: 'linear-gradient(135deg, rgba(88,86,214,0.08), rgba(175,82,222,0.08))',
      border: '2px solid rgba(88,86,214,0.3)',
      position: 'relative',
    } : undefined}>
      {isModel && (
        <div style={{
          position: 'absolute', top: '8px', right: '12px',
          fontSize: 'var(--text-2xs)', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.1em', color: '#5856D6', background: 'rgba(88,86,214,0.12)',
          padding: '3px 10px', borderRadius: '4px',
        }}>All signals</div>
      )}

      <div className="gemma-card-left">
        <div className="gemma-card-img">
          <FadeImg
            src={imageUrl(`/rendered/thumb/jpeg/${result.uuid}.jpg`)}
            alt="" loading="lazy"
          />
        </div>

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
              {g.tags.map(tag => <span key={tag} className="gemma-tag">{tag}</span>)}
            </div>
          )}
          <span className="gemma-card-uuid">{result.uuid.slice(0, 8)}</span>
        </div>
      </div>

      <div className="gemma-card-body">
        {(g.description || g.raw) && (
          <p className="gemma-lead">{g.description || g.raw}</p>
        )}

        {/* Structured labels */}
        {(g.setting || g.time_of_day || g.weather || g.grading_style || g.archetype || g.energy_direction || g.color_temp) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', margin: '12px 0' }}>
            {g.setting && <LabelPill label={`${g.setting}`} color={LABEL_COLORS.setting} />}
            {g.time_of_day && <LabelPill label={`${g.time_of_day}`} color={LABEL_COLORS.time_of_day} />}
            {g.weather && <LabelPill label={`${g.weather}`} color={LABEL_COLORS.weather} />}
            {g.grading_style && <LabelPill label={`${g.grading_style}`} color={LABEL_COLORS.grading_style} />}
            {g.exposure_label && <LabelPill label={`${g.exposure_label}`} color={LABEL_COLORS.exposure_label} />}
            {g.sharpness_label && <LabelPill label={`${g.sharpness_label}`} color={LABEL_COLORS.sharpness_label} />}
            {g.archetype && <LabelPill label={`${g.archetype}`} color={LABEL_COLORS.archetype} />}
            {g.energy_direction && <LabelPill label={`${g.energy_direction}`} color={LABEL_COLORS.energy_direction} />}
            {g.color_temp && <LabelPill label={`${g.color_temp}`} color={LABEL_COLORS.color_temp} />}
          </div>
        )}

        {/* Vibes + weight + faces */}
        {(g.vibes || g.visual_weight || g.faces_count !== undefined) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', margin: '8px 0' }}>
            {g.visual_weight !== undefined && (
              <span style={{
                fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
                color: 'var(--muted)',
              }}>weight {g.visual_weight}/10</span>
            )}
            {g.faces_count !== undefined && g.faces_count > 0 && (
              <span style={{
                fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
                color: 'var(--muted)',
              }}>{g.faces_count} face{g.faces_count !== 1 ? 's' : ''}</span>
            )}
            {g.vibes && g.vibes.length > 0 && g.vibes.map(v => (
              <span key={v} style={{
                fontSize: 'var(--text-xs)', padding: '1px 6px',
                borderRadius: '3px', background: 'rgba(175,82,222,0.1)',
                color: '#AF52DE', fontStyle: 'italic',
              }}>{v}</span>
            ))}
          </div>
        )}

        {/* Semantic pops */}
        {g.semantic_pops && g.semantic_pops.length > 0 && (
          <div style={{ display: 'flex', gap: '8px', margin: '8px 0', flexWrap: 'wrap' }}>
            {g.semantic_pops.map((p, i) => (
              <span key={i} style={{
                fontSize: 'var(--text-xs)', padding: '2px 8px',
                borderRadius: '4px', border: '1px solid var(--border)',
                color: 'var(--fg)',
              }}>
                <strong>{p.color}</strong> {p.object} <span style={{ color: 'var(--muted)' }}>({p.impact})</span>
              </span>
            ))}
          </div>
        )}

        {/* Stories */}
        {g.stories && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', margin: '16px 0' }}>
            {g.stories.silly && (
              <div style={{ borderLeft: '3px solid var(--system-yellow)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>SILLY</div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.silly}</div>
              </div>
            )}
            {g.stories.poetic && (
              <div style={{ borderLeft: '3px solid var(--system-purple)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>POETIC</div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.poetic}</div>
              </div>
            )}
            {g.stories.surrealist && (
              <div style={{ borderLeft: '3px solid var(--system-pink)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>SURREALIST</div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.surrealist}</div>
              </div>
            )}
            {g.stories.noir && (
              <div style={{ borderLeft: '3px solid var(--muted)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>NOIR</div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.noir}</div>
              </div>
            )}
            {g.stories.romantic && (
              <div style={{ borderLeft: '3px solid var(--system-red)', paddingLeft: '12px' }}>
                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '4px' }}>ROMANTIC</div>
                <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic' }}>{g.stories.romantic}</div>
              </div>
            )}
          </div>
        )}

        {/* Crops */}
        {g.crops && Object.keys(g.crops).length > 0 && (
          <div style={{
            background: 'var(--surface)', padding: '12px', borderRadius: '8px', margin: '12px 0',
          }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px' }}>
              CROP SUGGESTIONS
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '8px' }}>
              {Object.entries(g.crops).map(([ratio, crop]) => (
                <div key={ratio} style={{
                  fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
                  padding: '6px 8px', borderRadius: '4px', border: '1px solid var(--border)',
                }}>
                  <strong>{ratio}</strong> {crop.center_x},{crop.center_y} @ {crop.coverage}%
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Cartoon style */}
        {g.cartoon_style && (
          <div style={{
            background: 'var(--surface)', padding: '12px', borderRadius: '8px', margin: '12px 0',
          }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--muted)', marginBottom: '6px' }}>
              CARTOON TRANSFORMATION
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

/* ── Prompts ────────────────────────────────────────────── */

const SYSTEM_PROMPT = `You are an expert photography critic and creative storyteller. Analyze photographs in detail and respond with ONLY valid JSON.

Required fields:
{"description":"2-3 sentence vivid description of what this photograph shows",
"subject":"primary subject(s) of the photograph",
"story":"what moment, narrative, or feeling this image captures",
"composition":"how the frame is arranged - technique, balance, eye flow",
"lighting":"quality, direction, and character of the light",
"colors":"dominant colors and their relationships described naturally",
"texture":"visible textures, materials, surfaces",
"mood":"emotional atmosphere in 2-3 words",
"technical":"assessment of exposure, focus, depth of field, sharpness",
"strength":"what makes this a strong photograph",
"tags":["up to 15 descriptive tags"],
"print_worthy":true or false,
"crops":{...aspect ratio crops...},
"stories":{
  "silly":"fun playful 1-sentence story",
  "poetic":"lyrical beautiful 1-sentence interpretation",
  "surrealist":"dreamlike absurd 1-sentence narrative",
  "noir":"mysterious dramatic 1-sentence description",
  "romantic":"tender emotional 1-sentence interpretation"},
"cartoon_style":"what cartoon/illustration transformation would work best and why",
"visual_weight":1-10,
"energy_direction":"dominant visual flow direction",
"archetype":"compositional category",
"color_temp":"overall temperature feeling",
"setting":"interior|exterior|mixed",
"time_of_day":"dawn|morning|midday|golden_hour|blue_hour|night",
"weather":"clear|sunny|overcast|cloudy|rainy|foggy|snowy|stormy|indoors",
"grading_style":"cinematic|natural|monochrome|pastel|high_contrast|cross_processed|matte|vintage",
"exposure_label":"balanced|under|over",
"sharpness_label":"sharp|soft|motion_blur",
"vibes":["3-5 single-word mood/atmosphere tags"],
"faces_count":integer,
"semantic_pops":[{"color":"dominant color name","object":"what it is","impact":"high|medium|low"}]}

Rules:
- Output ONLY valid JSON, nothing else
- tags must be lowercase
- For crops: use center_x, center_y (0-100) and coverage (30-90)
- For stories: write SHORT punchy 1-sentence narratives
- print_worthy must be boolean true or false
- vibes must be an array of 3-5 single lowercase words
- faces_count must be an integer (0 if no faces visible)
- semantic_pops: 1-3 visually striking elements that pop`

const USER_PROMPT = `Analyze this photograph. Respond ONLY with valid JSON.

Crop ratios for landscape: 1:1, 2:1, 3:2, 4:3
Crop ratios for portrait:  1:1, 1:2, 2:3, 3:4

For crops: center_x/center_y = center of crop region (0-100), coverage = percentage of image to include (30-90).
visual_weight: 1=airy/minimal, 10=dense/heavy.
energy_direction: left_to_right|right_to_left|up|down|center_out|inward|diagonal_down|diagonal_up|static
archetype: portal|horizon|texture|figure|geometry|void|cluster|reflection|silhouette|panorama
color_temp: glacial|cool|neutral|warm|molten|electric|neon|muted|monochrome`

const EXAMPLE_RESULT = `{
  "description": "This photograph captures a sun-drenched beach scene with people lounging and swimming in clear turquoise water. A pale yellow building stands prominently on the right, overlooking the activity.",
  "subject": "people, beach, building",
  "story": "A perfect summer day unfolds as sunbathers and swimmers enjoy the Mediterranean warmth.",
  "composition": "Wide angle establishing sense of place. Building on right acts as visual anchor, water line leads eye across frame.",
  "lighting": "Bright direct midday sun, creating strong highlights and shadows. Clear day with light reflecting off water.",
  "colors": "Turquoise water, pale yellow building, warm beige sand. Harmonious and inviting palette.",
  "texture": "Grainy sand, rough stone beach, smooth water, stucco building.",
  "mood": "relaxed, peaceful, warm",
  "technical": "Well-balanced exposure, sharp focus throughout, moderate depth of field.",
  "strength": "Conveys sense of place and atmosphere through composition, lighting, and color harmony.",
  "tags": ["beach", "summer", "mediterranean", "coast", "sunbathing", "swimming", "building", "leisure", "travel", "europe", "sea", "sunshine", "holiday"],
  "print_worthy": true,
  "crops": {
    "1:1": { "center_x": 50, "center_y": 50, "coverage": 60 },
    "2:1": { "center_x": 50, "center_y": 50, "coverage": 80 },
    "3:2": { "center_x": 50, "center_y": 40, "coverage": 80 },
    "4:3": { "center_x": 40, "center_y": 50, "coverage": 75 }
  },
  "stories": {
    "silly": "A rogue beach ball bounced right into someone's sunbathing session!",
    "poetic": "Golden light kisses the shore, whispering tales of summer days and salty air.",
    "surrealist": "The building breathed with the rhythm of waves, a silent guardian of sun-soaked dreams.",
    "noir": "Shadows stretched long across the sand, hinting at secrets beneath the surface of paradise.",
    "romantic": "Sun-warmed skin and the sound of waves create a perfect moment of connection."
  },
  "cartoon_style": "Watercolor illustration emphasizing soft colors and relaxed atmosphere.",
  "visual_weight": 7,
  "energy_direction": "right_to_left",
  "archetype": "panorama",
  "color_temp": "warm",
  "setting": "exterior",
  "time_of_day": "midday",
  "weather": "sunny",
  "grading_style": "natural",
  "exposure_label": "balanced",
  "sharpness_label": "sharp",
  "vibes": ["calm", "serene", "sunny", "peaceful", "warm"],
  "faces_count": 11,
  "semantic_pops": [
    { "color": "turquoise", "object": "water", "impact": "high" },
    { "color": "yellow", "object": "building", "impact": "medium" },
    { "color": "beige", "object": "sand", "impact": "medium" }
  ]
}`

/* ── Page ───────────────────────────────────────────────── */

export function GemmaPage() {
  const { data, loading, error } = useFetch<GemmaData>('/api/gemma')

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading Gemma analysis...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  // Sort: complete v2 first, then by processed_at desc
  const sorted = [...data.results].sort((a, b) => {
    if (a.complete && !b.complete) return -1
    if (!a.complete && b.complete) return 1
    return b.processed_at.localeCompare(a.processed_at)
  })

  const v2Count = data.complete_v2 ?? sorted.filter(r => r.complete).length

  return (
    <PageShell title="Gemma" subtitle="gemma3:27b via Ollama (madphotos-critic)">

      {/* Stats bar */}
      <div style={{
        display: 'flex', gap: '24px', padding: '12px 16px',
        background: 'var(--surface)', borderRadius: '10px',
        marginBottom: '16px', fontSize: 'var(--text-sm)',
        fontFamily: 'var(--font-mono)',
      }}>
        <span><strong style={{ color: 'var(--fg)' }}>{data.processed}</strong> <span style={{ color: 'var(--muted)' }}>/ {data.total} processed</span></span>
        <span><strong style={{ color: '#5856D6' }}>{v2Count}</strong> <span style={{ color: 'var(--muted)' }}>complete (v2 labels)</span></span>
        <span><strong style={{ color: 'var(--muted)' }}>{data.total - data.processed}</strong> <span style={{ color: 'var(--muted)' }}>pending</span></span>
      </div>

      {/* Collapsible: System Prompt */}
      <Collapsible title={`System Prompt — baked into madphotos-critic Modelfile (${SYSTEM_PROMPT.split('\n').length} lines)`}>
        <pre style={{
          fontSize: '11px', fontFamily: 'var(--font-mono)',
          color: 'var(--fg)', background: 'var(--bg)',
          padding: '16px', borderRadius: '8px', overflow: 'auto',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          lineHeight: 1.5, border: '1px solid var(--border)',
        }}>{SYSTEM_PROMPT}</pre>
      </Collapsible>

      {/* Collapsible: User Prompt */}
      <Collapsible title="User Prompt — sent per image with orientation-specific crop ratios">
        <pre style={{
          fontSize: '11px', fontFamily: 'var(--font-mono)',
          color: 'var(--fg)', background: 'var(--bg)',
          padding: '16px', borderRadius: '8px', overflow: 'auto',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          lineHeight: 1.5, border: '1px solid var(--border)',
        }}>{USER_PROMPT}</pre>
      </Collapsible>

      {/* Collapsible: Example Result */}
      <Collapsible title="Example Result — complete v2 output with all 30+ fields">
        <pre style={{
          fontSize: '11px', fontFamily: 'var(--font-mono)',
          color: 'var(--fg)', background: 'var(--bg)',
          padding: '16px', borderRadius: '8px', overflow: 'auto',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          lineHeight: 1.5, border: '1px solid var(--border)',
        }}>{EXAMPLE_RESULT}</pre>
      </Collapsible>

      {/* Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {sorted.map((r, i) => (
          <GemmaCard key={r.uuid} result={r} isModel={i === 0 && r.complete} />
        ))}
      </div>

      {sorted.length === 0 && (
        <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '60px 20px' }}>
          No Gemma results yet.
        </p>
      )}
    </PageShell>
  )
}
