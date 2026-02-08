import { useRef, useEffect, useState } from 'react'
import { useFetch } from '../hooks/useFetch'
import { Footer } from '../components/layout/Footer'

/* ── Types (only fields this page needs) ── */
interface StatsData {
  total: number
  aesthetic_histogram: { bucket: number; count: number }[]
  aesthetic_avg: number
  monochrome_count: number
  cameras: { body: string; count: number; medium: string; film: string }[]
  top_styles: { name: string; count: number }[]
  top_scenes: { name: string; count: number }[]
  vibes: { name: string; count: number }[]
  top_emotions: { name: string; count: number }[]
  time_of_day: { name: string; count: number }[]
  depth_complexity_buckets: { name: string; count: number }[]
  top_objects: { name: string; count: number }[]
  top_color_names: { name: string; hex: string; count: number }[]
  face_images_with: number
  grading: { name: string; count: number }[]
  composition: { name: string; count: number }[]
  exposure: { name: string; count: number }[]
}

function fmt(n: number): string {
  return n.toLocaleString()
}

/* ── Scroll-reveal hook ── */
function useInView(threshold = 0.08) {
  const ref = useRef<HTMLElement>(null)
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect() } },
      { threshold }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [threshold])
  return { ref, visible }
}

/* ── BarChart helper (horizontal bars) ── */
function BarChart({ items, color, max: maxOverride }: {
  items: { label: string; value: number; color?: string }[]
  color?: string
  max?: number
}) {
  const maxVal = maxOverride ?? Math.max(...items.map(i => i.value), 1)
  const total = items.reduce((s, i) => s + i.value, 0)
  return (
    <div className="bar-chart">
      {items.map((item, i) => {
        const pct = total > 0 ? Math.round((item.value / total) * 100) : 0
        return (
          <div className="bar-row" key={i}>
            <span className="bar-label">{item.label}</span>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{
                  width: `${(item.value / maxVal) * 100}%`,
                  background: item.color || color || 'var(--system-blue)',
                }}
              />
            </div>
            <span className="bar-count">{fmt(item.value)}</span>
            <span className="bar-pct">{pct}%</span>
          </div>
        )
      })}
    </div>
  )
}

/* ── Section wrapper with scroll reveal ── */
function ChartSection({ title, subtitle, children, className }: {
  title: string
  subtitle: string
  children: React.ReactNode
  className?: string
}) {
  const { ref, visible } = useInView()
  return (
    <section
      ref={ref}
      className={`chart-section${visible ? ' chart-visible' : ''}${className ? ' ' + className : ''}`}
    >
      <h2 className="section-title">{title}</h2>
      <p className="chart-subtitle">{subtitle}</p>
      {children}
    </section>
  )
}

/* ── Hero stat row ── */
function HeroStats({ data }: { data: StatsData }) {
  return (
    <div className="hero-stats">
      <div className="hero-stat">
        <span className="hero-stat-num">{fmt(data.total)}</span>
        <span className="hero-stat-label">Images</span>
      </div>
      <div className="hero-stat">
        <span className="hero-stat-num">{data.aesthetic_avg.toFixed(1)}</span>
        <span className="hero-stat-label">Aesthetic Avg</span>
      </div>
      <div className="hero-stat">
        <span className="hero-stat-num">{data.cameras.length}</span>
        <span className="hero-stat-label">Cameras</span>
      </div>
      <div className="hero-stat">
        <span className="hero-stat-num">{fmt(data.face_images_with)}</span>
        <span className="hero-stat-label">Faces Found</span>
      </div>
      <div className="hero-stat">
        <span className="hero-stat-num">{fmt(data.monochrome_count)}</span>
        <span className="hero-stat-label">Monochrome</span>
      </div>
    </div>
  )
}

/* ── 1. The Quality Curve (vertical histogram, log scale) ── */
function QualityCurve({ data }: { data: StatsData }) {
  const hist = data.aesthetic_histogram
  if (!hist.length) return null
  const logMax = Math.log10(Math.max(...hist.map(h => h.count)) + 1)
  return (
    <ChartSection
      title="The Quality Curve"
      subtitle="NIMA aesthetic score distribution — log scale to show the tail"
    >
      <div className="histogram">
        {hist.map((h, i) => {
          const logH = Math.log10(h.count + 1) / logMax * 100
          return (
            <div className="histogram-col" key={i}>
              <span className="histogram-count">{fmt(h.count)}</span>
              <div className="histogram-bar-wrap">
                <div
                  className="histogram-bar"
                  style={{
                    height: `${logH}%`,
                    background: 'var(--system-blue)',
                  }}
                />
              </div>
              <span className="histogram-label">{h.bucket}</span>
            </div>
          )
        })}
      </div>
    </ChartSection>
  )
}

