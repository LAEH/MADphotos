export interface Photo {
  id: string
  w: number
  h: number
  aspect: number
  thumb: string
  mobile?: string
  display?: string
  micro?: string
  alt?: string
  caption?: string
  best_caption?: string
  orientation?: 'portrait' | 'landscape' | 'square'
  date?: string
  camera?: string
  palette?: string[]
  hue?: number
  parent?: string
  variant_type?: string
  style_name?: string
  brightness?: number
  contrast?: number
  aesthetic?: number
  mono?: boolean
  has_border?: boolean
  focus?: [number, number]
  border_crop?: BorderCrop
  saliency?: Saliency
  face_count?: number
  objects?: string[]
  vibes?: string[]
  consensus?: string[]
  scene?: string
  emotion?: string
  style?: string
  time?: string
  grading?: string
  depth?: string
  depth_complexity?: number
  composition?: string
  gemma_crops?: Record<string, GemmaCrop>
}

export interface BorderCrop {
  top?: number
  right?: number
  bottom?: number
  left?: number
}

export interface Saliency {
  px: number
  py: number
  spread: number
}

export interface GemmaCrop {
  center_x: number
  center_y: number
  coverage: number
}

export interface DriftNeighbor {
  id: string
  score: number
  uuid?: string
}

export interface GamePair {
  a: Photo
  b: Photo
  reason: string
  strategy?: string
}

export interface GemmaData {
  description?: string
  story?: string
  subject?: string
  mood?: string
  lighting?: string
  composition?: string
  colors?: string
  texture?: string
  technical?: string
  strength?: string
}

export interface PhotosData {
  photos: Photo[]
}

export interface PicksData {
  portrait: string[]
  landscape: string[]
}

export interface Experience {
  id: string
  route: string
  name: string
  emoji: string
  path: string
}
