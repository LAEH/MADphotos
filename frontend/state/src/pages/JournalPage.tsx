import { useFetch } from '../hooks/useFetch'
import { Footer } from '../components/layout/Footer'

interface JournalData {
  html: string
}

export function JournalPage() {
  const { data, loading, error } = useFetch<JournalData>('/api/journal')

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading journal...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  return (
    <>
      <h1 style={{
        fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700,
        letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-2)',
      }}>
        Journal de Bord
      </h1>
      <div className="prose" dangerouslySetInnerHTML={{ __html: data.html }} />
      <Footer />
    </>
  )
}
