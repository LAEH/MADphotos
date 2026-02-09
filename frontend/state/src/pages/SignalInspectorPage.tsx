import { useState, useMemo, useCallback } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { Footer } from '../components/layout/Footer'

interface SignalImage {
  uuid: string
  thumb: string
  display: string
  camera: string
  w: number
  h: number
  caption: string
  alt: string
  scene: string
  environment: string
  style: string
  grading: string
  vibes: string[]
  time: string
  setting: string
  exposure: string
  composition: string
  weather: string
  sharpness: string
  aesthetic: number
  colors: { hex: string; pct: number; name: string }[]
  depth: { near: number; mid: number; far: number }
  objects: { label: string; conf: number }[]
  faces: { conf: number; area: number; emotion: string }[]
  ocr: string[]
  exif: { focal: number; aperture: number; shutter: string; iso: number; make?: string; model?: string; lens?: string; date?: string }
  blip_caption?: string
  // v2 signals
  aesthetic_v2?: { topiq: number; musiq: number; laion: number; composite: number }
  quality?: { technical: number; clip: number; combined: number }
  florence?: { short: string; detailed: string }
  tags?: string[]
  open_objects?: { label: string; conf: number }[]
  identities?: string[]
  foreground?: { fg_pct: number; bg_pct: number }
  segments?: { count: number; largest_pct: number }
  poses?: number
  saliency?: { peak_x: number; peak_y: number; spread: number; center_bias: number }
  location?: { name: string; lat: number; lon: number }
  hashes?: { blur: number; sharpness: number; edge_density: number; entropy: number }
  analysis?: { brightness: number; dynamic_range: number; noise: number; color_temp: number }
  border?: number
}

interface InspectorData {
  sample_size: number
  total: number
  images: SignalImage[]
}

function fmt(n: number): string {
  return n.toLocaleString()
}

function Chip({ label, model, color }: { label: string; model: string; color: string }) {
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      padding: '2px 8px',
      margin: '2px',
      borderRadius: '10px',
      fontSize: 'var(--text-xs)',
      fontFamily: 'var(--font-mono)',
      background: color,
      color: '#fff',
      opacity: 0.9,
      whiteSpace: 'nowrap',
    }}>
      {label}
      <span style={{
        fontSize: '9px',
        padding: '0 4px',
        borderRadius: '6px',
        background: 'rgba(255,255,255,0.2)',
        lineHeight: '14px',
      }}>
        {model}
      </span>
    </span>
  )
}

function ImageCard({ img, onClick }: { img: SignalImage; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        gap: '12px',
        padding: '12px',
        borderRadius: '8px',
        background: 'var(--card-bg)',
        border: '1px solid var(--border)',
        cursor: 'pointer',
        transition: 'border-color 0.2s',
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--system-blue)')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      <img
        src={imageUrl(img.thumb)}
        alt={img.alt || img.caption}
        loading="lazy"
        style={{
          width: '120px',
          height: '90px',
          objectFit: 'cover',
          borderRadius: '4px',
          flexShrink: 0,
          background: 'var(--bg-secondary)',
        }}
      />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: '4px',
        }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            color: 'var(--muted)',
          }}>
            {img.camera}
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
            color: img.aesthetic >= 8 ? 'var(--system-green)' : img.aesthetic >= 6 ? 'var(--fg)' : 'var(--system-orange)',
          }}>
            {img.aesthetic.toFixed(1)}
          </span>
        </div>
        <div style={{ lineHeight: 1.6, display: 'flex', flexWrap: 'wrap' }}>
          {img.scene && <Chip label={img.scene} model="Places365" color="var(--system-teal)" />}
          {img.style && <Chip label={img.style} model="ResNet50" color="var(--system-indigo)" />}
          {img.vibes.slice(0, 2).map(v => <Chip key={v} label={v} model="Gemini" color="var(--system-blue)" />)}
          {img.objects.slice(0, 2).map(o => <Chip key={o.label} label={o.label} model="YOLOv8" color="var(--system-green)" />)}
          {(img.open_objects || []).slice(0, 2).map(o => <Chip key={`od-${o.label}`} label={o.label} model="G-DINO" color="var(--system-green)" />)}
          {(img.tags || []).slice(0, 2).map(t => <Chip key={`tag-${t}`} label={t} model="CLIP" color="var(--system-indigo)" />)}
          {img.faces.length > 0 && <Chip label={`${img.faces.length} face${img.faces.length > 1 ? 's' : ''}`} model="RetinaFace" color="var(--system-pink)" />}
          {(img.identities || []).length > 0 && <Chip label={img.identities![0]} model="ArcFace" color="var(--system-pink)" />}
          {img.ocr.length > 0 && <Chip label={`OCR: ${img.ocr[0]}`} model="EasyOCR" color="var(--system-teal)" />}
          {img.exif.focal > 0 && <Chip label={`${img.exif.focal}mm`} model="EXIF" color="var(--system-gray)" />}
          {img.location && <Chip label={img.location.name || `${img.location.lat.toFixed(2)}, ${img.location.lon.toFixed(2)}`} model="GPS" color="var(--system-orange)" />}
          {img.poses !== undefined && img.poses > 0 && <Chip label={`${img.poses} pose${img.poses > 1 ? 's' : ''}`} model="YOLOv8-pose" color="var(--system-green)" />}
          {img.border !== undefined && <Chip label={`border ${img.border}%`} model="OpenCV" color="var(--system-gray)" />}
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <h4 style={{
        margin: '0 0 8px',
        fontSize: 'var(--text-xs)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--muted)',
        borderBottom: '1px solid var(--border)',
        paddingBottom: '4px',
      }}>
        {title}
      </h4>
      {children}
    </div>
  )
}