/* ── 2. The Fleet (cameras) ── */
function Fleet({ data }: { data: StatsData }) {
  const cameras = data.cameras.slice(0, 12)
  if (!cameras.length) return null
  const items = cameras.map(c => ({
    label: c.body,
    value: c.count,
    color: c.medium === 'scanned_film' || c.medium === 'film'
      ? 'var(--system-orange)' : 'var(--system-blue)',
  }))
  return (
    <ChartSection
      title="The Fleet"
      subtitle="Camera bodies that shot this archive"
    >
      <BarChart items={items} />
      <div className="chart-legend">
        <span className="legend-item"><span className="legend-dot" style={{ background: 'var(--system-blue)' }} />Digital</span>
        <span className="legend-item"><span className="legend-dot" style={{ background: 'var(--system-orange)' }} />Film</span>
      </div>
    </ChartSection>
  )
}

/* ── 3. The Identity (styles) ── */
function Identity({ data }: { data: StatsData }) {
  const styles = data.top_styles.slice(0, 7)
  if (!styles.length) return null
  return (
    <ChartSection title="The Identity" subtitle="Dominant visual styles in the collection">
      <BarChart
        items={styles.map(s => ({ label: s.name, value: s.count }))}
        color="var(--system-purple)"
      />
    </ChartSection>
  )
}

/* ── 4. The Look (grading) ── */
const GRADING_COLORS: Record<string, string> = {
  cinematic: 'var(--system-blue)',
  natural: 'var(--system-green)',
  monochrome: 'var(--muted)',
  pastel: 'var(--system-pink)',
}
function Look({ data }: { data: StatsData }) {
  const grading = data.grading
  if (!grading?.length) return null
  return (
    <ChartSection title="The Look" subtitle="Color grading and tonal treatment">
      <BarChart
        items={grading.map(g => ({
          label: g.name,
          value: g.count,
          color: GRADING_COLORS[g.name.toLowerCase()] || 'var(--system-cyan)',
        }))}
      />
    </ChartSection>
  )
}

/* ── 5. The World (scenes) ── */
function World({ data }: { data: StatsData }) {
  const scenes = data.top_scenes.slice(0, 12)
  if (!scenes.length) return null
  return (
    <ChartSection title="The World" subtitle="What places and environments appear in the frames">
      <BarChart
        items={scenes.map(s => ({ label: s.name, value: s.count }))}
        color="var(--system-teal)"
      />
    </ChartSection>
  )
}

/* ── 6. The Feeling (vibes) ── */
function Feeling({ data }: { data: StatsData }) {
  const vibes = data.vibes.slice(0, 12)
  if (!vibes.length) return null
  return (
    <ChartSection title="The Feeling" subtitle="The moods and vibes that define the archive">
      <BarChart
        items={vibes.map(v => ({ label: v.name, value: v.count }))}
        color="var(--system-pink)"
      />
    </ChartSection>
  )
}

/* ── 7. The Human Element (emotions) ── */
const EMOTION_COLORS: Record<string, string> = {
  happy: '#FFCC00',
  sad: '#5856D6',
  angry: '#FF3B30',
  surprise: '#FF9500',
  fear: '#AF52DE',
  disgust: '#34C759',
  neutral: '#98989D',
  contempt: '#A2845E',
}
function HumanElement({ data }: { data: StatsData }) {
  const emotions = data.top_emotions.slice(0, 6)
  if (!emotions.length) return null
  return (
    <ChartSection title="The Human Element" subtitle="Dominant emotions detected in faces">
      <BarChart
        items={emotions.map(e => ({
          label: e.name,
          value: e.count,
          color: EMOTION_COLORS[e.name.toLowerCase()] || 'var(--muted)',
        }))}
      />
    </ChartSection>
  )
}

/* ── 8. The Layers (depth complexity) ── */
const DEPTH_COLORS = ['var(--system-green)', 'var(--system-teal)', 'var(--system-blue)', 'var(--system-indigo)']
const DEPTH_ORDER = ['simple', 'moderate', 'layered', 'complex']
function Layers({ data }: { data: StatsData }) {
  const buckets = data.depth_complexity_buckets
  if (!buckets.length) return null
  const sorted = [...buckets].sort((a, b) =>
    DEPTH_ORDER.indexOf(a.name) - DEPTH_ORDER.indexOf(b.name)
  )
  return (
    <ChartSection title="The Layers" subtitle="Depth complexity across the archive">
      <BarChart
        items={sorted.map((b, i) => ({
          label: b.name,
          value: b.count,
          color: DEPTH_COLORS[i] || 'var(--system-indigo)',
        }))}
      />
    </ChartSection>
  )
}

