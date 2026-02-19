import { useRef, useEffect } from 'react'
import type { Photo } from '../../types/photo'
import { loadProgressive } from '../../lib/imageLoading'

interface ProgressiveImgProps {
  photo: Photo
  tier: 'thumb' | 'mobile' | 'display'
  sizes?: string
  alt?: string
  className?: string
  onClick?: () => void
  style?: React.CSSProperties
}

export function ProgressiveImg({
  photo,
  tier,
  sizes,
  alt,
  className,
  onClick,
  style,
}: ProgressiveImgProps) {
  const imgRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    if (imgRef.current) {
      loadProgressive(imgRef.current, photo, tier, sizes)
    }
  }, [photo, tier, sizes])

  /* Merge aspect-ratio from photo dimensions for CLS prevention */
  const mergedStyle = photo.w && photo.h
    ? { aspectRatio: `${photo.w} / ${photo.h}`, ...style }
    : style

  return (
    <img
      ref={imgRef}
      className={className}
      alt={alt || photo.alt || photo.caption || ''}
      onClick={onClick}
      style={mergedStyle}
      width={photo.w || undefined}
      height={photo.h || undefined}
      decoding="async"
    />
  )
}
