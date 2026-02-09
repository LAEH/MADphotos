import { useState, useMemo } from 'react'
import { useFetch } from '../hooks/useFetch'
import { Footer } from '../components/layout/Footer'

interface Column {
  name: string
  type: string
  pk: boolean
}

interface TableInfo {
  name: string
  rows: number
  columns: Column[]
  col_count: number
  model: string
  category: string
  description: string
  coverage: number | null
  distinct_images: number | null
  samples: Record<string, (string | number)[]>
}

interface SchemaData {
  db_path: string
  db_size: number
  total_images: number
  table_count: number
  total_rows: number
  categories: Record<string, { count: number; rows: number; tables: string[] }>
  tables: TableInfo[]
}

function fmt(n: number): string {
  return n.toLocaleString()
}

function fmtBytes(bytes: number): string {
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB'
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB'
  return (bytes / 1e3).toFixed(0) + ' KB'
}

const categoryLabels: Record<string, { label: string; color: string; order: number }> = {
  core: { label: 'Core', color: 'var(--system-gray)', order: 0 },
  v1_signal: { label: 'V1 Signals', color: 'var(--system-blue)', order: 1 },
  v2_signal: { label: 'V2 Signals', color: 'var(--system-purple)', order: 2 },
  api_signal: { label: 'API Signals', color: 'var(--system-orange)', order: 3 },
  pipeline: { label: 'Pipeline', color: 'var(--system-green)', order: 4 },
  other: { label: 'Other', color: 'var(--system-gray)', order: 5 },
}

function CategoryPill({ category }: { category: string }) {
  const cat = categoryLabels[category] || categoryLabels.other
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 8px',
      borderRadius: '8px',
      fontSize: '10px',
      fontFamily: 'var(--font-mono)',
      background: cat.color,
      color: '#fff',
      textTransform: 'uppercase',
      letterSpacing: '0.04em',
      whiteSpace: 'nowrap',
    }}>
      {cat.label}
    </span>
  )
}

function ModelPill({ model }: { model: string }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 6px',
      borderRadius: '6px',
      fontSize: '9px',
      fontFamily: 'var(--font-mono)',
      background: 'var(--bg-secondary)',
      color: 'var(--muted)',
      whiteSpace: 'nowrap',
    }}>
      {model}
    </span>
  )
}

