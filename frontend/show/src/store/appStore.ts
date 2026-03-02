import { create } from 'zustand'
import type { Photo, PhotosData, PicksData, DriftNeighbor, GemmaData } from '../types/photo'

interface AppState {
  /* Data */
  data: PhotosData | null
  photoMap: Record<string, Photo>
  allPhotos: Photo[]
  allPhotoMap: Record<string, Photo>
  driftNeighbors: Record<string, DriftNeighbor[]> | null
  picksData: PicksData | null
  votedData: Record<string, string> | null
  gemmaData: Record<string, GemmaData> | null

  /* Lightbox */
  lightboxOpen: boolean
  lightboxPhotos: Photo[]
  lightboxIndex: number
  lightboxMinimal: boolean

  /* Actions */
  loadData: () => Promise<PhotosData>
  loadDriftNeighbors: () => Promise<Record<string, DriftNeighbor[]>>
  loadGemma: () => Promise<Record<string, GemmaData>>
  openLightbox: (photo: Photo, photoList?: Photo[], minimal?: boolean) => void
  closeLightbox: () => void
  navigateLightbox: (dir: number) => void
}

async function fetchJSON<T>(url: string): Promise<T> {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}: ${url}`)
  return resp.json()
}

/*
 * Promise dedup: if loadData is called concurrently (e.g. React StrictMode
 * double-mount), only one fetch runs. All callers share the same promise.
 */
let _loadDataPromise: Promise<PhotosData> | null = null
let _loadDriftPromise: Promise<Record<string, DriftNeighbor[]>> | null = null
let _loadGemmaPromise: Promise<Record<string, GemmaData>> | null = null

export const useAppStore = create<AppState>((set, get) => ({
  data: null,
  photoMap: {},
  allPhotos: [],
  allPhotoMap: {},
  driftNeighbors: null,
  picksData: null,
  votedData: null,
  gemmaData: null,

  lightboxOpen: false,
  lightboxPhotos: [],
  lightboxIndex: -1,
  lightboxMinimal: false,

  async loadData() {
    const existing = get().data
    if (existing) return existing
    if (_loadDataPromise) return _loadDataPromise

    _loadDataPromise = (async () => {
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
      const allPhotoMap = photoMap

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
    })()

    try {
      return await _loadDataPromise
    } finally {
      _loadDataPromise = null
    }
  },

  async loadDriftNeighbors() {
    const existing = get().driftNeighbors
    if (existing) return existing
    if (_loadDriftPromise) return _loadDriftPromise

    _loadDriftPromise = (async () => {
      let data: Record<string, DriftNeighbor[]>
      try {
        data = await fetchJSON('/data/drift_neighbors.json')
      } catch {
        data = {}
      }
      set({ driftNeighbors: data })
      return data
    })()

    try {
      return await _loadDriftPromise
    } finally {
      _loadDriftPromise = null
    }
  },

  async loadGemma() {
    const existing = get().gemmaData
    if (existing) return existing
    if (_loadGemmaPromise) return _loadGemmaPromise

    _loadGemmaPromise = (async () => {
      let data: Record<string, GemmaData>
      try {
        data = await fetchJSON('/data/gemma_picks.json?v=' + Date.now())
      } catch {
        data = {}
      }
      set({ gemmaData: data })
      return data
    })()

    try {
      return await _loadGemmaPromise
    } finally {
      _loadGemmaPromise = null
    }
  },

  openLightbox(photo, photoList, minimal) {
    if (photoList && photoList.length > 0) {
      let index = photoList.findIndex(p => p.id === photo.id)
      if (index < 0) index = 0
      set({ lightboxOpen: true, lightboxPhotos: photoList, lightboxIndex: index, lightboxMinimal: !!minimal })
    } else {
      set({ lightboxOpen: true, lightboxPhotos: [photo], lightboxIndex: 0, lightboxMinimal: !!minimal })
    }
  },

  closeLightbox() {
    set({ lightboxOpen: false, lightboxPhotos: [], lightboxIndex: -1, lightboxMinimal: false })
  },

  navigateLightbox(dir) {
    const { lightboxPhotos, lightboxIndex } = get()
    if (lightboxPhotos.length === 0 || lightboxIndex < 0) return
    const newIdx = lightboxIndex + dir
    if (newIdx < 0 || newIdx >= lightboxPhotos.length) return
    set({ lightboxIndex: newIdx })
  },
}))
