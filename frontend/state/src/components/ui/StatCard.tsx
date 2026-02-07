interface Props {
  label: string
  value: string | number
  detail?: string
  color?: string
}

export function StatCard({ label, value, detail, color }: Props) {
  return (
    <div style={{
      background: 'var(--card-bg)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      padding: 'var(--space-4) var(--space-5)',
      boxShadow: 'var(--shadow-sm)',
    }}>
      <div style={{
        fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-caps)', color: color || 'var(--muted)',
        marginBottom: 2,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 'var(--text-2xl)', fontWeight: 700,
        fontFamily: 'var(--font-display)',
        letterSpacing: 'var(--tracking-tight)',
        color: 'var(--fg)',
      }}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
      {detail && (
        <div style={{
          fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)', marginTop: 2,
        }}>
          {detail}
        </div>
      )}
    </div>
  )
}
