import { create } from 'zustand'
import type { Photo, PhotosData, PicksData, DriftNeighbor, GemmaData } from '../types/photo'

interface AppState {
  /* Data */
  data: PhotosData | null
  photoMap: Record<string, Photo>
  allPhotos: Photo[]
  allPhotoMap: Record<string, Photo>
  driftNeighbors: Record<string, DriftNeighbor[]> | null
  gameRounds: unknown[] | null
  picksData: PicksData | null
  votedData: Record<string, string> | null
  gemmaData: Record<string, GemmaData> | null

  /* Lightbox */
  lightboxOpen: boolean
  lightboxPhotos: Photo[]
  lightboxIndex: number

  /* Timers (for cleanup on view switch) */
  _activeTimers: number[]

  /* Actions */
  loadData: () => Promise<PhotosData>
  loadDriftNeighbors: () => Promise<Record<string, DriftNeighbor[]>>
  loadGameRounds: () => Promise<unknown[]>
  loadPicks: () => Promise<PicksData>
  loadVoted: () => Promise<Record<string, string>>
  loadGemma: () => Promise<Record<string, GemmaData>>
  openLightbox: (photo: Photo, photoList?: Photo[]) => void
  closeLightbox: () => void
  navigateLightbox: (dir: number) => void
  registerTimer: (id: number) => number
  clearAllTimers: () => void
}

async function fetchJSON<T>(url: string): Promise<T> {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}: ${url}`)
  return resp.json()
}

export const useAppStore = create<AppState>((set, get) => ({
  data: null,
  photoMap: {},
  allPhotos: [],
  allPhotoMap: {},
  driftNeighbors: null,
  gameRounds: null,
  picksData: null,
  votedData: null,
  gemmaData: null,

  lightboxOpen: false,
  lightboxPhotos: [],
  lightboxIndex: -1,

  _activeTimers: [],

  async loadData() {
    const existing = get().data
    if (existing) return existing

    const data = await fetchJSON<PhotosData>('/data/photos.json')
    const photoMap: Record<string, Photo> = {}
    for (const photo of data.photos) {
      photoMap[photo.id] = photo
    }

    /* Load picks to filter */
    let picksData: PicksData
    try {
      picksData = await fetchJSON<PicksData>('/data/picks.json')
    } catch {
      picksData = { portrait: [], landscape: [] }
    }

    /* Load server-side vote history */
    let votedData: Record<string, string>
    try {
      votedData = await fetchJSON<Record<string, string>>('/data/voted.json')
    } catch {
      votedData = {}
    }

    /* Stash full collection, then filter to picks */
    const allPhotos = data.photos
    const allPhotoMap = { ...photoMap }

    const picksSet = new Set([
      ...(picksData.portrait || []),
      ...(picksData.landscape || [])
    ])
    const filteredPhotos = allPhotos.filter(p => picksSet.has(p.id))
    const filteredPhotoMap: Record<string, Photo> = {}
    for (const photo of filteredPhotos) {
      filteredPhotoMap[photo.id] = photo
    }

    const filteredData = { ...data, photos: filteredPhotos }

    set({
      data: filteredData,
      photoMap: filteredPhotoMap,
      allPhotos,
      allPhotoMap,
      picksData,
      votedData,
    })

    /* Precache micro images via service worker */
    if (navigator.serviceWorker?.controller) {
      const micros = filteredPhotos.filter(p => p.micro).map(p => p.micro!)
      if (micros.length) {
        navigator.serviceWorker.controller.postMessage({
          type: 'precache-micros',
          urls: micros,
        })
      }
    }

    return filteredData
  },

  async loadDriftNeighbors() {
    const existing = get().driftNeighbors
    if (existing) return existing
    let data: Record<string, DriftNeighbor[]>
    try {
      data = await fetchJSON('/data/drift_neighbors.json')
    } catch {
      data = {}
    }
    set({ driftNeighbors: data })
    return data
  },

  async loadGameRounds() {
    const existing = get().gameRounds
    if (existing) return existing
    let data: unknown[]
    try {
      data = await fetchJSON('/data/game_rounds.json')
    } catch {
      data = []
    }
    set({ gameRounds: data })
    return data
  },

  async loadPicks() {
    const existing = get().picksData
    if (existing) return existing
    let data: PicksData
    try {
      data = await fetchJSON('/data/picks.json')
    } catch {
      data = { portrait: [], landscape: [] }
    }
    set({ picksData: data })
    return data
  },

  async loadVoted() {
    const existing = get().votedData
    if (existing) return existing
    let data: Record<string, string>
    try {
      data = await fetchJSON('/data/voted.json')
    } catch {
      data = {}
    }
    set({ votedData: data })
    return data
  },

  async loadGemma() {
    const existing = get().gemmaData
    if (existing) return existing
    let data: Record<string, GemmaData>
    try {
      data = await fetchJSON('/data/gemma_picks.json?v=' + Date.now())
    } catch {
      data = {}
    }
    set({ gemmaData: data })
    return data
  },

  openLightbox(photo, photoList) {
    if (photoList && photoList.length > 0) {
      let index = photoList.findIndex(p => p.id === photo.id)
      if (index < 0) index = 0
      set({ lightboxOpen: true, lightboxPhotos: photoList, lightboxIndex: index })
    } else {
      set({ lightboxOpen: true, lightboxPhotos: [], lightboxIndex: -1 })
    }
  },

  closeLightbox() {
    set({ lightboxOpen: false, lightboxPhotos: [], lightboxIndex: -1 })
  },

  navigateLightbox(dir) {
    const { lightboxPhotos, lightboxIndex } = get()
    if (lightboxPhotos.length === 0 || lightboxIndex < 0) return
    const newIdx = lightboxIndex + dir
    if (newIdx < 0 || newIdx >= lightboxPhotos.length) return
    set({ lightboxIndex: newIdx })
  },

  registerTimer(id) {
    set(state => ({ _activeTimers: [...state._activeTimers, id] }))
    return id
  },

  clearAllTimers() {
    const { _activeTimers } = get()
    for (const id of _activeTimers) {
      clearInterval(id)
      cancelAnimationFrame(id)
    }
    set({ _activeTimers: [] })
  },
}))
