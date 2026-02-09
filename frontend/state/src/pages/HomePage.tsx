import { Link } from 'react-router-dom'
import { Footer } from '../components/layout/Footer'

const navCards: { to: string; tag: string; title: string; desc: string; accent: string }[] = [
  { to: '/dashboard', tag: 'System', title: 'State Dashboard', desc: 'Every pipeline, signal, and model in real-time. Progress bars, camera fleet, enhancement metrics.', accent: 'var(--system-blue)' },
  { to: '/journal', tag: 'Log', title: 'Journal de Bord', desc: 'Development journal. Every decision, experiment, and insight as the project evolves.', accent: 'var(--system-green)' },
  { to: '/instructions', tag: 'AI', title: 'System Instructions', desc: 'The prompts and system instructions that drive Gemini analysis and Claude engineering.', accent: 'var(--system-purple)' },
  { to: '/mosaics', tag: 'Visual', title: 'Mosaics', desc: 'Every photograph tiled into 4K mosaics, sorted by brightness, hue, camera, faces.', accent: 'var(--system-orange)' },
  { to: '/cartoon', tag: 'AI Variants', title: 'Cartoon', desc: 'Imagen 3 cel-shaded illustration transforms of curated photos. Side-by-side comparisons.', accent: 'var(--system-pink)' },
  { to: '/similarity', tag: 'Vectors', title: 'Similarity', desc: 'Vector-space nearest neighbors across three embedding models. Visual serendipity.', accent: 'var(--system-teal)' },
]

