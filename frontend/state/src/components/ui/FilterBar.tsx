interface Props {
  items: { key: string; label: string; count?: number }[]
  active: string
  onSelect: (key: string) => void
}

export function FilterBar({ items, active, onSelect }: Props) {
  return (
    <div style={{
      display: 'flex', gap: 'var(--space-2)',
      marginBottom: 'var(--space-6)', flexWrap: 'wrap',
    }}>
      {items.map(item => (
        <button
          key={item.key}
          onClick={() => onSelect(item.key)}
          style={{
            padding: 'var(--space-1) var(--space-3)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)',
            background: active === item.key ? 'var(--fg)' : 'var(--card-bg)',
            color: active === item.key ? 'var(--bg)' : 'var(--muted)',
            fontSize: 'var(--text-xs)',
            fontFamily: 'inherit',
            cursor: 'pointer',
            transition: 'all var(--duration-fast)',
            borderColor: active === item.key ? 'var(--fg)' : undefined,
          }}
        >
          {item.label}{item.count != null ? ` (${item.count})` : ''}
        </button>
      ))}
    </div>
  )
}
