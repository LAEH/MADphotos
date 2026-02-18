import { useState, useMemo, useCallback, type ImgHTMLAttributes } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { FilterBar } from '../components/ui/FilterBar'
import { PageShell } from '../components/layout/PageShell'

function FadeImg({ style, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}`} style={{ width: '100%', height: '100%', ...style }}>
      <img {...props} onLoad={() => setLoaded(true)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
    </div>
  )
}

interface CartoonPair {
  uuid: string
  variant_uuid: string
  type: string
  category: string
  subcategory: string
  caption: string
  cartoon_style: string
  review: string | null
}

interface CartoonData {
  pairs: CartoonPair[]
  accepted: number
  rejected: number
}

function variantImagePath(pair: CartoonPair) {
  const folder = pair.type === 'gemma_cartoon' ? 'gemma_cartoon' : 'cartoon'
  return `/ai_variants/${folder}/${pair.category}/${pair.subcategory}/${pair.variant_uuid}.jpg`
}

export function CartoonPage() {
  const { data, loading, error } = useFetch<CartoonData>('/api/cartoons')
  const [filter, setFilter] = useState('unreviewed')
  const [reviews, setReviews] = useState<Record<string, string>>({})
  const [dismissing, setDismissing] = useState<Set<string>>(new Set())

  const getReview = useCallback((pair: CartoonPair) => {
    return reviews[pair.variant_uuid] ?? pair.review
  }, [reviews])

  const handleReview = useCallback(async (variantId: string, status: string) => {
    // Animate out first
    setDismissing(prev => new Set(prev).add(variantId))
    // Wait for animation, then update state
    setTimeout(() => {
      setReviews(prev => ({ ...prev, [variantId]: status }))
      setDismissing(prev => {
        const next = new Set(prev)
        next.delete(variantId)
        return next
      })
    }, 350)
    try {
      await fetch('/api/cartoon/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant_id: variantId, status }),
      })
    } catch {
      setReviews(prev => {
        const next = { ...prev }
        delete next[variantId]
        return next
      })
    }
  }, [])

  const categories = useMemo(() => {
    if (!data) return []
    return [
      { key: 'unreviewed', label: 'Unreviewed', count: data.pairs.filter(p => !getReview(p)).length },
      { key: 'accepted', label: 'Accepted', count: data.pairs.filter(p => getReview(p) === 'accepted').length },
      { key: 'rejected', label: 'Rejected', count: data.pairs.filter(p => getReview(p) === 'rejected').length },
      { key: 'all', label: 'All', count: data.pairs.length },
    ]
  }, [data, getReview])

  const filtered = useMemo(() => {
    if (!data) return []
    if (filter === 'all') return data.pairs
    if (filter === 'unreviewed') return data.pairs.filter(p => !getReview(p))
    if (filter === 'accepted') return data.pairs.filter(p => getReview(p) === 'accepted')
    if (filter === 'rejected') return data.pairs.filter(p => getReview(p) === 'rejected')
    return data.pairs
  }, [data, filter, getReview])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading cartoons...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  return (
    <PageShell title="Cartoon" subtitle="Imagen 3">
      <FilterBar items={categories} active={filter} onSelect={setFilter} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 'var(--space-6)' }}>
        {filtered.map(pair => {
          const review = getReview(pair)
          const isDismissing = dismissing.has(pair.variant_uuid)
          return (
            <div key={pair.variant_uuid} style={{
              background: 'var(--card-bg)', borderRadius: 'var(--radius-lg)',
              border: `2px solid ${review === 'accepted' ? 'var(--system-green)' : review === 'rejected' ? 'var(--system-red)' : 'var(--border)'}`,
              overflow: 'hidden',
              opacity: isDismissing ? 0 : 1,
              maxHeight: isDismissing ? '0px' : '2000px',
              marginBottom: isDismissing ? '-24px' : undefined,
              transition: 'opacity 0.3s ease, max-height 0.35s ease, margin-bottom 0.35s ease',
            }}>
              <div className="cartoon-pair-grid">
                <div style={{ position: 'relative', overflow: 'hidden', aspectRatio: '1' }}>
                  <FadeImg
                    src={imageUrl(`/rendered/display/jpeg/${pair.uuid}.jpg`)}
                    alt="Original"
                    loading="lazy"
                    style={{ aspectRatio: '1', width: '100%', height: '100%' }}
                  />
                  <span style={{
                    position: 'absolute', bottom: 'var(--space-2)', left: 'var(--space-2)',
                    fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase',
                    letterSpacing: 'var(--tracking-caps)', padding: 'var(--space-1) var(--space-2)',
                    borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
                    background: 'rgba(0,0,0,0.5)', color: '#fff', zIndex: 2,
                  }}>
                    Original
                  </span>
                </div>
                <div style={{ position: 'relative', overflow: 'hidden', aspectRatio: '1' }}>
                  <FadeImg
                    src={imageUrl(variantImagePath(pair))}
                    alt="Cartoon"
                    loading="lazy"
                    style={{ aspectRatio: '1', width: '100%', height: '100%' }}
                  />
                  <span style={{
                    position: 'absolute', bottom: 'var(--space-2)', left: 'var(--space-2)',
                    fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase',
                    letterSpacing: 'var(--tracking-caps)', padding: 'var(--space-1) var(--space-2)',
                    borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
                    background: pair.type === 'gemma_cartoon'
                      ? 'linear-gradient(135deg, rgba(52,199,89,0.7), rgba(0,122,255,0.7))'
                      : 'linear-gradient(135deg, rgba(175,82,222,0.7), rgba(255,45,85,0.7))',
                    color: '#fff', zIndex: 2,
                  }}>
                    {pair.type === 'gemma_cartoon' ? 'Gemma' : 'Cartoon'}
                  </span>
                </div>
                <div className="cartoon-divider" />
              </div>

              {/* Footer: caption + review buttons */}
              <div style={{
                padding: 'var(--space-3) var(--space-4)',
                display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
              }}>
                <div style={{ flex: 1 }}>
                  {pair.cartoon_style && (
                    <div style={{
                      fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--system-blue)',
                      marginBottom: 'var(--space-1)', textTransform: 'uppercase',
                      letterSpacing: 'var(--tracking-caps)',
                    }}>
                      {pair.cartoon_style}
                    </div>
                  )}
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--fg-secondary)', lineHeight: 'var(--leading-relaxed)' }}>
                    {pair.caption}
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>
                    {pair.category} / {pair.subcategory}
                  </div>
                </div>

                {/* Accept / Reject buttons */}
                <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                  <button
                    onClick={() => handleReview(pair.variant_uuid, 'accepted')}
                    style={{
                      width: '44px', height: '44px', borderRadius: '50%',
                      border: 'none', cursor: 'pointer',
                      background: review === 'accepted' ? 'var(--system-green)' : 'var(--surface)',
                      color: review === 'accepted' ? '#fff' : 'var(--system-green)',
                      fontSize: '22px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      transition: 'background 0.2s, color 0.2s, transform 0.15s',
                    }}
                    onMouseDown={e => (e.currentTarget.style.transform = 'scale(0.9)')}
                    onMouseUp={e => (e.currentTarget.style.transform = '')}
                    onMouseLeave={e => (e.currentTarget.style.transform = '')}
                    title="Accept"
                  >
                    &#10003;
                  </button>
                  <button
                    onClick={() => handleReview(pair.variant_uuid, 'rejected')}
                    style={{
                      width: '44px', height: '44px', borderRadius: '50%',
                      border: 'none', cursor: 'pointer',
                      background: review === 'rejected' ? 'var(--system-red)' : 'var(--surface)',
                      color: review === 'rejected' ? '#fff' : 'var(--system-red)',
                      fontSize: '22px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      transition: 'background 0.2s, color 0.2s, transform 0.15s',
                    }}
                    onMouseDown={e => (e.currentTarget.style.transform = 'scale(0.9)')}
                    onMouseUp={e => (e.currentTarget.style.transform = '')}
                    onMouseLeave={e => (e.currentTarget.style.transform = '')}
                    title="Reject"
                  >
                    &#10005;
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '60px 20px' }}>
          {filter === 'unreviewed' ? 'All done! Every cartoon has been reviewed.' : 'No cartoons match this filter.'}
        </p>
      )}
    </PageShell>
  )
}