function CoverageBar({ coverage }: { coverage: number | null }) {
  if (coverage === null) return <span style={{ color: 'var(--muted)', fontSize: 'var(--text-xs)' }}>—</span>
  const color = coverage >= 95 ? 'var(--system-green)' : coverage >= 50 ? 'var(--system-blue)' : 'var(--system-orange)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <div style={{
        width: '60px',
        height: '4px',
        borderRadius: '2px',
        background: 'var(--bg-secondary)',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${coverage}%`,
          background: color,
          borderRadius: '2px',
        }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--muted)' }}>
        {coverage}%
      </span>
    </div>
  )
}

function TableCard({ table, expanded, onToggle }: { table: TableInfo; expanded: boolean; onToggle: () => void }) {
  return (
    <div
      style={{
        background: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        overflow: 'hidden',
        transition: 'border-color 0.2s',
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = categoryLabels[table.category]?.color || 'var(--border)')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      {/* Header — always visible */}
      <div
        onClick={onToggle}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '12px 16px',
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-sm)',
          fontWeight: 600,
          color: 'var(--fg)',
          flex: 1,
          minWidth: 0,
        }}>
          {table.name}
        </span>

        <CoverageBar coverage={table.coverage} />

        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-xs)',
          color: 'var(--muted)',
          minWidth: '60px',
          textAlign: 'right',
        }}>
          {fmt(table.rows)} rows
        </span>

        <CategoryPill category={table.category} />

        <span style={{
          fontSize: '12px',
          color: 'var(--muted)',
          transition: 'transform 0.2s',
          transform: expanded ? 'rotate(180deg)' : 'rotate(0)',
        }}>
          ▾
        </span>
      </div>

      {/* Description line */}
      <div style={{
        padding: '0 16px 8px',
        fontSize: 'var(--text-xs)',
        color: 'var(--muted)',
        lineHeight: 1.4,
        display: 'flex',
        gap: '8px',
        alignItems: 'baseline',
      }}>
        <ModelPill model={table.model} />
        <span>{table.description}</span>
      </div>

      {/* Expanded: columns + samples */}
      {expanded && (
        <div style={{
          borderTop: '1px solid var(--border)',
          padding: '12px 16px',
        }}>
          {/* Column table */}
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 'var(--text-xs)',
            fontFamily: 'var(--font-mono)',
          }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ textAlign: 'left', padding: '4px 8px', color: 'var(--muted)', fontWeight: 500 }}>Column</th>
                <th style={{ textAlign: 'left', padding: '4px 8px', color: 'var(--muted)', fontWeight: 500 }}>Type</th>
                <th style={{ textAlign: 'left', padding: '4px 8px', color: 'var(--muted)', fontWeight: 500 }}>Sample Values</th>
              </tr>
            </thead>
            <tbody>
              {table.columns.map(col => (
                <tr key={col.name} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{
                    padding: '4px 8px',
                    color: col.pk ? 'var(--system-blue)' : 'var(--fg)',
                    fontWeight: col.pk ? 600 : 400,
                  }}>
                    {col.name}
                    {col.pk && <span style={{ fontSize: '9px', marginLeft: '4px', color: 'var(--system-blue)' }}>PK</span>}
                  </td>
                  <td style={{ padding: '4px 8px', color: 'var(--muted)' }}>
                    {col.type || 'TEXT'}
                  </td>
                  <td style={{ padding: '4px 8px', color: 'var(--muted)' }}>
                    {(table.samples[col.name] || []).map((v, i) => (
                      <span key={i}>
                        {i > 0 && <span style={{ opacity: 0.3 }}> · </span>}
                        <span style={{ color: typeof v === 'number' ? 'var(--system-blue)' : 'var(--fg)', opacity: 0.7 }}>
                          {String(v)}
                        </span>
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Stats */}
          <div style={{
            display: 'flex',
            gap: '16px',
            marginTop: '12px',
            fontSize: 'var(--text-xs)',
            color: 'var(--muted)',
          }}>
            <span>{table.col_count} columns</span>
            {table.distinct_images !== null && (
              <span>{fmt(table.distinct_images)} distinct images</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

type FilterCategory = 'all' | 'core' | 'v1_signal' | 'v2_signal' | 'api_signal' | 'pipeline'

export function DatabasePage() {
  const { data, loading, error } = useFetch<SchemaData>('/api/schema')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [filter, setFilter] = useState<FilterCategory>('all')
  const [search, setSearch] = useState('')

  const toggle = (name: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const expandAll = () => {
    if (!data) return
    setExpanded(new Set(data.tables.map(t => t.name)))
  }

  const collapseAll = () => setExpanded(new Set())

  const filtered = useMemo(() => {
    if (!data) return []
    return data.tables
      .filter(t => filter === 'all' || t.category === filter)
      .filter(t => {
        if (!search) return true
        const q = search.toLowerCase()
        return t.name.includes(q) || t.model.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q) ||
          t.columns.some(c => c.name.includes(q))
      })
      .sort((a, b) => {
        const oa = categoryLabels[a.category]?.order ?? 9
        const ob = categoryLabels[b.category]?.order ?? 9
        if (oa !== ob) return oa - ob
        return a.name.localeCompare(b.name)
      })
  }, [data, filter, search])

  if (loading) return <div className="main-content"><p style={{ color: 'var(--muted)' }}>Loading schema...</p></div>
  if (error) return <div className="main-content"><p style={{ color: 'var(--system-red)' }}>Error: {error}</p></div>
  if (!data) return null

  const catCounts = Object.entries(data.categories).sort(
    (a, b) => (categoryLabels[a[0]]?.order ?? 9) - (categoryLabels[b[0]]?.order ?? 9)
  )

  return (
    <div className="main-content">
      {/* Hero */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ marginBottom: '4px' }}>Database</h1>
        <p style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
          {data.table_count} tables · {fmt(data.total_rows)} total rows · {fmtBytes(data.db_size)}
        </p>
      </div>

      {/* Hero stats */}
      <div className="hero-stats" style={{ marginBottom: '32px' }}>
        <div className="hero-stat">
          <span className="hero-stat-num">{fmt(data.total_images)}</span>
          <span className="hero-stat-label">Images</span>
        </div>
        <div className="hero-stat">
          <span className="hero-stat-num">{data.table_count}</span>
          <span className="hero-stat-label">Tables</span>
        </div>
        <div className="hero-stat">
          <span className="hero-stat-num">{fmt(data.total_rows)}</span>
          <span className="hero-stat-label">Rows</span>
        </div>
        <div className="hero-stat">
          <span className="hero-stat-num">{fmtBytes(data.db_size)}</span>
          <span className="hero-stat-label">Size</span>
        </div>
      </div>

      {/* Category summary cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: '12px',
        marginBottom: '32px',
      }}>
        {catCounts.map(([cat, info]) => {
          const meta = categoryLabels[cat] || categoryLabels.other
          return (
            <div
              key={cat}
              onClick={() => setFilter(filter === cat ? 'all' : cat as FilterCategory)}
              style={{
                padding: '12px 16px',
                borderRadius: '10px',
                background: filter === cat ? meta.color : 'var(--card-bg)',
                border: `1px solid ${filter === cat ? meta.color : 'var(--border)'}`,
                cursor: 'pointer',
                transition: 'all 0.2s',
                color: filter === cat ? '#fff' : 'var(--fg)',
              }}
            >
              <div style={{
                fontSize: 'var(--text-xs)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                opacity: 0.8,
                marginBottom: '4px',
              }}>
                {meta.label}
              </div>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-lg)',
                fontWeight: 600,
              }}>
                {info.count} tables
              </div>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                opacity: 0.7,
              }}>
                {fmt(info.rows)} rows
              </div>
            </div>
          )
        })}
      </div>

      {/* How it works */}
      <div style={{
        padding: '16px 20px',
        borderRadius: '10px',
        background: 'var(--card-bg)',
        border: '1px solid var(--border)',
        marginBottom: '32px',
        fontSize: 'var(--text-sm)',
        lineHeight: 1.6,
        color: 'var(--muted)',
      }}>
        <h3 style={{ margin: '0 0 8px', color: 'var(--fg)', fontSize: 'var(--text-sm)' }}>How it works</h3>
        <p style={{ margin: '0 0 8px' }}>
          Every image in the archive gets a UUID. The <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', padding: '1px 4px', borderRadius: '3px', background: 'var(--bg-secondary)' }}>images</code> table
          is the master — one row per photograph. All signal tables link back via <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', padding: '1px 4px', borderRadius: '3px', background: 'var(--bg-secondary)' }}>image_uuid</code>.
        </p>
        <p style={{ margin: '0 0 8px' }}>
          <strong style={{ color: 'var(--fg)' }}>V1 Signals</strong> were the first wave — EXIF, BLIP captions, YOLOv8 objects, face detection, aesthetic scores, depth, colors, scene/style classification, Gemini semantic analysis.
        </p>
        <p style={{ margin: '0 0 8px' }}>
          <strong style={{ color: 'var(--fg)' }}>V2 Signals</strong> came next — better quality scoring (TOPIQ+MUSIQ), open-vocabulary detection (Grounding DINO, CLIP tags), segmentation (SAM 2.1), pose estimation, saliency maps, face identity clustering, location geocoding.
        </p>
        <p style={{ margin: 0 }}>
          <strong style={{ color: 'var(--fg)' }}>Pipeline tables</strong> track rendering, enhancement, and uploads.
          All signals feed into the Show experiences and the State dashboard. The richer the signals, the more creative possibilities unlock.
        </p>
      </div>

      {/* Filter + search bar */}
      <div style={{
        display: 'flex',
        gap: '12px',
        alignItems: 'center',
        marginBottom: '16px',
        flexWrap: 'wrap',
      }}>
        <input
          type="text"
          placeholder="Search tables, columns, models..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            padding: '6px 12px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--fg)',
            fontSize: 'var(--text-sm)',
            flex: 1,
            minWidth: '200px',
          }}
        />
        <button
          onClick={expandAll}
          style={{
            padding: '6px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--fg)',
            cursor: 'pointer',
            fontSize: 'var(--text-xs)',
          }}
        >
          Expand All
        </button>
        <button
          onClick={collapseAll}
          style={{
            padding: '6px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--fg)',
            cursor: 'pointer',
            fontSize: 'var(--text-xs)',
          }}
        >
          Collapse All
        </button>
        <span style={{ color: 'var(--muted)', fontSize: 'var(--text-xs)' }}>
          {filtered.length} of {data.table_count} tables
        </span>
      </div>

      {/* Table cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '40px' }}>
        {filtered.map(table => (
          <TableCard
            key={table.name}
            table={table}
            expanded={expanded.has(table.name)}
            onToggle={() => toggle(table.name)}
          />
        ))}
      </div>

      <Footer />
    </div>
  )
}
