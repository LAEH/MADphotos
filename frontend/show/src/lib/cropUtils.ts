import type { Photo } from '../types/photo'

export type CellOrient = 'P' | 'L'

/** Width-to-height ratio of each grid unit cell (square). */
export const BENTO_UNIT_RATIO = 1

/** The 7 allowed cell aspect ratios. */
export const ALLOWED_RATIOS = new Set([1/2, 2/3, 3/4, 1, 4/3, 3/2, 2/1])

export interface BentoCell {
  r: number; c: number; rs: number; cs: number
  orient: CellOrient
}

/** Map a container width/height ratio to the closest Gemma crop key.
 *  Exact-matches the 7 allowed ratios first, then falls back to thresholds. */
export function cropKeyFromRatio(ratio: number): string {
  // Exact matches (within float tolerance)
  if (Math.abs(ratio - 0.5) < 0.01) return '2:3'    // 1/2
  if (Math.abs(ratio - 2/3) < 0.01) return '2:3'     // 2/3
  if (Math.abs(ratio - 0.75) < 0.01) return '2:3'    // 3/4
  if (Math.abs(ratio - 1) < 0.01) return '1:1'        // 1
  if (Math.abs(ratio - 4/3) < 0.01) return '3:2'     // 4/3
  if (Math.abs(ratio - 1.5) < 0.01) return '3:2'     // 3/2
  if (Math.abs(ratio - 2) < 0.01) return '16:9'       // 2/1
  // Fallback thresholds for dynamic grids
  if (ratio >= 1.6) return '16:9'
  if (ratio >= 1.1) return '3:2'
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

/**
 * Compute the true rendered aspect ratio of a cell given the container.
 * containerRatio = CSS aspect-ratio of the grid container (w/h).
 * cols/rows = grid dimensions.
 * The unit cell on screen = containerRatio × rows / cols.
 * The cell ratio = (cs/rs) × unitOnScreen.
 */
export function renderedCellRatio(cell: BentoCell, cols: number, rows: number, containerRatio: number): number {
  const unitOnScreen = containerRatio * rows / cols
  return (cell.cs / cell.rs) * unitOnScreen
}

export function getObjectPosition(photo: Photo, cell: BentoCell, cols?: number, rows?: number, containerRatio?: number): string {
  if (cols != null && rows != null && containerRatio != null) {
    return smartObjectPosition(photo, renderedCellRatio(cell, cols, rows, containerRatio))
  }
  // Legacy fallback (no container info) — use mathematical ratio
  const ratio = (cell.cs * BENTO_UNIT_RATIO) / cell.rs
  return smartObjectPosition(photo, ratio)
}
