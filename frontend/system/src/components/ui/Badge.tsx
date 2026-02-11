interface Props {
  children: React.ReactNode
  variant?: 'green' | 'amber' | 'red' | 'default'
}

const styles: Record<string, React.CSSProperties> = {
  green: { background: 'var(--badge-green-bg)', color: 'var(--badge-green-fg)' },
  amber: { background: 'var(--badge-amber-bg)', color: 'var(--badge-amber-fg)' },
  red: { background: 'var(--badge-red-bg)', color: 'var(--badge-red-fg)' },
  default: { background: 'var(--hover-overlay)', color: 'var(--fg-secondary)' },
}

export function Badge({ children, variant = 'default' }: Props) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px var(--space-2)',
      borderRadius: 'var(--radius-sm)',
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      ...styles[variant],
    }}>
      {children}
    </span>
  )
}