/* ── 9. The Light (time of day, segmented bar) ── */
const TIME_COLORS: Record<string, string> = {
  'golden hour': '#FF9500',
  'blue hour': '#5856D6',
  'midday': '#FFCC00',
  'day': '#FFCC00',
  'night': '#3A3A3C',
  'overcast': '#98989D',
  'sunset': '#FF2D55',
  'sunrise': '#FF9500',
  'dawn': '#AF52DE',
  'dusk': '#5856D6',
  'dusk/blue hour': '#5856D6',
  'artificial': '#5AC8FA',
  'mixed': '#86868B',
}
function Light({ data }: { data: StatsData }) {
  const tod = data.time_of_day
  if (!tod.length) return null
  const total = tod.reduce((s, t) => s + t.count, 0)
  return (
    <ChartSection title="The Light" subtitle="When these photos were taken">
      <div className="segmented-bar">
        {tod.map((t, i) => (
          <div
            key={i}
            className="segment"
            style={{
              width: `${(t.count / total) * 100}%`,
              background: TIME_COLORS[t.name.toLowerCase()] || 'var(--muted)',
            }}
            title={`${t.name}: ${fmt(t.count)}`}
          />
        ))}
      </div>
      <div className="segment-legend">
        {tod.map((t, i) => (
          <span key={i} className="legend-item">
            <span className="legend-dot" style={{ background: TIME_COLORS[t.name.toLowerCase()] || 'var(--muted)' }} />
            {t.name} ({fmt(t.count)})
          </span>
        ))}
      </div>
    </ChartSection>
  )
}

/* ── 10. The Exposure ── */
const EXPOSURE_COLORS: Record<string, string> = {
  balanced: 'var(--system-green)',
  under: 'var(--system-blue)',
  over: 'var(--system-orange)',
}
function Exposure({ data }: { data: StatsData }) {
  const exp = data.exposure
  if (!exp?.length) return null
  return (
    <ChartSection title="The Exposure" subtitle="How light is distributed across the archive">
      <BarChart
        items={exp.map(e => ({
          label: e.name,
          value: e.count,
          color: EXPOSURE_COLORS[e.name.toLowerCase()] || 'var(--muted)',
        }))}
      />
    </ChartSection>
  )
}

/* ── 11. The Composition ── */
function Composition({ data }: { data: StatsData }) {
  const comp = data.composition?.filter(c => !c.name.includes('|'))
  if (!comp?.length) return null
  return (
    <ChartSection title="The Composition" subtitle="Compositional techniques identified by AI">
      <BarChart
        items={comp.map(c => ({ label: c.name, value: c.count }))}
        color="var(--system-indigo)"
      />
    </ChartSection>
  )
}

/* ── 12. What's In Frame (objects) ── */
function InFrame({ data }: { data: StatsData }) {
  const objects = data.top_objects.slice(0, 12)
  if (!objects.length) return null
  return (
    <ChartSection title="What's In Frame" subtitle="Most frequently detected objects">
      <BarChart
        items={objects.map(o => ({ label: o.name, value: o.count }))}
        color="var(--system-green)"
      />
    </ChartSection>
  )
}

/* ── 13. The Palette (color swatches, sized by count) ── */
function Palette({ data }: { data: StatsData }) {
  const colors = data.top_color_names.slice(0, 20)
  if (!colors.length) return null
  const maxC = Math.max(...colors.map(c => c.count))
  return (
    <ChartSection title="The Palette" subtitle="Dominant colors across the archive">
      <div className="color-grid">
        {colors.map((c, i) => {
          const h = 40 + (c.count / maxC) * 48
          return (
            <div className="color-swatch" key={i}>
              <div
                className="swatch-block"
                style={{ background: c.hex, height: `${h}px` }}
              />
              <span className="swatch-name">{c.name}</span>
              <span className="swatch-count">{fmt(c.count)}</span>
            </div>
          )
        })}
      </div>
    </ChartSection>
  )
}

/* ── Page ── */
export function StatsPage() {
  const { data, loading, error } = useFetch<StatsData>('/api/stats')

  if (loading) return <div className="main-content"><p style={{ color: 'var(--muted)' }}>Loading stats...</p></div>
  if (error) return <div className="main-content"><p style={{ color: 'var(--system-red)' }}>Error: {error}</p></div>
  if (!data) return null

  return (
    <div className="main-content">
      <div className="stats-hero">
        <h1>Stats</h1>
        <p style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)' }}>
          A visual profile of the archive
        </p>
      </div>

      <HeroStats data={data} />
      <QualityCurve data={data} />
      <Fleet data={data} />

      <div className="chart-pair">
        <Identity data={data} />
        <Look data={data} />
      </div>

      <World data={data} />
      <Feeling data={data} />

      <div className="chart-pair">
        <HumanElement data={data} />
        <Layers data={data} />
      </div>

      <Light data={data} />

      <div className="chart-pair">
        <Exposure data={data} />
        <Composition data={data} />
      </div>

      <InFrame data={data} />
      <Palette data={data} />

      <Footer />
    </div>
  )
}