function Row({ label, value, model }: { label: string; value: string; model?: string }) {
  return (
    <div style={{
      display: 'flex',
      gap: '12px',
      padding: '2px 0',
      fontSize: 'var(--text-sm)',
      alignItems: 'baseline',
    }}>
      <span style={{
        width: '100px',
        flexShrink: 0,
        color: 'var(--muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: 'var(--text-xs)',
      }}>
        {label}
      </span>
      <span style={{ color: 'var(--fg)', flex: 1 }}>{value}</span>
      {model && (
        <span style={{
          fontSize: '9px',
          padding: '1px 6px',
          borderRadius: '6px',
          background: 'var(--bg-secondary)',
          color: 'var(--muted)',
          fontFamily: 'var(--font-mono)',
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}>
          {model}
        </span>
      )}
    </div>
  )
}

function DetailModal({ img, onClose }: { img: SignalImage; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'rgba(0,0,0,0.85)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--card-bg)',
          borderRadius: '12px',
          maxWidth: '900px',
          width: '100%',
          maxHeight: '90vh',
          overflow: 'auto',
          padding: '24px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h3 style={{ margin: 0, fontSize: 'var(--text-base)' }}>
            {img.uuid.slice(0, 8)}... — {img.camera}
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--muted)',
              cursor: 'pointer',
              fontSize: '20px',
            }}
          >
            &times;
          </button>
        </div>

        <img
          src={imageUrl(img.display)}
          alt={img.alt || img.caption}
          style={{
            width: '100%',
            maxHeight: '400px',
            objectFit: 'contain',
            borderRadius: '8px',
            background: '#000',
            marginBottom: '20px',
          }}
        />

        {/* Identity */}
        <Section title="Identity">
          <Row label="Camera" value={img.camera} model="EXIF" />
          <Row label="Resolution" value={`${img.w} x ${img.h}`} />
          <Row label="Aesthetic" value={img.aesthetic.toFixed(1)} model="LAION" />
          {img.aesthetic_v2 && (
            <Row label="Aesthetic v2" value={`TOPIQ ${img.aesthetic_v2.topiq} / MUSIQ ${img.aesthetic_v2.musiq} / LAION ${img.aesthetic_v2.laion} = ${img.aesthetic_v2.composite}`} model="TOPIQ+MUSIQ" />
          )}
          {img.quality && (
            <Row label="Quality" value={`Tech ${img.quality.technical} / CLIP ${img.quality.clip} / Combined ${img.quality.combined}`} model="Technical+CLIP" />
          )}
          {img.exif.focal > 0 && <Row label="Focal" value={`${img.exif.focal}mm`} model="EXIF" />}
          {img.exif.aperture > 0 && <Row label="Aperture" value={`f/${img.exif.aperture}`} model="EXIF" />}
          {img.exif.shutter && <Row label="Shutter" value={img.exif.shutter} model="EXIF" />}
          {img.exif.iso > 0 && <Row label="ISO" value={String(img.exif.iso)} model="EXIF" />}
          {img.exif.make && <Row label="Make" value={img.exif.make} model="EXIF" />}
          {img.exif.model && <Row label="Model" value={img.exif.model} model="EXIF" />}
          {img.exif.lens && <Row label="Lens" value={img.exif.lens} model="EXIF" />}
          {img.exif.date && <Row label="Date" value={img.exif.date} model="EXIF" />}
          {img.hashes && (
            <Row label="Hashes" value={`Blur ${img.hashes.blur} / Sharp ${img.hashes.sharpness} / Entropy ${img.hashes.entropy}`} model="pHash" />
          )}
          {img.border !== undefined && (
            <Row label="Border" value={`${img.border}% border detected`} model="OpenCV" />
          )}
        </Section>

        {/* Content */}
        <Section title="Content">
          {img.caption && <Row label="Caption" value={img.caption} model="Gemini" />}
          {img.blip_caption && <Row label="BLIP" value={img.blip_caption} model="BLIP2" />}
          {img.florence && img.florence.short && (
            <Row label="Florence" value={img.florence.short} model="Florence-2" />
          )}
          {img.florence && img.florence.detailed && (
            <Row label="Detailed" value={img.florence.detailed} model="Florence-2" />
          )}
          {img.scene && <Row label="Scene" value={img.scene} model="Places365" />}
          {img.environment && <Row label="Environment" value={img.environment} model="Places365" />}
          {img.setting && <Row label="Setting" value={img.setting} model="Gemini" />}
          {img.objects.length > 0 && (
            <Row label="Objects" value={img.objects.map(o => `${o.label} (${o.conf})`).join(', ')} model="YOLOv8" />
          )}
          {(img.open_objects || []).length > 0 && (
            <Row label="Open Det." value={img.open_objects!.map(o => `${o.label} (${o.conf})`).join(', ')} model="G-DINO" />
          )}
          {(img.tags || []).length > 0 && (
            <Row label="Tags" value={img.tags!.join(', ')} model="CLIP" />
          )}
          {img.ocr.length > 0 && <Row label="OCR" value={img.ocr.join(', ')} model="EasyOCR" />}
          {img.faces.length > 0 && (
            <Row label="Faces" value={img.faces.map(f =>
              `${(f.area * 100).toFixed(0)}% area${f.emotion ? `, ${f.emotion}` : ''}`
            ).join('; ')} model="RetinaFace" />
          )}
          {(img.identities || []).length > 0 && (
            <Row label="Identities" value={img.identities!.join(', ')} model="ArcFace" />
          )}
          {img.poses !== undefined && img.poses > 0 && (
            <Row label="Poses" value={`${img.poses} pose${img.poses > 1 ? 's' : ''} detected`} model="YOLOv8-pose" />
          )}
          {img.location && (
            <Row label="Location" value={img.location.name || `${img.location.lat.toFixed(4)}, ${img.location.lon.toFixed(4)}`} model="EXIF GPS" />
          )}
        </Section>

        {/* Perception */}
        <Section title="Perception">
          {img.style && <Row label="Style" value={img.style} model="ResNet50" />}
          {img.grading && <Row label="Grading" value={img.grading} model="Gemini" />}
          {img.vibes.length > 0 && <Row label="Vibes" value={img.vibes.join(', ')} model="Gemini" />}
          {img.time && <Row label="Time" value={img.time} model="Gemini" />}
          {img.exposure && <Row label="Exposure" value={img.exposure} model="Gemini" />}
          {img.composition && <Row label="Composition" value={img.composition} model="Gemini" />}
          {img.weather && <Row label="Weather" value={img.weather} model="Gemini" />}
          {img.sharpness && <Row label="Sharpness" value={img.sharpness} model="Gemini" />}
        </Section>

        {/* Technical */}
        <Section title="Technical">
          <Row label="Depth" value={`Near: ${img.depth.near}% / Mid: ${img.depth.mid}% / Far: ${img.depth.far}%`} model="Depth v2L" />
          {img.foreground && (
            <Row label="Foreground" value={`FG ${img.foreground.fg_pct}% / BG ${img.foreground.bg_pct}%`} model="u2net" />
          )}
          {img.segments && (
            <Row label="Segments" value={`${img.segments.count} segments, largest ${img.segments.largest_pct}%`} model="SAM 2.1" />
          )}
          {img.saliency && (
            <Row label="Saliency" value={`Peak (${img.saliency.peak_x}, ${img.saliency.peak_y}) spread ${img.saliency.spread} bias ${img.saliency.center_bias}`} model="OpenCV SR" />
          )}
          {img.analysis && (
            <>
              <Row label="Brightness" value={`${img.analysis.brightness}`} model="NumPy/CV" />
              <Row label="Dyn. Range" value={`${img.analysis.dynamic_range}`} model="NumPy/CV" />
              <Row label="Noise Est." value={`${img.analysis.noise}`} model="NumPy/CV" />
              {img.analysis.color_temp > 0 && <Row label="Color Temp" value={`${img.analysis.color_temp}K`} model="NumPy/CV" />}
            </>
          )}
          {img.colors.length > 0 && (
            <div style={{ marginTop: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <span style={{
                  width: '100px',
                  flexShrink: 0,
                  color: 'var(--muted)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                }}>
                  Colors
                </span>
                <span style={{
                  fontSize: '9px',
                  padding: '1px 6px',
                  borderRadius: '6px',
                  background: 'var(--bg-secondary)',
                  color: 'var(--muted)',
                  fontFamily: 'var(--font-mono)',
                }}>
                  K-means
                </span>
              </div>
              <div style={{ display: 'flex', gap: '6px', marginLeft: '112px' }}>
                {img.colors.map((c, i) => (
                  <div key={i} style={{ textAlign: 'center' }}>
                    <div style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '4px',
                      background: c.hex,
                      border: '1px solid var(--border)',
                    }} />
                    <div style={{ fontSize: '10px', color: 'var(--muted)', marginTop: '2px' }}>
                      {c.pct}%
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}

export function SignalInspectorPage() {
  const { data, loading, error } = useFetch<InspectorData>('/api/signal-inspector')
  const [selected, setSelected] = useState<SignalImage | null>(null)
  const [cameraFilter, setCameraFilter] = useState('')
  const [sceneFilter, setSceneFilter] = useState('')
  const [aestheticRange, setAestheticRange] = useState<[number, number]>([0, 10])
  const [shuffleSeed, setShuffleSeed] = useState(0)

  const cameras = useMemo(() => {
    if (!data) return []
    const set = new Set(data.images.map(i => i.camera))
    return Array.from(set).sort()
  }, [data])

  const scenes = useMemo(() => {
    if (!data) return []
    const set = new Set(data.images.map(i => i.scene).filter(Boolean))
    return Array.from(set).sort()
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    let imgs = data.images.filter(i => {
      if (cameraFilter && i.camera !== cameraFilter) return false
      if (sceneFilter && i.scene !== sceneFilter) return false
      if (i.aesthetic < aestheticRange[0] || i.aesthetic > aestheticRange[1]) return false
      return true
    })
    // Shuffle deterministically by seed
    if (shuffleSeed > 0) {
      const seeded = [...imgs]
      for (let i = seeded.length - 1; i > 0; i--) {
        const j = (shuffleSeed * (i + 1) * 2654435761) % (i + 1)
        const abs = Math.abs(j) % (i + 1);
        [seeded[i], seeded[abs]] = [seeded[abs], seeded[i]]
      }
      return seeded
    }
    return imgs
  }, [data, cameraFilter, sceneFilter, aestheticRange, shuffleSeed])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') setSelected(null)
  }, [])

  if (loading) return <div className="main-content"><p style={{ color: 'var(--muted)' }}>Loading signals...</p></div>
  if (error) return <div className="main-content"><p style={{ color: 'var(--system-red)' }}>Error: {error}</p></div>
  if (!data) return null

  return (
    <div className="main-content" onKeyDown={handleKeyDown} tabIndex={0}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ marginBottom: '4px' }}>Signal Inspector</h1>
        <p style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
          {fmt(data.sample_size)} of {fmt(data.total)} images, all AI signals
        </p>
      </div>

      {/* Filter bar */}
      <div style={{
        display: 'flex',
        gap: '12px',
        flexWrap: 'wrap',
        marginBottom: '20px',
        alignItems: 'center',
      }}>
        <select
          value={cameraFilter}
          onChange={e => setCameraFilter(e.target.value)}
          style={{
            padding: '6px 10px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--fg)',
            fontSize: 'var(--text-sm)',
          }}
        >
          <option value="">All Cameras</option>
          {cameras.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        <select
          value={sceneFilter}
          onChange={e => setSceneFilter(e.target.value)}
          style={{
            padding: '6px 10px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--fg)',
            fontSize: 'var(--text-sm)',
          }}
        >
          <option value="">All Scenes</option>
          {scenes.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 'var(--text-sm)' }}>
          <span style={{ color: 'var(--muted)' }}>Aesthetic</span>
          <input
            type="range"
            min={0}
            max={10}
            step={0.5}
            value={aestheticRange[0]}
            onChange={e => setAestheticRange([parseFloat(e.target.value), aestheticRange[1]])}
            style={{ width: '60px' }}
          />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
            {aestheticRange[0]}-{aestheticRange[1]}
          </span>
          <input
            type="range"
            min={0}
            max={10}
            step={0.5}
            value={aestheticRange[1]}
            onChange={e => setAestheticRange([aestheticRange[0], parseFloat(e.target.value)])}
            style={{ width: '60px' }}
          />
        </div>

        <button
          onClick={() => setShuffleSeed(s => s + 1)}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--fg)',
            cursor: 'pointer',
            fontSize: 'var(--text-sm)',
          }}
        >
          Shuffle
        </button>

        <span style={{ color: 'var(--muted)', fontSize: 'var(--text-xs)', marginLeft: 'auto' }}>
          {filtered.length} images
        </span>
      </div>

      {/* Card grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
        gap: '12px',
        marginBottom: '40px',
      }}>
        {filtered.map(img => (
          <ImageCard key={img.uuid} img={img} onClick={() => setSelected(img)} />
        ))}
      </div>

      {selected && <DetailModal img={selected} onClose={() => setSelected(null)} />}

      <Footer />
    </div>
  )
}
