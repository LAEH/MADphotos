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
  aesthetic: number
  colors: { hex: string; pct: number; name: string }[]
  depth: { near: number; mid: number; far: number }
  objects: { label: string; conf: number }[]
  faces: { conf: number; area: number; emotion: string }[]
  ocr: string[]
  exif: { focal: number; aperture: number; shutter: string; iso: number }
  blip_caption?: string
}

interface InspectorData {
  sample_size: number
  total: number
  images: SignalImage[]
}

function fmt(n: number): string {
  return n.toLocaleString()
}

/* Chip colors by signal type */
const chipColors: Record<string, string> = {
  gemini: 'var(--system-blue)',
  object: 'var(--system-green)',
  exif: 'var(--system-orange)',
  vibe: 'var(--system-purple)',
  face: 'var(--system-pink)',
  ocr: 'var(--system-teal)',
}

function Chip({ label, type }: { label: string; type: string }) {
  const bg = chipColors[type] || 'var(--system-blue)'
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      margin: '2px',
      borderRadius: '10px',
      fontSize: 'var(--text-xs)',
      fontFamily: 'var(--font-mono)',
      background: bg,
      color: '#fff',
      opacity: 0.9,
      whiteSpace: 'nowrap',
    }}>
      {label}
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
        <div style={{ lineHeight: 1.4 }}>
          {img.scene && <Chip label={img.scene} type="gemini" />}
          {img.style && <Chip label={img.style} type="gemini" />}
          {img.vibes.slice(0, 2).map(v => <Chip key={v} label={v} type="vibe" />)}
          {img.objects.slice(0, 2).map(o => <Chip key={o.label} label={o.label} type="object" />)}
          {img.faces.length > 0 && <Chip label={`${img.faces.length} face${img.faces.length > 1 ? 's' : ''}`} type="face" />}
          {img.ocr.length > 0 && <Chip label={`OCR: ${img.ocr[0]}`} type="ocr" />}
          {img.exif.focal > 0 && <Chip label={`${img.exif.focal}mm`} type="exif" />}
        </div>
      </div>
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
          <Row label="Camera" value={img.camera} />
          <Row label="Resolution" value={`${img.w} x ${img.h}`} />
          <Row label="Aesthetic" value={img.aesthetic.toFixed(1)} />
          {img.exif.focal > 0 && <Row label="Focal" value={`${img.exif.focal}mm`} />}
          {img.exif.aperture > 0 && <Row label="Aperture" value={`f/${img.exif.aperture}`} />}
          {img.exif.shutter && <Row label="Shutter" value={img.exif.shutter} />}
          {img.exif.iso > 0 && <Row label="ISO" value={String(img.exif.iso)} />}
        </Section>

        {/* Content */}
        <Section title="Content">
          {img.caption && <Row label="Caption" value={img.caption} />}
          {img.blip_caption && <Row label="BLIP" value={img.blip_caption} />}
          {img.scene && <Row label="Scene" value={img.scene} />}
          {img.environment && <Row label="Environment" value={img.environment} />}
          {img.setting && <Row label="Setting" value={img.setting} />}
          {img.objects.length > 0 && (
            <Row label="Objects" value={img.objects.map(o => `${o.label} (${o.conf})`).join(', ')} />
          )}
          {img.ocr.length > 0 && <Row label="OCR" value={img.ocr.join(', ')} />}
          {img.faces.length > 0 && (
            <Row label="Faces" value={img.faces.map(f =>
              `${(f.area * 100).toFixed(0)}% area${f.emotion ? `, ${f.emotion}` : ''}`
            ).join('; ')} />
          )}
        </Section>

        {/* Perception */}
        <Section title="Perception">
          {img.style && <Row label="Style" value={img.style} />}
          {img.grading && <Row label="Grading" value={img.grading} />}
          {img.vibes.length > 0 && <Row label="Vibes" value={img.vibes.join(', ')} />}
          {img.time && <Row label="Time" value={img.time} />}
          {img.exposure && <Row label="Exposure" value={img.exposure} />}
          {img.composition && <Row label="Composition" value={img.composition} />}
        </Section>

        {/* Technical */}
        <Section title="Technical">
          <Row label="Depth" value={`Near: ${img.depth.near}% / Mid: ${img.depth.mid}% / Far: ${img.depth.far}%`} />
          {img.colors.length > 0 && (
            <div style={{ marginTop: '8px', display: 'flex', gap: '6px' }}>
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
          )}
        </Section>
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

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      display: 'flex',
      gap: '12px',
      padding: '2px 0',
      fontSize: 'var(--text-sm)',
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
      <span style={{ color: 'var(--fg)' }}>{value}</span>
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
