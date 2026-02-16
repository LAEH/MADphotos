import { useRef, useEffect } from 'react'
import type { Photo } from '../../types/photo'
import { loadProgressive } from '../../lib/imageLoading'

interface ProgressiveImgProps {
  photo: Photo
  tier: 'thumb' | 'mobile' | 'display'
  alt?: string
  className?: string
  onClick?: () => void
  style?: React.CSSProperties
}

export function ProgressiveImg({
  photo,
  tier,
  alt,
  className,
  onClick,
  style,
}: ProgressiveImgProps) {
  const imgRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    if (imgRef.current) {
      loadProgressive(imgRef.current, photo, tier)
    }
  }, [photo, tier])

  return (
    <img
      ref={imgRef}
      className={className}
      alt={alt || photo.alt || photo.caption || ''}
      onClick={onClick}
      style={style}
      decoding="async"
    />
  )
}
