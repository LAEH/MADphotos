import { useCallback, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { EXPERIENCES } from './experiences'
import { ThemeToggle } from './ThemeToggle'

interface SideMenuProps {
  open: boolean
  onClose: () => void
}

function toggleFullscreen() {
  const doc = document as Document & {
    webkitFullscreenElement?: Element
    webkitExitFullscreen?: () => void
  }
  const el = document.documentElement as HTMLElement & {
    webkitRequestFullscreen?: () => void
  }

  if (!doc.fullscreenElement && !doc.webkitFullscreenElement) {
    if (el.requestFullscreen) el.requestFullscreen()
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen()
  } else {
    if (doc.exitFullscreen) doc.exitFullscreen()
    else if (doc.webkitExitFullscreen) doc.webkitExitFullscreen()
  }
}

function updateFullscreenIcon() {
  const doc = document as Document & { webkitFullscreenElement?: Element }
  const isFs = !!(doc.fullscreenElement || doc.webkitFullscreenElement)
  document.documentElement.classList.toggle('is-fullscreen', isFs)
}

export function SideMenu({ open, onClose }: SideMenuProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const currentRoute = location.pathname.slice(1)

  const handleNav = useCallback(
    (path: string) => {
      navigate(path)
      onClose()
    },
    [navigate, onClose],
  )

  const handleSystem = useCallback(() => {
    window.open('/system/', '_blank')
    onClose()
  }, [onClose])

  const handleFullscreen = useCallback(() => {
    toggleFullscreen()
  }, [])

  /* Listen for fullscreen changes */
  useEffect(() => {
    document.addEventListener('fullscreenchange', updateFullscreenIcon)
    document.addEventListener('webkitfullscreenchange', updateFullscreenIcon)
    return () => {
      document.removeEventListener('fullscreenchange', updateFullscreenIcon)
      document.removeEventListener('webkitfullscreenchange', updateFullscreenIcon)
    }
  }, [])

  /* Escape key to close */
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  /* Detect if fullscreen API is supported (hide button on iOS Safari) */
  const el = document.documentElement as HTMLElement & {
    webkitRequestFullscreen?: () => void
  }
  const supportsFullscreen = !!(el.requestFullscreen || el.webkitRequestFullscreen)
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
  const showFullscreen = supportsFullscreen && !isIOS

  return (
    <div className={'side-menu' + (open ? ' open' : '')} id="side-menu">
      <ul className="side-menu-list">
        {EXPERIENCES.map(exp => (
          <li
            key={exp.id}
            className={
              'side-menu-item' + (currentRoute === exp.route ? ' active' : '')
            }
            onClick={() => handleNav(exp.path)}
          >
            <span>{exp.name}</span>
          </li>
        ))}
      </ul>
      <div className="side-menu-footer">
        <button
          className="side-menu-action"
          onClick={handleSystem}
          aria-label="System"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="8" cy="8" r="3" />
            <path d="M13.4 10a1.2 1.2 0 0 0 .2 1.3l.1.1a1.5 1.5 0 1 1-2.1 2.1l-.1-.1a1.2 1.2 0 0 0-1.3-.2 1.2 1.2 0 0 0-.7 1.1v.2a1.5 1.5 0 0 1-3 0v-.1a1.2 1.2 0 0 0-.8-1.1 1.2 1.2 0 0 0-1.3.2l-.1.1a1.5 1.5 0 1 1-2.1-2.1l.1-.1a1.2 1.2 0 0 0 .2-1.3 1.2 1.2 0 0 0-1.1-.7h-.2a1.5 1.5 0 0 1 0-3h.1a1.2 1.2 0 0 0 1.1-.8 1.2 1.2 0 0 0-.2-1.3l-.1-.1a1.5 1.5 0 1 1 2.1-2.1l.1.1a1.2 1.2 0 0 0 1.3.2h.1a1.2 1.2 0 0 0 .7-1.1v-.2a1.5 1.5 0 0 1 3 0v.1a1.2 1.2 0 0 0 .7 1.1 1.2 1.2 0 0 0 1.3-.2l.1-.1a1.5 1.5 0 1 1 2.1 2.1l-.1.1a1.2 1.2 0 0 0-.2 1.3v.1a1.2 1.2 0 0 0 1.1.7h.2a1.5 1.5 0 0 1 0 3h-.1a1.2 1.2 0 0 0-1.1.7z" />
          </svg>
          <span>System</span>
        </button>
        <ThemeToggle />
        {showFullscreen && (
          <button
            className="side-menu-action"
            id="fullscreen-toggle"
            onClick={handleFullscreen}
            aria-label="Toggle fullscreen"
          >
            {/* Expand icon */}
            <svg
              className="fs-icon-expand"
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4" />
            </svg>
            {/* Collapse icon */}
            <svg
              className="fs-icon-collapse"
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M6 2v4H2M10 2v4h4M6 14v-4H2M10 14v-4h4" />
            </svg>
            <span>Fullscreen</span>
          </button>
        )}
      </div>
    </div>
  )
}
