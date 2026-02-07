import { useState, useCallback, useMemo, type ImgHTMLAttributes } from 'react'
import { useFetch } from '../hooks/useFetch'
import { imageUrl } from '../config'
import { Footer } from '../components/layout/Footer'

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
  }, [revealed, enhancedIsLeft])

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
    <>
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700,
          letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-2)',
        }}>
          Blind Test
        </h1>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)' }}>
          Can you spot the AI-enhanced photo? One side is the original, the other has been
          through our 6-step enhancement pipeline. Click the one you think looks better.
        </p>
        <div style={{
          display: 'flex', gap: 'var(--space-6)', marginTop: 'var(--space-4)',
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
                Enhanced picked
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Comparison grid */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px',
        borderRadius: 'var(--radius-lg)', overflow: 'hidden',
        border: '1px solid var(--border)', marginBottom: 'var(--space-4)',
      }}>
        <div
          onClick={() => handleChoice('a')}
          style={{
            position: 'relative', cursor: revealed ? 'default' : 'pointer',
            aspectRatio: '1', overflow: 'hidden',
            outline: choice === 'a' ? '3px solid var(--system-blue)' : 'none',
            outlineOffset: '-3px',
          }}
        >
          <FadeImg
            src={leftSrc}
            alt="Option A"
            style={{ aspectRatio: '1' }}
          />
          <span style={{
            position: 'absolute', top: 'var(--space-2)', left: 'var(--space-2)',
            fontSize: 'var(--text-xs)', fontWeight: 700, padding: '2px var(--space-2)',
            borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
            background: 'rgba(0,0,0,0.5)', color: '#fff', zIndex: 2,
          }}>
            A
          </span>
          {revealed && (
            <span style={{
              position: 'absolute', bottom: 'var(--space-2)', left: 'var(--space-2)',
              fontSize: 'var(--text-xs)', fontWeight: 600, padding: '2px var(--space-2)',
              borderRadius: 'var(--radius-sm)', zIndex: 2,
              background: enhancedIsLeft ? 'var(--badge-green-bg)' : 'var(--badge-amber-bg)',
              color: enhancedIsLeft ? 'var(--badge-green-fg)' : 'var(--badge-amber-fg)',
            }}>
              {leftLabel}
            </span>
          )}
        </div>
        <div
          onClick={() => handleChoice('b')}
          style={{
            position: 'relative', cursor: revealed ? 'default' : 'pointer',
            aspectRatio: '1', overflow: 'hidden',
            outline: choice === 'b' ? '3px solid var(--system-blue)' : 'none',
            outlineOffset: '-3px',
          }}
        >
          <FadeImg
            src={rightSrc}
            alt="Option B"
            style={{ aspectRatio: '1' }}
          />
          <span style={{
            position: 'absolute', top: 'var(--space-2)', right: 'var(--space-2)',
            fontSize: 'var(--text-xs)', fontWeight: 700, padding: '2px var(--space-2)',
            borderRadius: 'var(--radius-sm)', backdropFilter: 'blur(12px)',
            background: 'rgba(0,0,0,0.5)', color: '#fff', zIndex: 2,
          }}>
            B
          </span>
          {revealed && (
            <span style={{
              position: 'absolute', bottom: 'var(--space-2)', right: 'var(--space-2)',
              fontSize: 'var(--text-xs)', fontWeight: 600, padding: '2px var(--space-2)',
              borderRadius: 'var(--radius-sm)', zIndex: 2,
              background: !enhancedIsLeft ? 'var(--badge-green-bg)' : 'var(--badge-amber-bg)',
              color: !enhancedIsLeft ? 'var(--badge-green-fg)' : 'var(--badge-amber-fg)',
            }}>
              {rightLabel}
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'center' }}>
        <button onClick={prev} disabled={index === 0} style={{
          background: 'var(--card-bg)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)', padding: 'var(--space-2) var(--space-4)',
          cursor: index === 0 ? 'default' : 'pointer', color: index === 0 ? 'var(--muted)' : 'var(--fg)',
          fontFamily: 'var(--font-sans)', fontSize: 'var(--text-sm)',
          opacity: index === 0 ? 0.4 : 1,
        }}>
          Previous
        </button>
        {revealed && (
          <button onClick={next} disabled={index === data.pairs.length - 1} style={{
            background: 'var(--system-blue)', border: 'none',
            borderRadius: 'var(--radius-sm)', padding: 'var(--space-2) var(--space-5)',
            cursor: 'pointer', color: '#fff', fontWeight: 600,
            fontFamily: 'var(--font-sans)', fontSize: 'var(--text-sm)',
          }}>
            Next
          </button>
        )}
        {!revealed && (
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', alignSelf: 'center' }}>
            Click the photo you think is enhanced
          </span>
        )}
      </div>

      <Footer />
    </>
  )
}
