interface Props {
  value: number
  max: number
  color?: string
  label?: string
}

export function ProgressBar({ value, max, color = 'var(--system-blue)', label }: Props) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div>
      {label && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
          marginBottom: 'var(--space-1)',
        }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>{label}</span>
          <span style={{
            fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
            color: 'var(--fg-secondary)',
          }}>
            {value.toLocaleString()} / {max.toLocaleString()}
          </span>
        </div>
      )}
      <div style={{
        height: 6, borderRadius: 'var(--radius-full)',
        background: 'var(--bar-bg)', overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', width: `${pct}%`, borderRadius: 'var(--radius-full)',
          background: color,
          transition: 'width var(--duration-normal) var(--ease-default)',
        }} />
      </div>
    </div>
  )
}
