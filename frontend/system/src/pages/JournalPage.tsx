import { useFetch } from '../hooks/useFetch'
import { PageShell } from '../components/layout/PageShell'
import { Card } from '../components/layout/Card'

interface JournalData {
  html: string
}

export function JournalPage() {
  const { data, loading, error } = useFetch<JournalData>('/api/journal')

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading journal...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  return (
    <PageShell title="Journal de Bord">
      <Card>
        <div className="prose" dangerouslySetInnerHTML={{ __html: data.html }} />
      </Card>
    </PageShell>
  )
}
