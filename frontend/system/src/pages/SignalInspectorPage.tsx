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

interface SignalImage {
  uuid: string
  thumb: string
  display: string
  camera: string
  film: string
  category: string
  subcategory: string
  w: number
  h: number
  gemini_alt?: string
  grading?: string
  time?: string
  setting?: string
  exposure?: string
  composition?: string
  weather?: string
  gemini_sharpness?: string
  vibes?: string[]
  scene?: string
  environment?: string
  style?: string
  aesthetic?: number
  aesthetic_v2?: { topiq: number; musiq: number; laion: number; composite: number }
  quality?: { technical: number; clip: number; combined: number }
  hashes?: { blur: number; sharpness: number; edge_density: number; entropy: number }
  colors?: { hex: string; pct: number; name: string }[]
  depth?: { near: number; mid: number; far: number }
  saliency?: { peak_x: number; peak_y: number; spread: number; center_bias: number }
  objects?: { label: string; conf: number }[]
  open_objects?: { label: string; conf: number }[]
  faces?: { conf: number; area: number; emotion: string }[]
  identities?: string[]
  ocr?: string[]
  poses?: number
  foreground?: { fg_pct: number; bg_pct: number }
  segments?: { count: number; largest_pct: number }
  blip_caption?: string
  florence?: { short: string; detailed: string }
  clip_tags?: string[]
  exif?: { focal: number; aperture: number; shutter: string; iso: number; make: string; model: string; lens: string; date: string }
  analysis?: { brightness: number; dynamic_range: number; noise: number; color_temp: number }
  location?: { name: string; lat: number; lon: number }
  gemma?: {
    description?: string
    mood?: string
    tags?: string[]
    stories?: { silly?: string; poetic?: string; surrealist?: string; noir?: string; romantic?: string }
    crop_square?: { x: number; y: number; size: number; reason: string }
    crops?: Record<string, { center_x: number; center_y: number; coverage: number; reason: string }>
    cartoon_style?: string
  }
}

interface SignalData {
  sample_size: number
  total_picks: number
  images: SignalImage[]
}

const sectionStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: '8px',
  padding: '12px 0', borderTop: '1px solid var(--border)',
}

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 'var(--text-xs)', textTransform: 'uppercase',
  letterSpacing: '0.08em', color: 'var(--muted)', fontWeight: 600,
}

const fieldRowStyle: React.CSSProperties = {
  display: 'flex', flexWrap: 'wrap', gap: '12px 20px',
}

function Field({ label, value }: { label: string; value?: string | number }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: '120px' }}>
      <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 500 }}>{label}</span>
      <span style={{ fontSize: 'var(--text-sm)', color: 'var(--fg)', lineHeight: 1.4 }}>{value}</span>
    </div>
  )
}

function DetectionPills({ items }: { items: { label: string; conf: number }[] }) {
  if (!items?.length) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
      {items.map((d, i) => (
        <span key={i} style={{
          fontSize: 'var(--text-xs)', padding: '2px 8px', borderRadius: '10px',
          background: 'var(--surface)', color: 'var(--fg)', border: '1px solid var(--border)',
        }}>
          {d.label} <span style={{ color: 'var(--muted)' }}>{(d.conf * 100).toFixed(0)}%</span>
        </span>
      ))}
    </div>
  )
}

function ColorSwatches({ colors }: { colors: { hex: string; pct: number; name: string }[] }) {
  if (!colors?.length) return null
  return (
    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
      {colors.map((c, i) => (
        <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
          <div style={{
            width: '28px', height: '28px', borderRadius: '4px',
            background: c.hex, border: '1px solid var(--border)',
          }} />
          <span style={{ fontSize: '9px', color: 'var(--muted)' }}>{c.pct}%</span>
        </div>
      ))}
    </div>
  )
}

function StoryBlock({ label, color, text }: { label: string; color: string; text: string }) {
  return (
    <div style={{ borderLeft: `3px solid ${color}`, paddingLeft: '10px' }}>
      <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)', fontWeight: 600, marginBottom: '2px' }}>{label}</div>
      <div style={{ fontSize: 'var(--text-sm)', fontStyle: 'italic', lineHeight: 1.4 }}>{text}</div>
    </div>
  )
}

