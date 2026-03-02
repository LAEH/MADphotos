import { NavLink, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { ThemeToggle } from './ThemeToggle'

interface NavItem {
  to: string
  label: string
}

const navItems: NavItem[] = [
  { to: '/status', label: 'Status' },
  { to: '/journal', label: 'Journal' },
  { to: '/instructions', label: 'Instructions' },
  { to: '/docs/bento', label: 'Bento Algorithm' },
]

const signals: NavItem[] = [
  { to: '/experiments/signals', label: 'All' },
  { to: '/experiments/gemma', label: 'Gemma' },
  { to: '/experiments/mosaics', label: 'Mosaics' },
]

const curation: NavItem[] = [
  { to: '/review/unpicked', label: 'Unpicked' },
  { to: '/curation/location', label: 'Location' },
  { to: '/experiments/generated', label: 'Generated' },
  { to: '/review/variants', label: 'Variant Disks' },
  { to: '/review/borders', label: 'Border Crops' },
  { to: '/experiments/enhanced', label: 'Enhanced' },
]

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const renderLink = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      className={({ isActive }) => isActive ? 'active' : ''}
      onClick={() => setMobileOpen(false)}
    >
      {item.label}
    </NavLink>
  )

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
