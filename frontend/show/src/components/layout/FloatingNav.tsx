import { useLocation } from 'react-router-dom'
import { EXPERIENCES } from './experiences'

interface FloatingNavProps {
  menuOpen: boolean
  onMenuToggle: () => void
}

export function FloatingNav({ menuOpen, onMenuToggle }: FloatingNavProps) {
  const location = useLocation()

  /* Determine current experience from pathname */
  const currentRoute = location.pathname.slice(1) /* strip leading / */
  const currentExp = EXPERIENCES.find(e => e.route === currentRoute)

  return (
    <nav className={'floating-nav' + (menuOpen ? ' menu-expanded' : '')}>
      <button
        id="menu-btn"
        className={'menu-btn' + (menuOpen ? ' menu-open' : '')}
        onClick={onMenuToggle}
        aria-label="Toggle menu"
      >
        <span className="logo">
          <span className="logo-mad">MAD</span>
          <span className="logo-photos">photos</span>
        </span>
        <span className="menu-chevron">
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 4.5L6 7.5L9 4.5" />
          </svg>
        </span>
        {currentExp && (
          <span className="menu-btn-label">{currentExp.name}</span>
        )}
      </button>

      {currentExp && (
        <span id="nav-exp-label" className="nav-exp-label">
          {currentExp.name}
        </span>
      )}

    </nav>
  )
}
