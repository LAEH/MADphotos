import { useState, useCallback } from 'react'
import { FloatingNav } from './FloatingNav'
import { SideMenu } from './SideMenu'
import { Lightbox } from '../ui/Lightbox'

export function Shell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false)

  const handleMenuToggle = useCallback(() => {
    setMenuOpen(prev => !prev)
  }, [])

  const handleMenuClose = useCallback(() => {
    setMenuOpen(false)
  }, [])

  return (
    <>
      <div className="nav-container">
        <FloatingNav menuOpen={menuOpen} onMenuToggle={handleMenuToggle} />
        <SideMenu open={menuOpen} onClose={handleMenuClose} />
      </div>
      <div
        className={'side-menu-backdrop' + (menuOpen ? ' open' : '')}
        onClick={handleMenuClose}
      />
      {children}
      <Lightbox />
    </>
  )
}