function SignalCard({ img }: { img: SignalImage }) {
  return (
    <div className="gemma-card">
      {/* Left column: image + meta (same as GemmaCard) */}
      <div className="gemma-card-left">
        <div className="gemma-card-img">
          <FadeImg
            src={imageUrl(img.thumb)}
            alt=""
            loading="lazy"
          />
        </div>

        <div className="gemma-card-meta">
          {img.camera && (
            <span className="gemma-meta-subject">
              {img.camera}{img.film ? ` \u2022 ${img.film}` : ''}
            </span>
          )}
          <span className="gemma-meta-mood">
            {img.w}\u00d7{img.h} {img.category && `\u2022 ${img.category}`}
          </span>

          {/* Color swatches */}
          <ColorSwatches colors={img.colors || []} />

          {/* Vibes */}
          {img.vibes && img.vibes.length > 0 && (
            <div className="gemma-tags">
              {img.vibes.map(v => (
                <span key={v} className="gemma-tag">{v}</span>
              ))}
            </div>
          )}

          {/* CLIP tags */}
          {img.clip_tags && img.clip_tags.length > 0 && (
            <div className="gemma-tags">
              {img.clip_tags.map(t => (
                <span key={t} className="gemma-tag">{t}</span>
              ))}
            </div>
          )}

          <span className="gemma-card-uuid">{img.uuid.slice(0, 8)}</span>
        </div>
      </div>

      {/* Right column: all signal content */}
      <div className="gemma-card-body">

        {/* Captions */}
        {(img.gemini_alt || img.blip_caption || img.florence) && (
          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>Captions</div>
            <Field label="Gemini Alt" value={img.gemini_alt} />
            <Field label="BLIP" value={img.blip_caption} />
            {img.florence && <Field label="Florence Short" value={img.florence.short} />}
            {img.florence && <Field label="Florence Detailed" value={img.florence.detailed} />}
          </div>
        )}

        {/* Gemma */}
        {img.gemma && (
          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>Gemma</div>
            <Field label="Description" value={img.gemma.description} />
            <Field label="Mood" value={img.gemma.mood} />
            {img.gemma.stories && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
                {img.gemma.stories.silly && <StoryBlock label="SILLY" color="var(--system-yellow)" text={img.gemma.stories.silly} />}
                {img.gemma.stories.poetic && <StoryBlock label="POETIC" color="var(--system-purple)" text={img.gemma.stories.poetic} />}
                {img.gemma.stories.surrealist && <StoryBlock label="SURREALIST" color="var(--system-pink)" text={img.gemma.stories.surrealist} />}
                {img.gemma.stories.noir && <StoryBlock label="NOIR" color="var(--muted)" text={img.gemma.stories.noir} />}
                {img.gemma.stories.romantic && <StoryBlock label="ROMANTIC" color="var(--system-red)" text={img.gemma.stories.romantic} />}
              </div>
            )}
            {img.gemma.crop_square && (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
                Crop: {img.gemma.crop_square.x}%, {img.gemma.crop_square.y}% &bull; {img.gemma.crop_square.size}% &mdash; {img.gemma.crop_square.reason}
              </div>
            )}
            {img.gemma.cartoon_style && <Field label="Cartoon Style" value={img.gemma.cartoon_style} />}
            {img.gemma.tags && img.gemma.tags.length > 0 && (
              <div className="gemma-tags">
                {img.gemma.tags.map(t => (
                  <span key={t} className="gemma-tag">{t}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Scores */}
        <div style={sectionStyle}>
          <div style={sectionTitleStyle}>Scores</div>
          <div style={fieldRowStyle}>
            <Field label="Aesthetic v1" value={img.aesthetic} />
            {img.aesthetic_v2 && <>
              <Field label="TOPIQ" value={img.aesthetic_v2.topiq} />
              <Field label="MUSIQ" value={img.aesthetic_v2.musiq} />
              <Field label="LAION" value={img.aesthetic_v2.laion} />
              <Field label="Composite" value={img.aesthetic_v2.composite} />
            </>}
            {img.quality && <>
              <Field label="Technical" value={img.quality.technical} />
              <Field label="CLIP Score" value={img.quality.clip} />
              <Field label="Combined" value={img.quality.combined} />
            </>}
          </div>
          {img.hashes && (
            <div style={fieldRowStyle}>
              <Field label="Blur" value={img.hashes.blur} />
              <Field label="Sharpness" value={img.hashes.sharpness} />
              <Field label="Edge Density" value={img.hashes.edge_density} />
              <Field label="Entropy" value={img.hashes.entropy} />
            </div>
          )}
        </div>

        {/* Vision */}
        <div style={sectionStyle}>
          <div style={sectionTitleStyle}>Vision</div>
          <div style={fieldRowStyle}>
            <Field label="Scene" value={img.scene} />
            <Field label="Style" value={img.style} />
            <Field label="Environment" value={img.environment} />
          </div>
          {img.depth && (
            <div style={fieldRowStyle}>
              <Field label="Depth Near" value={`${img.depth.near}%`} />
              <Field label="Depth Mid" value={`${img.depth.mid}%`} />
              <Field label="Depth Far" value={`${img.depth.far}%`} />
            </div>
          )}
          {img.saliency && (
            <div style={fieldRowStyle}>
              <Field label="Saliency Peak" value={`${img.saliency.peak_x}, ${img.saliency.peak_y}`} />
              <Field label="Spread" value={img.saliency.spread} />
              <Field label="Center Bias" value={img.saliency.center_bias} />
            </div>
          )}
        </div>

        {/* Detections */}
        {(img.objects?.length || img.open_objects?.length || img.faces?.length || img.ocr?.length || img.poses) ? (
          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>Detections</div>
            {img.objects && img.objects.length > 0 && (
              <div>
                <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)' }}>YOLO</span>
                <DetectionPills items={img.objects} />
              </div>
            )}
            {img.open_objects && img.open_objects.length > 0 && (
              <div>
                <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--muted)' }}>Grounding DINO</span>
                <DetectionPills items={img.open_objects} />
              </div>
            )}
            {img.faces && img.faces.length > 0 && (
              <div style={{ fontSize: 'var(--text-sm)' }}>
                Faces: {img.faces.map((f, i) => (
                  <span key={i} style={{ marginRight: '8px' }}>
                    {(f.conf * 100).toFixed(0)}% ({f.area.toFixed(1)}% area{f.emotion ? `, ${f.emotion}` : ''})
                  </span>
                ))}
                {img.identities && img.identities.length > 0 && (
                  <span style={{ color: 'var(--system-blue)' }}> ID: {img.identities.join(', ')}</span>
                )}
              </div>
            )}
            {img.ocr && img.ocr.length > 0 && (
              <div style={{ fontSize: 'var(--text-sm)' }}>
                OCR: <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{img.ocr.join(' | ')}</span>
              </div>
            )}
            {img.poses ? <Field label="Poses" value={img.poses} /> : null}
          </div>
        ) : null}

        {/* Segmentation */}
        {(img.foreground || img.segments) && (
          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>Segmentation</div>
            <div style={fieldRowStyle}>
              {img.foreground && <>
                <Field label="Foreground" value={`${img.foreground.fg_pct}%`} />
                <Field label="Background" value={`${img.foreground.bg_pct}%`} />
              </>}
              {img.segments && <>
                <Field label="Segments" value={img.segments.count} />
                <Field label="Largest" value={`${img.segments.largest_pct}%`} />
              </>}
            </div>
          </div>
        )}

        {/* Technical */}
        {(img.exif || img.analysis || img.location) && (
          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>Technical</div>
            {img.exif && (
              <div style={fieldRowStyle}>
                <Field label="Focal" value={img.exif.focal ? `${img.exif.focal}mm` : undefined} />
                <Field label="Aperture" value={img.exif.aperture ? `f/${img.exif.aperture}` : undefined} />
                <Field label="Shutter" value={img.exif.shutter} />
                <Field label="ISO" value={img.exif.iso || undefined} />
                <Field label="Make" value={img.exif.make} />
                <Field label="Model" value={img.exif.model} />
                <Field label="Lens" value={img.exif.lens} />
                <Field label="Date" value={img.exif.date} />
              </div>
            )}
            {img.analysis && (
              <div style={fieldRowStyle}>
                <Field label="Brightness" value={img.analysis.brightness} />
                <Field label="Dynamic Range" value={img.analysis.dynamic_range} />
                <Field label="Noise" value={img.analysis.noise} />
                <Field label="Color Temp" value={img.analysis.color_temp ? `${img.analysis.color_temp}K` : undefined} />
              </div>
            )}
            {img.location && img.location.name && (
              <Field label="Location" value={img.location.name} />
            )}
          </div>
        )}

        {/* Gemini meta */}
        {(img.grading || img.composition || img.exposure) && (
          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>Gemini Meta</div>
            <div style={fieldRowStyle}>
              <Field label="Grading" value={img.grading} />
              <Field label="Composition" value={img.composition} />
              <Field label="Exposure" value={img.exposure} />
              <Field label="Time" value={img.time} />
              <Field label="Setting" value={img.setting} />
              <Field label="Weather" value={img.weather} />
              <Field label="Sharpness" value={img.gemini_sharpness} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export function SignalInspectorPage() {
  const { data, loading, error } = useFetch<SignalData>('/api/signal-inspector')

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading signal data...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  return (
    <PageShell
      title="Signal Inspector"
      subtitle={`${data.sample_size} sampled picks out of ${data.total_picks} total \u2014 all DB signals per image`}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {data.images.map(img => (
          <SignalCard key={img.uuid} img={img} />
        ))}
      </div>
    </PageShell>
  )
}
