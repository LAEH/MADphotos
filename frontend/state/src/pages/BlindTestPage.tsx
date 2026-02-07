import { Footer } from '../components/layout/Footer'

export function BlindTestPage() {
  return (
    <>
      <h1 style={{
        fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700,
        letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-2)',
      }}>
        Blind Test
      </h1>
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-4)' }}>
        A/B enhancement comparison. Can you tell which is the AI-enhanced version? Coming soon.
      </p>
      <div style={{
        background: 'var(--card-bg)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 'var(--space-10)',
        textAlign: 'center', color: 'var(--muted)',
      }}>
        This experience will be ported from the existing blind-test.html implementation.
      </div>
      <Footer />
    </>
  )
}
