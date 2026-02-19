import { useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../../store/appStore'
import { loadProgressive, applyBorderClip } from '../../lib/imageLoading'
import { GlassTag } from './GlassTag'
import { PaletteDots } from './PaletteDots'

export function Lightbox() {
  const lightboxOpen = useAppStore(s => s.lightboxOpen)
  const lightboxPhotos = useAppStore(s => s.lightboxPhotos)
  const lightboxIndex = useAppStore(s => s.lightboxIndex)
  const closeLightbox = useAppStore(s => s.closeLightbox)
  const navigateLightbox = useAppStore(s => s.navigateLightbox)

  const imgRef = useRef<HTMLImageElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const touchStartX = useRef(0)

  const photo =
    lightboxPhotos.length > 0 && lightboxIndex >= 0
      ? lightboxPhotos[lightboxIndex]
      : null

  /* Load image when photo changes */
  useEffect(() => {
    if (!photo || !imgRef.current) return
    const img = imgRef.current
    img.style.transform = ''
    loadProgressive(img, photo, 'display', '100vw')
    applyBorderClip(img, photo.border_crop)
    img.alt = photo.alt || photo.caption || ''
  }, [photo])

  /* Capture-phase keyboard handler so lightbox takes priority */
  useEffect(() => {
    if (!lightboxOpen) return

    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeLightbox()
        e.stopPropagation()
        e.preventDefault()
      } else if (e.key === 'ArrowRight') {
        navigateLightbox(1)
        e.stopPropagation()
        e.preventDefault()
      } else if (e.key === 'ArrowLeft') {
        navigateLightbox(-1)
        e.stopPropagation()
        e.preventDefault()
      }
    }

    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [lightboxOpen, closeLightbox, navigateLightbox])

  /* Touch swipe */
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
  }, [])

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const dx = e.changedTouches[0].clientX - touchStartX.current
      if (Math.abs(dx) > 50) {
        navigateLightbox(dx > 0 ? -1 : 1)
      }
    },
    [navigateLightbox],
  )

  const hasList = lightboxPhotos.length > 1
  const showPrev = hasList && lightboxIndex > 0
  const showNext = hasList && lightboxIndex < lightboxPhotos.length - 1

  /* Build tag list for current photo */
  const tags: { text: string; category: string }[] = []
  if (photo) {
    const consensusSet = new Set(photo.consensus || [])
    for (const c of photo.consensus || []) {
      tags.push({ text: c, category: 'consensus' })
    }
    for (const v of photo.vibes || []) {
      if (!consensusSet.has(v.toLowerCase())) {
        tags.push({ text: v, category: 'vibe' })
      }
    }
    if (photo.grading) tags.push({ text: photo.grading, category: 'grading' })
    if (photo.time) tags.push({ text: photo.time, category: 'time' })
    if (photo.scene) tags.push({ text: photo.scene, category: 'scene' })
    if (photo.emotion) tags.push({ text: photo.emotion, category: 'emotion' })
    if (photo.camera) tags.push({ text: photo.camera, category: 'camera' })
  }

  return (
    <div
      className={'lightbox' + (lightboxOpen ? '' : ' hidden')}
      id="lightbox"
    >
      <div className="lightbox-backdrop" onClick={closeLightbox} />
      <div
        className="lightbox-content"
        ref={contentRef}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        <button
          className="lightbox-close"
          onClick={closeLightbox}
          aria-label="Close lightbox"
        >
          &times;
        </button>
        <img
          ref={imgRef}
          className="lightbox-img"
          alt=""
        />
        <div className="lightbox-meta" style={{ display: photo ? 'block' : 'none' }}>
          <div className="lightbox-alt">
            {photo
              ? photo.best_caption || photo.caption || photo.alt || ''
              : ''}
          </div>
          <div className="lightbox-tags">
            {tags.map((t, i) => (
              <GlassTag key={`${t.category}-${t.text}-${i}`} text={t.text} category={t.category} />
            ))}
          </div>
          <div className="lightbox-palette">
            <PaletteDots palette={photo?.palette} size={20} />
          </div>
        </div>

        <button
          className="lightbox-nav lightbox-prev"
          hidden={!showPrev}
          onClick={e => {
            e.stopPropagation()
            navigateLightbox(-1)
          }}
          aria-label="Previous photo"
        >
          &#8249;
        </button>
        <button
          className="lightbox-nav lightbox-next"
          hidden={!showNext}
          onClick={e => {
            e.stopPropagation()
            navigateLightbox(1)
          }}
          aria-label="Next photo"
        >
          &#8250;
        </button>
      </div>
    </div>
  )
}
