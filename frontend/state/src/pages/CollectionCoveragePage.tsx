import { useMemo } from 'react'
import { useFetch } from '../hooks/useFetch'
import { Footer } from '../components/layout/Footer'

interface DistEntry {
  appearances: number
  count: number
}

interface Experience {
  name: string
  pool_size: number
  pct_of_collection: number
}

interface DimensionData {
  full: Record<string, number>
  curated: Record<string, number>
}

interface CoverageData {
  total: number
  in_at_least_one: number
  in_zero: number
  pct_covered: number
  distribution: DistEntry[]
  experiences: Experience[]
  dimensions: Record<string, DimensionData>
}

function fmt(n: number): string {
  return n.toLocaleString()
}

/* Hero stats row */
function HeroStats({ data }: { data: CoverageData }) {
  return (
    <div className="hero-stats" style={{ marginBottom: '32px' }}>
      <div className="hero-stat">
        <span className="hero-stat-num">{fmt(data.in_at_least_one)}</span>
        <span className="hero-stat-label">Visible</span>
      </div>
      <div className="hero-stat">
        <span className="hero-stat-num">{data.pct_covered}%</span>
        <span className="hero-stat-label">Coverage</span>
      </div>
      <div className="hero-stat">
        <span className="hero-stat-num" style={{ color: data.in_zero > 0 ? 'var(--system-orange)' : 'var(--system-green)' }}>
          {fmt(data.in_zero)}
        </span>
        <span className="hero-stat-label">Invisible</span>
      </div>
      <div className="hero-stat">
        <span className="hero-stat-num">{data.experiences.length}</span>
        <span className="hero-stat-label">Experiences</span>
      </div>
    </div>
  )
}

