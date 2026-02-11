import { useTheme } from '../../hooks/useTheme'

export function ThemeToggle() {
  const { toggle } = useTheme()
  return (
    <div className="theme-toggle" onClick={toggle}>
      <div className="theme-switch" />
      <span className="theme-label">Light mode</span>
    </div>
  )
}
