import { useFetch } from '../hooks/useFetch'
import { PageShell } from '../components/layout/PageShell'
import { Card } from '../components/layout/Card'

interface InstructionsData {
  html: string
}

export function InstructionsPage() {
  const { data, loading, error } = useFetch<InstructionsData>('/api/instructions')

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading instructions...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  return (
    <PageShell title="System Instructions">
      <Card>
        <div className="prose" dangerouslySetInnerHTML={{ __html: data.html }} />
      </Card>
    </PageShell>
  )
}