/* Distribution histogram */
function DistributionChart({ distribution }: { distribution: DistEntry[] }) {
  const maxCount = Math.max(...distribution.map(d => d.count), 1)
  const logMax = Math.log10(maxCount + 1)

  return (
    <div style={{ marginBottom: '40px' }}>
      <h2 className="section-title">Appearance Distribution</h2>
      <p style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)', marginBottom: '16px' }}>
        How many experiences each image appears in (log scale)
      </p>
      <div className="histogram">
        {distribution.map((d, i) => {
          const logH = Math.log10(d.count + 1) / logMax * 100
          return (
            <div className="histogram-col" key={i}>
              <span className="histogram-count">{fmt(d.count)}</span>
              <div className="histogram-bar-wrap">
                <div
                  className="histogram-bar"
                  style={{
                    height: `${logH}%`,
                    background: d.appearances === 0 ? 'var(--system-orange)' : 'var(--system-blue)',
                  }}
                />
              </div>
              <span className="histogram-label">{d.appearances}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* Per-experience table */
function ExperienceTable({ experiences }: { experiences: Experience[] }) {
  return (
    <div style={{ marginBottom: '40px' }}>
      <h2 className="section-title">Per-Experience Pool</h2>
      <p style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)', marginBottom: '16px' }}>
        Pool size for each Show experience
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 'var(--text-sm)',
        }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--border)' }}>
              <th style={{ textAlign: 'left', padding: '8px 12px', color: 'var(--muted)', fontWeight: 500 }}>Experience</th>
              <th style={{ textAlign: 'right', padding: '8px 12px', color: 'var(--muted)', fontWeight: 500 }}>Pool</th>
              <th style={{ textAlign: 'right', padding: '8px 12px', color: 'var(--muted)', fontWeight: 500 }}>% of Collection</th>
              <th style={{ textAlign: 'left', padding: '8px 12px', color: 'var(--muted)', fontWeight: 500, width: '40%' }}></th>
            </tr>
          </thead>
          <tbody>
            {experiences.map((exp) => (
              <tr key={exp.name} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '8px 12px', fontWeight: 500 }}>{exp.name}</td>
                <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                  {fmt(exp.pool_size)}
                </td>
                <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                  {exp.pct_of_collection}%
                </td>
                <td style={{ padding: '8px 12px' }}>
                  <div style={{
                    height: '16px',
                    borderRadius: '8px',
                    background: 'var(--bg-secondary)',
                    overflow: 'hidden',
                  }}>
                    <div style={{
                      height: '100%',
                      width: `${exp.pct_of_collection}%`,
                      background: exp.pct_of_collection >= 80 ? 'var(--system-green)' :
                        exp.pct_of_collection >= 40 ? 'var(--system-blue)' : 'var(--system-orange)',
                      borderRadius: '8px',
                      transition: 'width 0.5s ease-out',
                    }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* Dimension bias chart */
function DimensionBias({ title, dimension }: { title: string; dimension: DimensionData }) {
  const keys = useMemo(() => {
    const allKeys = new Set([...Object.keys(dimension.full), ...Object.keys(dimension.curated)])
    return Array.from(allKeys)
      .filter(k => (dimension.full[k] || 0) >= 1 || (dimension.curated[k] || 0) >= 1)
      .sort((a, b) => (dimension.full[b] || 0) - (dimension.full[a] || 0))
      .slice(0, 10)
  }, [dimension])

  if (keys.length === 0) return null

  const maxPct = Math.max(
    ...keys.map(k => Math.max(dimension.full[k] || 0, dimension.curated[k] || 0)),
    1
  )

  return (
    <div style={{ marginBottom: '32px' }}>
      <h3 style={{
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        marginBottom: '12px',
        color: 'var(--fg)',
      }}>
        {title}
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {keys.map(key => {
          const fullPct = dimension.full[key] || 0
          const curPct = dimension.curated[key] || 0
          const diff = curPct - fullPct
          return (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{
                width: '120px',
                flexShrink: 0,
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-mono)',
                color: 'var(--muted)',
                textAlign: 'right',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {key}
              </span>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{
                    height: '8px',
                    width: `${(fullPct / maxPct) * 100}%`,
                    background: 'var(--system-blue)',
                    borderRadius: '4px',
                    opacity: 0.6,
                    minWidth: '2px',
                  }} />
                  <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--muted)' }}>
                    {fullPct.toFixed(1)}%
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{
                    height: '8px',
                    width: `${(curPct / maxPct) * 100}%`,
                    background: diff > 2 ? 'var(--system-green)' : diff < -2 ? 'var(--system-orange)' : 'var(--system-purple)',
                    borderRadius: '4px',
                    minWidth: '2px',
                  }} />
                  <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--muted)' }}>
                    {curPct.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
      <div style={{
        display: 'flex',
        gap: '16px',
        marginTop: '8px',
        fontSize: 'var(--text-xs)',
        color: 'var(--muted)',
      }}>
        <span><span style={{ display: 'inline-block', width: '10px', height: '6px', borderRadius: '3px', background: 'var(--system-blue)', opacity: 0.6, marginRight: '4px' }} />Full collection</span>
        <span><span style={{ display: 'inline-block', width: '10px', height: '6px', borderRadius: '3px', background: 'var(--system-purple)', marginRight: '4px' }} />Curated (in experiences)</span>
      </div>
    </div>
  )
}

export function CollectionCoveragePage() {
  const { data, loading, error } = useFetch<CoverageData>('/api/collection-coverage')

  if (loading) return <div className="main-content"><p style={{ color: 'var(--muted)' }}>Loading coverage...</p></div>
  if (error) return <div className="main-content"><p style={{ color: 'var(--system-red)' }}>Error: {error}</p></div>
  if (!data) return null

  const dimensionLabels: Record<string, string> = {
    camera: 'Camera',
    scene: 'Scene',
    time_of_day: 'Time of Day',
    style: 'Style',
    grading: 'Grading',
  }

  return (
    <div className="main-content">
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ marginBottom: '4px' }}>Collection Coverage</h1>
        <p style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
          How well the Show experiences represent the full archive
        </p>
      </div>

      <HeroStats data={data} />
      <DistributionChart distribution={data.distribution} />
      <ExperienceTable experiences={data.experiences} />

      {Object.keys(data.dimensions).length > 0 && (
        <div style={{ marginBottom: '40px' }}>
          <h2 className="section-title">Dimension Bias</h2>
          <p style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)', marginBottom: '20px' }}>
            Full collection vs curated (appearing in experiences) — reveals systematic over/under-representation
          </p>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
            gap: '24px',
          }}>
            {Object.entries(data.dimensions).map(([key, dim]) => (
              <DimensionBias key={key} title={dimensionLabels[key] || key} dimension={dim} />
            ))}
          </div>
        </div>
      )}

      <Footer />
    </div>
  )
}
