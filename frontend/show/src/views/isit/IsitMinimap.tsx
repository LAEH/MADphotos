import type { Photo } from '../../types/photo'
import { smartObjectPosition } from '../../lib/cropUtils'

interface IsitMinimapProps {
  photos: Photo[]
  index: number
  votes: Record<string, string>
  onGoBack: (targetIndex: number) => void
  animating: boolean
}

export function IsitMinimap({ photos, index, votes, onGoBack, animating }: IsitMinimapProps) {
  const slots = []

  for (let s = 0; s < 5; s++) {
    const i = index + s - 2

    if (i < 0 || i >= photos.length) {
      slots.push(
        <div key={s} className="isit-mini-slot isit-mini-empty">
          <img style={{ display: 'none' }} alt="" />
          <div className="isit-mini-tint" style={{ display: 'none' }} />
        </div>
      )
      continue
    }

    const photo = photos[i]
    const src = photo.thumb || photo.mobile || ''
    const focus = { objectPosition: smartObjectPosition(photo, 1) }

    let slotClass = 'isit-mini-slot'
    let tintClass = 'isit-mini-tint'
    let showTint = false
    let clickable = false

    if (i === index) {
      /* Current — no tint */
    } else if (i < index) {
      /* Past — vote tint */
      const v = votes[photo.id]
      showTint = true
      tintClass += v === 'accept' ? ' isit-mini-accept' : ' isit-mini-reject'
      clickable = true
    } else {
      /* Future — dimmed gray */
      slotClass += ' isit-mini-future'
    }

    slots.push(
      <div
        key={s}
        className={slotClass}
        style={clickable ? { cursor: 'pointer' } : undefined}
        onClick={clickable && !animating ? () => onGoBack(i) : undefined}
      >
        {src ? <img src={src} style={focus} alt="" draggable={false} /> : <img style={{ display: 'none' }} alt="" />}
        <div className={tintClass} style={showTint ? undefined : { display: 'none' }} />
      </div>
    )
  }

  return <div className="isit-minimap">{slots}</div>
}