export function HomePage() {
  return (
    <>
      {/* Hero Banner */}
      <div style={{
        display: 'flex', alignItems: 'stretch', gap: 'var(--space-8)',
        marginBottom: 'var(--space-10)',
      }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 72, fontWeight: 800,
            letterSpacing: '-0.03em', lineHeight: 1, marginBottom: 4,
          }}>
            9,011
          </div>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)',
            fontWeight: 500, color: 'var(--muted)', marginBottom: 'var(--space-6)',
          }}>
            photographs, unedited
          </div>
          <p style={{
            fontSize: 'var(--text-base)', lineHeight: 'var(--leading-relaxed)',
            color: 'var(--fg-secondary)', marginBottom: 'var(--space-4)', maxWidth: 540,
          }}>
            Shot over a decade on <em style={{ color: 'var(--fg)', fontStyle: 'normal', fontWeight: 600 }}>Leica rangefinders</em>, a monochrome sensor with no Bayer filter, scanned analog film, and pocket action cameras. Most have never been seen by anyone.
          </p>
          <p style={{
            fontSize: 'var(--text-base)', lineHeight: 'var(--leading-relaxed)',
            color: 'var(--fg)', maxWidth: 540, fontWeight: 700,
          }}>
            Leverage all AIs &mdash; Claude Code, CV models, Gemini APIs &mdash; to create engaging, playful, elegant, smart, teasing, revealing, exciting experiences on screens.
          </p>
          <p style={{
            fontSize: 'var(--text-sm)', color: 'var(--muted)', marginTop: 'var(--space-2)',
            letterSpacing: 'var(--tracking-caps)', textTransform: 'uppercase', fontWeight: 600,
          }}>
            Game is ON.
          </p>
        </div>
        <div className="hero-mosaic-wrap" style={{
          width: 300, flexShrink: 0, borderRadius: 'var(--radius-xl)',
          overflow: 'hidden', boxShadow: 'var(--shadow-lg)',
        }}>
          <img
            src={`${import.meta.env.BASE_URL}hero-mosaic.jpg`}
            alt="Mosaic of 9,011 photographs arranged by brightness"
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            loading="eager"
          />
        </div>
      </div>

      {/* Nav Cards */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr', gap: 'var(--space-3)',
        marginBottom: 'var(--space-12)',
      }} className="nav-grid">
        {navCards.map(card => (
          <Link
            key={card.to}
            to={card.to}
            style={{
              display: 'block', background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)', padding: 'var(--space-5)',
              textDecoration: 'none', position: 'relative', overflow: 'hidden',
              transition: 'box-shadow var(--duration-normal), transform var(--duration-normal)',
              boxShadow: 'var(--shadow-sm)',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.boxShadow = 'var(--shadow-lg)'
              e.currentTarget.style.transform = 'translateY(-1px)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
              e.currentTarget.style.transform = 'none'
            }}
          >
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: card.accent }} />
            <div style={{
              fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
              letterSpacing: 'var(--tracking-caps)', color: card.accent, marginBottom: 'var(--space-2)',
            }}>
              {card.tag}
            </div>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)', fontWeight: 700,
              color: 'var(--fg)', letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-1)',
            }}>
              {card.title}
            </div>
            <div style={{
              fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)', color: 'var(--fg-secondary)',
            }}>
              {card.desc}
            </div>
          </Link>
        ))}
      </div>

      {/* The Collection */}
      <Section label="The Collection" heading="Five cameras, one decade">
        <ItemList items={[
          { name: 'Leica M8', desc: 'Digital CCD sensor, IR-sensitive', count: '3,533' },
          { name: 'DJI Osmo Pro', desc: 'Action camera, digital sensor', count: '3,032' },
          { name: 'Leica MP', desc: 'Analog \u2014 Kodak Portra 400 VC / B&W film, scanned', count: '1,126' },
          { name: 'Leica Monochrom', desc: 'Pure B&W sensor \u2014 no Bayer filter', count: '1,099' },
          { name: 'Canon G12 & Osmo Memo', desc: 'Compact digital + pocket action camera', count: '221' },
        ]} />
        <p style={{
          marginTop: 'var(--space-5)', fontSize: 'var(--text-sm)', color: 'var(--fg-secondary)',
        }}>
          <strong style={{ color: 'var(--fg)', fontWeight: 600 }}>5,138</strong> JPEG + <strong style={{ color: 'var(--fg)', fontWeight: 600 }}>3,841</strong> DNG + <strong style={{ color: 'var(--fg)', fontWeight: 600 }}>32</strong> RAW = <strong style={{ color: 'var(--fg)', fontWeight: 600 }}>9,011</strong> source images
        </p>
      </Section>

      {/* Three Apps */}
      <Section label="Three Apps" heading="See. Show. State.">
        <ItemList items={[
          { name: 'See', desc: 'The private power tool. A native macOS SwiftUI app for exploring, curating, and editing the collection. Browse by camera, vibe, time of day, aesthetic score. Keep or reject with a keystroke. Toggle between original and enhanced. Every decision flows back into the database.' },
          { name: 'Show', desc: 'The public experience. 14 web experiences: La Grille, Le Bento, La Similarit\u00E9, La D\u00E9rive, Les Couleurs, Le Terrain de Jeu, La Chambre Noire, Le Flot, Les Visages, La Boussole, L\u2019Observatoire, La Carte, La Machine \u00E0 \u00C9crire, Le Pendule. All images served from GCS.' },
          { name: 'State', desc: 'The system dashboard. Every pipeline, signal, and model in real-time. Progress bars, camera fleet statistics, enhancement metrics, vector store health.' },
        ]} />
      </Section>

      {/* The Pipeline */}
      <Section label="The Pipeline" heading="Eleven stages, per-image intelligence">
        <ol style={{ listStyle: 'none', counterReset: 'step' }}>
          {[
            { name: 'Render', desc: '6-tier resolution pyramid per image (64px to 3840px), plus 4-tier for AI variants.', file: 'render.py' },
            { name: 'Analyze', desc: 'Gemini 2.5 Pro structured analysis: vibes, exposure, composition, color grading, per-image edit instructions.', file: 'gemini.py' },
            { name: 'Pixel Metrics', desc: 'Luminance, white balance shift, noise levels, clipping, contrast ratio, color temperature.', file: 'signals.py' },
            { name: 'Vectors v1', desc: 'DINOv2-base (768d), SigLIP-base (768d), CLIP ViT-B/32 (512d) into LanceDB.', file: 'vectors.py' },
            { name: 'Vectors v2', desc: 'DINOv2-Large (1024d), SigLIP2-SO400M (1152d), CLIP (512d) \u2014 upgraded embeddings.', file: 'vectors_v2.py' },
            { name: 'Signals v1', desc: 'EXIF, dominant colors, faces (YuNet), objects (YOLOv8n), hashes, depth, scenes, aesthetics, OCR, captions, emotions.', file: 'signals.py + signals_advanced.py' },
            { name: 'Signals v2', desc: 'Florence-2 captions, Grounding DINO, SAM segmentation, TOPIQ/MUSIQ/LAION aesthetics, rembg, ArcFace identities, poses, saliency, tags.', file: 'signals_v2.py' },
            { name: 'Enhance', desc: 'Camera-aware per-image enhancement: WB, exposure, shadows/highlights, contrast, saturation, sharpening.', file: 'enhance.py' },
            { name: 'Variants', desc: 'AI variants via Imagen 3: cartoon cel-shaded illustrations.', file: 'imagen.py' },
            { name: 'Export', desc: 'Merge all signals into photos.json, faces.json, drift_neighbors.json for Show app.', file: 'export_gallery.py' },
            { name: 'Sync', desc: 'Upload to Google Cloud Storage. Track public URLs in the database.', file: 'upload.py' },
          ].map(step => (
            <li key={step.name} className="pipeline-item">
              <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', marginBottom: 2 }}>{step.name}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)', lineHeight: 'var(--leading-relaxed)' }}>{step.desc}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{step.file}</div>
            </li>
          ))}
        </ol>
      </Section>

      {/* Infrastructure */}
      <Section label="Infrastructure" heading="Under the hood">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 'var(--space-3)' }} className="infra-grid">
          {[
            { label: 'Database', value: 'SQLite \u2014 33 signal tables' },
            { label: 'Vector Store', value: 'LanceDB \u2014 9,011 \u00D7 3 (v2: 1024d + 1152d + 512d)' },
            { label: 'Cloud', value: 'gs://myproject-public-assets/', mono: true },
            { label: 'Platform', value: 'macOS, Python 3.9, Apple Silicon' },
            { label: 'AI Engine', value: 'Gemini 2.5 Pro + Imagen 3' },
          ].map(item => (
            <div key={item.label} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-4) var(--space-5)',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <div style={{
                fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: 'var(--tracking-caps)', color: 'var(--muted)', marginBottom: 2,
              }}>
                {item.label}
              </div>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--fg)' }}>
                {item.mono ? (
                  <code style={{
                    fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
                    color: 'var(--fg-secondary)', background: 'var(--hover-overlay)',
                    padding: '2px 6px', borderRadius: 4,
                  }}>
                    {item.value}
                  </code>
                ) : item.value}
              </div>
            </div>
          ))}
        </div>
        <div style={{
          fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: 'var(--tracking-caps)', color: 'var(--muted)', marginTop: 'var(--space-6)',
        }}>
          24 Models
        </div>
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', marginTop: 'var(--space-4)',
        }} className="model-grid">
          {['Gemini 2.5 Pro', 'Imagen 3', 'DINOv2-Large', 'SigLIP2-SO400M', 'CLIP', 'YOLOv8n', 'YuNet', 'BLIP', 'Depth Anything v2', 'Places365', 'Florence-2', 'Grounding DINO', 'SAM 2.1', 'TOPIQ', 'MUSIQ', 'LAION Aesthetic', 'rembg / U2Net', 'InsightFace ArcFace', 'YOLOv8n-pose', 'EasyOCR', 'RAM++ Tags', 'DeepFace', 'OpenCV Saliency', 'K-means LAB'].map(m => (
            <div key={m} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-3)',
              fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--fg-secondary)',
            }}>
              {m}
            </div>
          ))}
        </div>
      </Section>

      <Footer />
    </>
  )
}

function Section({ label, heading, children }: { label: string; heading: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 'var(--space-12)' }}>
      <div style={{
        fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-caps)', color: 'var(--muted)', marginBottom: 'var(--space-3)',
      }}>
        {label}
      </div>
      <h2 style={{
        fontFamily: 'var(--font-display)', fontSize: 'var(--text-2xl)', fontWeight: 700,
        letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-5)',
        paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--border)',
      }}>
        {heading}
      </h2>
      {children}
    </div>
  )
}

function ItemList({ items }: { items: { name: string; desc: string; count?: string }[] }) {
  return (
    <ul style={{ listStyle: 'none' }}>
      {items.map(item => (
        <li key={item.name} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: item.count ? 'baseline' : 'flex-start',
          padding: 'var(--space-3) 0', borderBottom: '1px solid var(--border)',
          flexDirection: item.count ? 'row' : 'column', gap: item.count ? undefined : 4,
        }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{item.name}</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)', marginTop: item.count ? 2 : 0 }}>{item.desc}</div>
          </div>
          {item.count && (
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)',
              fontVariantNumeric: 'tabular-nums', color: 'var(--fg-secondary)',
              whiteSpace: 'nowrap', marginLeft: 'var(--space-4)',
            }}>
              {item.count}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}
