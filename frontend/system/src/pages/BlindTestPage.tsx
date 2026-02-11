import { useState, useCallback, useMemo, type ImgHTMLAttributes } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { PageShell } from '../components/layout/PageShell'
import { Card } from '../components/layout/Card'

function FadeImg({ style, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}`} style={{ width: '100%', height: '100%', ...style }}>
      <img {...props} onLoad={() => setLoaded(true)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
    </div>
  )
}

interface BlindTestData {
  pairs: { uuid: string }[]
}

type Choice = 'a' | 'b' | null

export function BlindTestPage() {
  const { data, loading, error } = useFetch<BlindTestData>('/api/blind-test')
  const [index, setIndex] = useState(0)
  const [choice, setChoice] = useState<Choice>(null)
  const [revealed, setRevealed] = useState(false)
  const [score, setScore] = useState({ correct: 0, total: 0 })

  // Randomize which side shows the enhanced version
  const sides = useMemo(() => {
    if (!data) return []
    return data.pairs.map(() => Math.random() < 0.5)
  }, [data])

  const pair = data?.pairs[index]
  const enhancedIsLeft = sides[index]

  const handleChoice = useCallback((c: Choice) => {
    if (revealed) return
    setChoice(c)
    setRevealed(true)
    // 'a' is left, 'b' is right; enhanced version randomly placed
    const pickedEnhanced = (c === 'a' && enhancedIsLeft) || (c === 'b' && !enhancedIsLeft)
    setScore(s => ({
      correct: s.correct + (pickedEnhanced ? 1 : 0),
      total: s.total + 1,
    }))

    // Save result to localStorage
    const results = JSON.parse(localStorage.getItem('blind-test-results') || '[]')
    results.push({
      uuid: pair?.uuid,
      choice: c,
      pickedEnhanced,
      timestamp: new Date().toISOString(),
    })
    localStorage.setItem('blind-test-results', JSON.stringify(results))

    // Auto-advance after brief delay to show the reveal
    setTimeout(() => {
      if (index < (data?.pairs.length || 0) - 1) {
        setIndex(i => i + 1)
        setChoice(null)
        setRevealed(false)
      }
    }, 1200)
  }, [revealed, enhancedIsLeft, pair, index, data])

  const next = useCallback(() => {
    setIndex(i => Math.min(i + 1, (data?.pairs.length || 1) - 1))
    setChoice(null)
    setRevealed(false)
  }, [data])

  const prev = useCallback(() => {
    setIndex(i => Math.max(0, i - 1))
    setChoice(null)
    setRevealed(false)
  }, [])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading blind test...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data || !pair) return null

  const leftSrc = enhancedIsLeft
    ? imageUrl(`/ai_variants/blind_test/${pair.uuid}_enhanced_v1.jpg`)
    : imageUrl(`/ai_variants/blind_test/${pair.uuid}_original.jpg`)
  const rightSrc = enhancedIsLeft
    ? imageUrl(`/ai_variants/blind_test/${pair.uuid}_original.jpg`)
    : imageUrl(`/ai_variants/blind_test/${pair.uuid}_enhanced_v1.jpg`)

  const leftLabel = enhancedIsLeft ? 'Enhanced' : 'Original'
  const rightLabel = enhancedIsLeft ? 'Original' : 'Enhanced'

  return (
    <PageShell
      title="Blind Test"
      subtitle="Which one did I pick? One side is the original, the other has been enhanced. Click the one you think I originally curated."
    >
      <Card>
        <div style={{
          display: 'flex', gap: 'var(--space-6)', marginBottom: 'var(--space-4)',
          fontSize: 'var(--text-sm)', alignItems: 'center',
        }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
              {index + 1} / {data.pairs.length}
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)' }}>
              Round
            </span>
          </div>
          {score.total > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
                {score.correct}/{score.total}
              </span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)' }}>
                Preferred enhanced
              </span>
            </div>
          )}
        </div>

        {/* Comparison grid */}
        <div className="bt-grid">
          <div
            className="bt-cell"
            data-clickable={!revealed ? 'true' : undefined}
            onClick={() => handleChoice('a')}
            style={{
              outline: choice === 'a' ? '3px solid var(--system-blue)' : 'none',
              outlineOffset: '-3px',
            }}
          >
            <FadeImg
              src={leftSrc}
              alt="Option A"
              style={{ width: '100%', height: '100%' }}
            />
            <span style={{
              position: 'absolute', top: 'var(--space-2)', left: 'var(--space-2)',
              fontSize: 'var(--text-sm)', fontWeight: 700, padding: 'var(--space-1) var(--space-3)',
              borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
              background: 'rgba(0,0,0,0.5)', color: '#fff', zIndex: 2,
            }}>
              A
            </span>
            {revealed && (
              <span style={{
                position: 'absolute', bottom: 'var(--space-2)', left: 'var(--space-2)',
                fontSize: 'var(--text-sm)', fontWeight: 600, padding: 'var(--space-1) var(--space-3)',
                borderRadius: 'var(--radius-sm)', zIndex: 2,
                background: enhancedIsLeft ? 'var(--badge-green-bg)' : 'var(--badge-amber-bg)',
                color: enhancedIsLeft ? 'var(--badge-green-fg)' : 'var(--badge-amber-fg)',
              }}>
                {leftLabel}
              </span>
            )}
          </div>
          <div
            className="bt-cell"
            data-clickable={!revealed ? 'true' : undefined}
            onClick={() => handleChoice('b')}
            style={{
              outline: choice === 'b' ? '3px solid var(--system-blue)' : 'none',
              outlineOffset: '-3px',
            }}
          >
            <FadeImg
              src={rightSrc}
              alt="Option B"
              style={{ width: '100%', height: '100%' }}
            />
            <span style={{
              position: 'absolute', top: 'var(--space-2)', right: 'var(--space-2)',
              fontSize: 'var(--text-sm)', fontWeight: 700, padding: 'var(--space-1) var(--space-3)',
              borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
              background: 'rgba(0,0,0,0.5)', color: '#fff', zIndex: 2,
            }}>
              B
            </span>
            {revealed && (
              <span style={{
                position: 'absolute', bottom: 'var(--space-2)', right: 'var(--space-2)',
                fontSize: 'var(--text-sm)', fontWeight: 600, padding: 'var(--space-1) var(--space-3)',
                borderRadius: 'var(--radius-sm)', zIndex: 2,
                background: !enhancedIsLeft ? 'var(--badge-green-bg)' : 'var(--badge-amber-bg)',
                color: !enhancedIsLeft ? 'var(--badge-green-fg)' : 'var(--badge-amber-fg)',
              }}>
                {rightLabel}
              </span>
            )}
          </div>
        </div>

        {/* Status */}
        {!revealed && (
          <div style={{ marginTop: 'var(--space-4)', fontSize: 'var(--text-sm)', color: 'var(--muted)', textAlign: 'center' }}>
            Click the photo you think I originally picked
          </div>
        )}
        {revealed && index === data.pairs.length - 1 && (
          <div style={{ marginTop: 'var(--space-4)', fontSize: 'var(--text-base)', color: 'var(--fg)', textAlign: 'center', fontWeight: 600 }}>
            Test complete! You preferred enhanced {score.correct}/{score.total} times
          </div>
        )}
      </Card>
    </PageShell>
  )
}
