import { useState, useMemo, useCallback, useEffect } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { Footer } from '../components/layout/Footer'

interface Neighbor {
  uuid: string
  thumb: string
  score: number
}

interface Anchor {
  uuid: string
  thumb: string
  display: string
  caption: string
  scene: string
  vibes: string[]
  neighbors: Record<string, Neighbor[]>
  agreement: {
    shared_2plus: number
    shared_3plus: number
    unique_neighbors: number
  }
}

interface AuditData {
  anchor_count: number
  neighbor_k: number
  models: string[]
  anchors: Anchor[]
}

type SortMode = 'default' | 'highest' | 'lowest'

function NeighborCard({ nb, highlight }: { nb: Neighbor; highlight: 'gold' | 'blue' | null }) {
  const borderColor = highlight === 'gold'
    ? 'var(--system-yellow)'
    : highlight === 'blue'
      ? 'var(--system-blue)'
      : 'transparent'

  return (
    <div style={{
      position: 'relative',
      borderRadius: '6px',
      border: `2px solid ${borderColor}`,
      overflow: 'hidden',
      background: 'var(--bg-secondary)',
    }}>
      <img
        src={imageUrl(nb.thumb)}
        alt=""
        loading="lazy"
        style={{
          width: '100%',
          aspectRatio: '4/3',
          objectFit: 'cover',
          display: 'block',
        }}
      />
      <div style={{
        position: 'absolute',
        bottom: '4px',
        right: '4px',
        background: 'rgba(0,0,0,0.7)',
        color: '#fff',
        fontSize: '10px',
        fontFamily: 'var(--font-mono)',
        padding: '1px 5px',
        borderRadius: '4px',
      }}>
        {nb.score.toFixed(2)}
      </div>
    </div>
  )
}

