import { NavLink, useLocation } from 'react-router-dom'
import { useState, useCallback, useEffect } from 'react'
import { ThemeToggle } from './ThemeToggle'

interface NavItem {
  to: string
  label: string
}

const navItems: NavItem[] = [
  { to: '/status', label: 'Status' },
  { to: '/journal', label: 'Journal' },
  { to: '/instructions', label: 'Instructions' },
]

const database: NavItem[] = [
  { to: '/db/overview', label: 'Overview' },
]

const experiments: NavItem[] = [
  { to: '/experiments/gemma', label: 'Gemma' },
  { to: '/experiments/mosaics', label: 'Mosaics' },
  { to: '/experiments/cartoon', label: 'Cartoon' },
  { to: '/experiments/blind-test', label: 'Blind Test' },
]

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() =>
    localStorage.getItem('mad-sidebar') === 'collapsed'
  )
  const location = useLocation()

  const toggleCollapse = useCallback(() => {
    setCollapsed(c => {
      const next = !c
      localStorage.setItem('mad-sidebar', next ? 'collapsed' : 'expanded')
      return next
    })
  }, [])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // Removed sidebar-rail collapse effect - we only collapse vertically now

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
    <nav className={`sidebar${mobileOpen ? ' open' : ''}${collapsed ? ' collapsed' : ''}`} id="sidebar">
      <div className="sb-title">
        <span>
          <span className="brand-mad">MAD</span>
          <span className="brand-sub">photos</span>
        </span>
        <button
          className="sb-collapse-btn"
          onClick={toggleCollapse}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '\u25C0' : '\u25BC'}
        </button>
      </div>
      <button
        className="sb-hamburger"
        onClick={() => setMobileOpen(o => !o)}
        aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
      >
        {mobileOpen ? '\u2715' : '\u2630'}
      </button>

      <div className="sb-content">
        <a href="/" className="sb-show-link">
          Show
        </a>
        {navItems.map(renderLink)}

        <div className="sb-sep" />
        <div className="sb-group">Database</div>
        {database.map(renderLink)}

        <div className="sb-sep" />
        <div className="sb-group">Experiments</div>
        {experiments.map(renderLink)}

        <div className="sb-bottom">
          <ThemeToggle />
        </div>
      </div>
    </nav>
  )
}
