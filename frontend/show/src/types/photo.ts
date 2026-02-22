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
  // Gemma composition signals (visual intelligence for layout)
  gc_weight?: number      // visual_weight 1-10
  gc_energy?: string      // energy_direction
  gc_archetype?: string   // portal, horizon, texture, figure, geometry, void, cluster, reflection, silhouette, panorama
  gc_temp?: string        // glacial, cool, neutral, warm, molten, electric, neon, muted, monochrome
  // Gemma creative signals
  gemma_description?: string
  gemma_subject?: string
  gemma_story?: string
  gemma_vibes?: string[]
  gemma_pops?: SemanticPop[]
  gemma_stories?: Record<string, string>
  gemma_tags?: string
  gemma_exposure?: string
  gemma_sharpness?: string
}

export interface SemanticPop {
  color: string
  object: string
  impact: string
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
