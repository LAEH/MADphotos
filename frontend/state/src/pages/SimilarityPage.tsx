import { Footer } from '../components/layout/Footer'

export function SimilarityPage() {
  return (
    <>
      <h1 style={{
        fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700,
        letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-2)',
      }}>
        Similarity
      </h1>
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-4)' }}>
        Vector-space nearest neighbors across three embedding models. Coming soon.
      </p>
      <div style={{
        background: 'var(--card-bg)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 'var(--space-10)',
        textAlign: 'center', color: 'var(--muted)',
      }}>
        This experience will be ported from the existing drift.html implementation.
      </div>
      <Footer />
    </>
  )
}
