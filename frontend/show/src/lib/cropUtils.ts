import type { Photo } from '../types/photo'

export type CellOrient = 'P' | 'L'

/** Width-to-height ratio of each grid unit cell (4:3). */
export const BENTO_UNIT_RATIO = 4 / 3

export interface BentoCell {
  r: number; c: number; rs: number; cs: number
  orient: CellOrient
}

/** Map a container width/height ratio to the closest Gemma crop key. */
export function cropKeyFromRatio(ratio: number): string {
  if (ratio >= 1.6) return '16:9'
  if (ratio >= 1.2) return '3:2'
  if (ratio <= 0.85) return '2:3'
  return '1:1'
}

/** Full cascade: gemma_crops → focus → saliency → center. */
export function smartObjectPosition(photo: Photo, containerRatio: number): string {
  if (photo.gemma_crops) {
    const key = cropKeyFromRatio(containerRatio)
    const crop = photo.gemma_crops[key]
    if (crop) return `${crop.center_x}% ${crop.center_y}%`
  }
  if (photo.focus) return `${photo.focus[0]}% ${photo.focus[1]}%`
  if (photo.saliency) return `${Math.round(photo.saliency.px * 100)}% ${Math.round(photo.saliency.py * 100)}%`
  return '50% 50%'
}

export function getObjectPosition(photo: Photo, cell: BentoCell): string {
  const ratio = (cell.cs * BENTO_UNIT_RATIO) / cell.rs
  return smartObjectPosition(photo, ratio)
}
