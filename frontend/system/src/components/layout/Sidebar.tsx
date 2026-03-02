import { NavLink, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { ThemeToggle } from './ThemeToggle'

interface NavItem {
  to: string
  label: string
  localOnly?: boolean
}

const isProd = import.meta.env.PROD

const navItems: NavItem[] = [
  { to: '/status', label: 'Status' },
  { to: '/journal', label: 'Journal', localOnly: true },
  { to: '/instructions', label: 'Instructions' },
  { to: '/docs/bento', label: 'Bento Algorithm' },
]

const signals: NavItem[] = [
  { to: '/experiments/signals', label: 'All' },
  { to: '/experiments/gemma', label: 'Gemma' },
  { to: '/experiments/mosaics', label: 'Mosaics' },
]

const curation: NavItem[] = [
  { to: '/review/unpicked', label: 'Unpicked', localOnly: true },
  { to: '/curation/location', label: 'Location', localOnly: true },
  { to: '/experiments/generated', label: 'Generated', localOnly: true },
  { to: '/review/variants', label: 'Variant Disks', localOnly: true },
  { to: '/review/borders', label: 'Border Crops', localOnly: true },
  { to: '/experiments/enhanced', label: 'Enhanced', localOnly: true },
]

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const renderLink = (item: NavItem) => {
    const disabled = isProd && item.localOnly
    if (disabled) {
      return (
        <span key={item.to} className="sb-disabled">
          {item.label}
        </span>
      )
    }
    return (
      <NavLink
        key={item.to}
        to={item.to}
        className={({ isActive }) => isActive ? 'active' : ''}
        onClick={() => setMobileOpen(false)}
      >
        {item.label}
      </NavLink>
    )
  }

  return (
    <nav className={`sidebar${mobileOpen ? ' open' : ''}`} id="sidebar">
      <div className="sb-title">
        <span>
          <span className="brand-mad">MAD</span>
          <span className="brand-sub">photos</span>
        </span>
      </div>
      <button
        className="sb-hamburger"
        onClick={() => setMobileOpen(o => !o)}
        aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
      >
        {mobileOpen ? '\u2715' : '\u2630'}
      </button>

      <div className="sb-content">
        {navItems.map(renderLink)}

        <div className="sb-sep" />
        <div className="sb-group">Signals</div>
        {signals.map(renderLink)}

        <div className="sb-sep" />
        <div className="sb-group">Curation</div>
        {curation.map(renderLink)}

        <div className="sb-bottom">
          <ThemeToggle />
        </div>
      </div>
    </nav>
  )
}
