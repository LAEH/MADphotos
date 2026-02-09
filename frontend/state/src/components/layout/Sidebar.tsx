import { NavLink, useLocation } from 'react-router-dom'
import { useState, useCallback, useEffect } from 'react'
import { ThemeToggle } from './ThemeToggle'

const navItems = [
  { to: '/', label: 'State' },
  { to: '/stats', label: 'Stats' },
  { to: '/see', label: 'See App' },
  { to: '/journal', label: 'Journal de Bord' },
  { to: '/instructions', label: 'System Instructions' },
]

const analysis = [
  { to: '/signal-inspector', label: 'Signal Inspector' },
  { to: '/embedding-audit', label: 'Embedding Audit' },
  { to: '/collection-coverage', label: 'Coverage' },
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
  const [isMobile, setIsMobile] = useState(false)
  const location = useLocation()

  const toggleCollapse = useCallback(() => {
    setCollapsed(c => {
      const next = !c
      localStorage.setItem('mad-sidebar', next ? 'collapsed' : 'expanded')
      return next
    })
  }, [])

  // Close mobile menu on navigation
  const closeMobile = useCallback(() => setMobileOpen(false), [])

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // Track mobile vs desktop
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)')
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      setIsMobile(e.matches)
      if (!e.matches) setMobileOpen(false)
    }
    handler(mq)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  // Sync body class for collapsed state
  useEffect(() => {
    document.body.classList.toggle('sb-collapsed', collapsed)
  }, [collapsed])

  // Prevent body scroll when mobile menu open
  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [mobileOpen])

  // Desktop collapsed: only apply inline styles when NOT on mobile
  const desktopCollapsedStyle = (collapsed && !isMobile) ? {
    width: 0,
    minWidth: 0,
    overflow: 'hidden' as const,
    padding: 0,
    borderRight: 'none',
  } : undefined

  return (
    <>
      {/* Expand button -- desktop collapsed */}
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
        style={desktopCollapsedStyle}
      >
        <div className="sb-title">MADphotos</div>
        <button
          className="sb-hamburger"
          onClick={() => setMobileOpen(o => !o)}
          aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
        >
          {mobileOpen ? '\u2715' : '\u2630'}
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
        <div className="sb-group">Analysis</div>

        {analysis.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
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
