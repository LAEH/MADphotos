import { useState, useEffect, useCallback } from 'react'

interface FloatingNavProps {
  menuOpen: boolean
  onMenuToggle: () => void
}

export function FloatingNav({ menuOpen, onMenuToggle }: FloatingNavProps) {
  const [loved, setLoved] = useState(false)
  const [bounce, setBounce] = useState(false)

  /* Listen for loved state changes from BentoView */
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      setLoved(detail?.loved ?? false)
    }
    document.addEventListener('bento-loved-change', handler)
    return () => document.removeEventListener('bento-loved-change', handler)
  }, [])

  const handleHeart = useCallback(() => {
    document.dispatchEvent(new CustomEvent('bento-love'))
    setBounce(true)
    setTimeout(() => setBounce(false), 350)
  }, [])

  return (
    <nav className={'floating-nav' + (menuOpen ? ' menu-expanded' : '')}>
      {/* Heart — left of logo */}
      <button
        className={`nav-heart${loved ? ' loved' : ''}${bounce ? ' bounce' : ''}`}
        onClick={handleHeart}
        aria-label="Love this composition"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
        </svg>
      </button>

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
        <span className="menu-hamburger">
          <svg width="11" height="9" viewBox="0 0 11 9" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
            <line x1="0.5" y1="0.65" x2="10.5" y2="0.65" />
            <line x1="0.5" y1="4.5" x2="10.5" y2="4.5" />
            <line x1="0.5" y1="8.35" x2="10.5" y2="8.35" />
          </svg>
        </span>
      </button>

    </nav>
  )
}
