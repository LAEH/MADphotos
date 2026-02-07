import { useTheme } from '../../hooks/useTheme'

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  return (
    <button
      onClick={toggle}
      style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
        fontSize: 'var(--text-sm)', color: 'var(--muted)', cursor: 'pointer',
        padding: 'var(--space-2) 0', background: 'none', border: 'none',
        fontFamily: 'inherit', width: '100%',
        transition: `color var(--duration-fast)`,
        whiteSpace: 'nowrap', overflow: 'hidden',
      }}
      onMouseEnter={e => (e.currentTarget.style.color = 'var(--fg)')}
      onMouseLeave={e => (e.currentTarget.style.color = 'var(--muted)')}
    >
      <span style={{ fontSize: 16 }}>{theme === 'dark' ? '\u2600' : '\u263E'}</span>
      <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
    </button>
  )
}
