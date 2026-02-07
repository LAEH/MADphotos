import { NavLink } from 'react-router-dom'
import { useState, useCallback, useEffect } from 'react'
import { ThemeToggle } from './ThemeToggle'

const navItems = [
  { to: '/', label: 'State' },
  { to: '/journal', label: 'Journal de Bord' },
  { to: '/instructions', label: 'System Instructions' },
]

const experiments = [
  { to: '/similarity', label: 'Similarity' },
  { to: '/blind-test', label: 'Blind Test' },
  { to: '/mosaics', label: 'Mosaics' },
  { to: '/cartoon', label: 'Cartoon' },
]

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() =>
    localStorage.getItem('mad-sidebar') === 'collapsed'
  )

  const toggleCollapse = useCallback(() => {
    setCollapsed(c => {
      const next = !c
      localStorage.setItem('mad-sidebar', next ? 'collapsed' : 'expanded')
      return next
    })
  }, [])

  // Close mobile menu on navigation
  const closeMobile = useCallback(() => setMobileOpen(false), [])

  // Sync body class for collapsed state
  useEffect(() => {
    document.body.classList.toggle('sb-collapsed', collapsed)
  }, [collapsed])

  return (
    <>
      {/* Expand button — desktop collapsed */}
      <button
        className="sb-expand"
        onClick={toggleCollapse}
        title="Show sidebar"
        style={{
          display: collapsed ? undefined : 'none',
        }}
      >
        &#9776;
      </button>

      <nav
        className={`sidebar${mobileOpen ? ' open' : ''}`}
        style={{
          width: collapsed ? 0 : undefined,
          minWidth: collapsed ? 0 : undefined,
          overflow: collapsed ? 'hidden' : undefined,
          padding: collapsed ? 0 : undefined,
          borderRight: collapsed ? 'none' : undefined,
        }}
      >
        <div className="sb-title">MADphotos</div>
        <button
          className="sb-hamburger"
          onClick={() => setMobileOpen(o => !o)}
          aria-label="Menu"
        >
          &#9776;
        </button>

        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => isActive ? 'active' : ''}
            onClick={closeMobile}
          >
            {item.label}
          </NavLink>
        ))}

        <div className="sb-sep" />
        <div className="sb-group">Experiments</div>

        {experiments.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => isActive ? 'active' : ''}
            onClick={closeMobile}
          >
            {item.label}
          </NavLink>
        ))}

        <div className="sb-bottom">
          <button className="sb-collapse" onClick={toggleCollapse}>
            &#x276E; Hide sidebar
          </button>
          <ThemeToggle />
        </div>
      </nav>
    </>
  )
}
