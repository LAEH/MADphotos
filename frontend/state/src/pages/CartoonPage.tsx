import { useState, useMemo } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { FilterBar } from '../components/ui/FilterBar'
import { Footer } from '../components/layout/Footer'

interface CartoonPair {
  uuid: string
  variant_uuid: string
  category: string
  subcategory: string
  caption: string
}

interface CartoonData {
  pairs: CartoonPair[]
}

export function CartoonPage() {
  const { data, loading, error } = useFetch<CartoonData>('/api/cartoon')
  const [filter, setFilter] = useState('all')

  const categories = useMemo(() => {
    if (!data) return []
    const counts: Record<string, number> = {}
    data.pairs.forEach(p => {
      const key = `${p.category}/${p.subcategory}`
      counts[key] = (counts[key] || 0) + 1
    })
    return [
      { key: 'all', label: 'All', count: data.pairs.length },
      ...Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .map(([key, count]) => ({ key, label: key, count })),
    ]
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    if (filter === 'all') return data.pairs
    return data.pairs.filter(p => `${p.category}/${p.subcategory}` === filter)
  }, [data, filter])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading cartoon pairs...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  const analogCount = data.pairs.filter(p => p.category === 'Analog').length
  const digitalCount = data.pairs.filter(p => p.category === 'Digital').length

  return (
    <>
      <div style={{ marginBottom: 'var(--space-8)' }}>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700,
          letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-2)',
        }}>
          Cartoon Variants
        </h1>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)' }}>
          Imagen 3 cel-shaded illustration transforms of curated photos
        </p>
        <div style={{
          display: 'flex', gap: 'var(--space-6)', margin: 'var(--space-4) 0',
          fontSize: 'var(--text-sm)',
        }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>{data.pairs.length}</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)' }}>Pairs</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>{analogCount}</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)' }}>Analog</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>{digitalCount}</span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)' }}>Digital</span>
          </div>
        </div>
      </div>

      <FilterBar items={categories} active={filter} onSelect={setFilter} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 'var(--space-8)' }}>
        {filtered.map(pair => (
          <div key={pair.uuid} style={{
            background: 'var(--card-bg)', borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)', overflow: 'hidden',
            transition: 'box-shadow var(--duration-fast)',
          }}>
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr',
              position: 'relative',
            }}>
              <div style={{ position: 'relative', overflow: 'hidden', aspectRatio: '1', background: 'var(--hover-overlay)' }}>
                <img
                  src={imageUrl(`/rendered/display/jpeg/${pair.uuid}.jpg`)}
                  alt="Original"
                  loading="lazy"
                  style={{ width: '100%', height: '100%', objectFit: 'cover', transition: 'transform 0.3s' }}
                />
                <span style={{
                  position: 'absolute', bottom: 'var(--space-2)', left: 'var(--space-2)',
                  fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase',
                  letterSpacing: 'var(--tracking-caps)', padding: '2px var(--space-2)',
                  borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
                  background: 'rgba(0,0,0,0.5)', color: '#fff',
                }}>
                  Original
                </span>
              </div>
              <div style={{ position: 'relative', overflow: 'hidden', aspectRatio: '1', background: 'var(--hover-overlay)' }}>
                <img
                  src={imageUrl(`/ai_variants/cartoon/${pair.category}/${pair.subcategory}/${pair.variant_uuid}.jpg`)}
                  alt="Cartoon"
                  loading="lazy"
                  style={{ width: '100%', height: '100%', objectFit: 'cover', transition: 'transform 0.3s' }}
                />
                <span style={{
                  position: 'absolute', bottom: 'var(--space-2)', left: 'var(--space-2)',
                  fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase',
                  letterSpacing: 'var(--tracking-caps)', padding: '2px var(--space-2)',
                  borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
                  background: 'linear-gradient(135deg, rgba(175,82,222,0.7), rgba(255,45,85,0.7))', color: '#fff',
                }}>
                  Cartoon
                </span>
              </div>
              <div style={{
                position: 'absolute', top: 0, left: '50%', width: 2, height: '100%',
                background: 'var(--bg)', zIndex: 1,
              }} />
            </div>
            <div style={{ padding: 'var(--space-3) var(--space-4)' }}>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--fg-secondary)', lineHeight: 'var(--leading-relaxed)' }}>
                {pair.caption}
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>
                {pair.category} / {pair.subcategory}
              </div>
            </div>
          </div>
        ))}
      </div>

      <Footer />
    </>
  )
}
