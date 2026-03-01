interface FloatingNavProps {
  menuOpen: boolean
  onMenuToggle: () => void
}

export function FloatingNav({ menuOpen, onMenuToggle }: FloatingNavProps) {
  return (
    <nav className={'floating-nav' + (menuOpen ? ' menu-expanded' : '')}>
      <button
        id="menu-btn"
        className={'menu-btn' + (menuOpen ? ' menu-open' : '')}
        onClick={onMenuToggle}
        aria-label="Toggle menu"
      >
        <span className="menu-hamburger">
          <svg width="11" height="9" viewBox="0 0 11 9" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
            <line x1="0.5" y1="0.65" x2="10.5" y2="0.65" />
            <line x1="0.5" y1="4.5" x2="10.5" y2="4.5" />
            <line x1="0.5" y1="8.35" x2="10.5" y2="8.35" />
          </svg>
        </span>
        <span className="logo">
          <span className="logo-mad">MAD</span>
          <span className="logo-photos">photos</span>
        </span>
      </button>

    </nav>
  )
}