export function EmbeddingAuditPage() {
  const { data, loading, error } = useFetch<AuditData>('/api/embedding-audit')
  const [index, setIndex] = useState(0)
  const [sortMode, setSortMode] = useState<SortMode>('default')

  const sorted = useMemo(() => {
    if (!data) return []
    const anchors = [...data.anchors]
    if (sortMode === 'highest') {
      anchors.sort((a, b) => b.agreement.shared_3plus - a.agreement.shared_3plus)
    } else if (sortMode === 'lowest') {
      anchors.sort((a, b) => a.agreement.shared_3plus - b.agreement.shared_3plus)
    }
    return anchors
  }, [data, sortMode])

  const anchor = sorted[index] || null

  const prev = useCallback(() => setIndex(i => Math.max(0, i - 1)), [])
  const next = useCallback(() => setIndex(i => Math.min((sorted.length || 1) - 1, i + 1)), [sorted])

  useEffect(() => {
    setIndex(0)
  }, [sortMode])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') prev()
      else if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [prev, next])

  // Count how many models each neighbor UUID appears in
  const neighborAppearances = useMemo(() => {
    if (!anchor) return new Map<string, number>()
    const counts = new Map<string, number>()
    for (const model of Object.keys(anchor.neighbors)) {
      for (const nb of anchor.neighbors[model]) {
        counts.set(nb.uuid, (counts.get(nb.uuid) || 0) + 1)
      }
    }
    return counts
  }, [anchor])

  if (loading) return <div className="main-content"><p style={{ color: 'var(--muted)' }}>Loading embeddings...</p></div>
  if (error) return <div className="main-content"><p style={{ color: 'var(--system-red)' }}>Error: {error}</p></div>
  if (!data || data.anchor_count === 0) {
    return (
      <div className="main-content">
        <h1>Embedding Audit</h1>
        <p style={{ color: 'var(--muted)' }}>No vector data available. Run the embedding pipeline first.</p>
        <Footer />
      </div>
    )
  }

  return (
    <div className="main-content">
      <div style={{ marginBottom: '20px' }}>
        <h1 style={{ marginBottom: '4px' }}>Embedding Audit</h1>
        <p style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
          Per-model neighbor comparison across {data.anchor_count} anchors
        </p>
      </div>

      {/* Controls */}
      <div style={{
        display: 'flex',
        gap: '12px',
        alignItems: 'center',
        marginBottom: '20px',
        flexWrap: 'wrap',
      }}>
        <button
          onClick={prev}
          disabled={index === 0}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: index === 0 ? 'var(--muted)' : 'var(--fg)',
            cursor: index === 0 ? 'default' : 'pointer',
            fontSize: 'var(--text-sm)',
          }}
        >
          Prev
        </button>

        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-sm)',
          color: 'var(--muted)',
          minWidth: '80px',
          textAlign: 'center',
        }}>
          {index + 1} / {sorted.length}
        </span>

        <button
          onClick={next}
          disabled={index === sorted.length - 1}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: index === sorted.length - 1 ? 'var(--muted)' : 'var(--fg)',
            cursor: index === sorted.length - 1 ? 'default' : 'pointer',
            fontSize: 'var(--text-sm)',
          }}
        >
          Next
        </button>

        <div style={{ flex: 1 }} />

        <select
          value={sortMode}
          onChange={e => setSortMode(e.target.value as SortMode)}
          style={{
            padding: '6px 10px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--fg)',
            fontSize: 'var(--text-sm)',
          }}
        >
          <option value="default">Default Order</option>
          <option value="highest">Highest Agreement</option>
          <option value="lowest">Lowest Agreement</option>
        </select>
      </div>

      {anchor && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: '280px 1fr',
          gap: '24px',
          marginBottom: '40px',
        }}>
          {/* Anchor */}
          <div>
            <img
              src={imageUrl(anchor.display)}
              alt={anchor.caption}
              style={{
                width: '100%',
                borderRadius: '8px',
                background: '#000',
                marginBottom: '12px',
              }}
            />
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--fg)', marginBottom: '8px' }}>
              {anchor.caption}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', marginBottom: '4px' }}>
              Scene: {anchor.scene || '—'}
            </div>
            {anchor.vibes.length > 0 && (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', marginBottom: '8px' }}>
                Vibes: {anchor.vibes.join(', ')}
              </div>
            )}
            <div style={{
              padding: '8px 12px',
              borderRadius: '6px',
              background: 'var(--bg-secondary)',
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-mono)',
            }}>
              <div>3+ models agree: <strong>{anchor.agreement.shared_3plus}</strong></div>
              <div>2+ models agree: <strong>{anchor.agreement.shared_2plus}</strong></div>
              <div>Unique neighbors: <strong>{anchor.agreement.unique_neighbors}</strong></div>
            </div>

            {/* Legend */}
            <div style={{
              marginTop: '12px',
              fontSize: 'var(--text-xs)',
              color: 'var(--muted)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                <div style={{ width: '12px', height: '12px', border: '2px solid var(--system-yellow)', borderRadius: '3px' }} />
                <span>In 3+ models</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div style={{ width: '12px', height: '12px', border: '2px solid var(--system-blue)', borderRadius: '3px' }} />
                <span>In 2 models</span>
              </div>
            </div>
          </div>

          {/* Model columns */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${data.models.length}, 1fr)`,
            gap: '12px',
          }}>
            {data.models.map(model => (
              <div key={model}>
                <h4 style={{
                  margin: '0 0 8px',
                  fontSize: 'var(--text-xs)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: 'var(--muted)',
                  textAlign: 'center',
                  paddingBottom: '4px',
                  borderBottom: '1px solid var(--border)',
                }}>
                  {model}
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {(anchor.neighbors[model] || []).map(nb => {
                    const count = neighborAppearances.get(nb.uuid) || 0
                    const highlight = count >= 3 ? 'gold' as const : count >= 2 ? 'blue' as const : null
                    return <NeighborCard key={nb.uuid} nb={nb} highlight={highlight} />
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <Footer />
    </div>
  )
}
