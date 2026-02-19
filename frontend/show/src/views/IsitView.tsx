import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import { cardImageTier } from '../lib/imageLoading'
import { setupSwipe } from './isit/IsitSwipe'
import { IsitMinimap } from './isit/IsitMinimap'
import { IsitPills } from './isit/IsitPills'
import { fireAndForget } from '../lib/firebase'
import type { Photo } from '../types/photo'
import './IsitView.css'

const PRELOAD_AHEAD = 10
const MIN_EXIT_V = 0.8

/* Module-level capability flags (set once during init, read by card builders) */
let _isitHasTouch = false
let _isitHasHover = false

interface LabelData {
  labels?: { label: string; category: string }[]
}

interface ActiveFilter {
  type: string
  value: string
}

interface CursorState {
  element: HTMLDivElement
  icon: HTMLDivElement
  x: number
  y: number
  targetX: number
  targetY: number
}

export function IsitView() {
  const data = useAppStore(s => s.data)
  const allPhotos = useAppStore(s => s.allPhotos)
  const votedData = useAppStore(s => s.votedData)
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [loadProgress, setLoadProgress] = useState(0)
  const [photos, setPhotos] = useState<Photo[]>([])
  const [index, setIndex] = useState(0)
  const [animating, setAnimating] = useState(false)
  const [votes, setVotes] = useState<Record<string, string>>({})
  const [labelsData, setLabelsData] = useState<Record<string, LabelData> | null>(null)
  const [activeFilter, setActiveFilter] = useState<ActiveFilter | null>(null)
  const [isMobile, setIsMobile] = useState(false)

  const stackRef = useRef<HTMLDivElement>(null)
  const cacheRef = useRef<Record<string, { src: string; img: HTMLImageElement; decoded: boolean }>>({})
  const animatingRef = useRef(false)
  const photosRef = useRef<Photo[]>([])
  const indexRef = useRef(0)
  const votesRef = useRef<Record<string, string>>({})
  const swipeCleanupRef = useRef<(() => void) | null>(null)
  const cursorRef = useRef<CursorState | null>(null)
  const allPhotosRef = useRef<Photo[]>([])

  /* Keep refs in sync */
  useEffect(() => { animatingRef.current = animating }, [animating])
  useEffect(() => { photosRef.current = photos }, [photos])
  useEffect(() => { indexRef.current = index }, [index])
  useEffect(() => { votesRef.current = votes }, [votes])
  useEffect(() => { allPhotosRef.current = allPhotos }, [allPhotos])

  /* Viewport lock */
  useEffect(() => {
    const html = document.documentElement
    const body = document.body
    html.style.overflow = 'hidden'
    body.style.overflow = 'hidden'
    html.style.position = 'fixed'
    html.style.inset = '0'
    html.style.width = '100%'
    return () => {
      body.classList.remove('picks-bg-reject', 'picks-bg-accept')
      html.style.overflow = ''
      body.style.overflow = ''
      html.style.position = ''
      html.style.inset = ''
      html.style.width = ''
    }
  }, [])

  /* Init: load photos, labels, votes */
  useEffect(() => {
    if (!data) return

    const mobile = window.innerWidth < window.innerHeight
    setIsMobile(mobile)
    const hasTouch = 'ontouchstart' in window

    /* Load votes from localStorage, merge with server votes */
    let localVotes: Record<string, string> = {}
    try { localVotes = JSON.parse(localStorage.getItem('isit-votes') || '{}') } catch { /* empty */ }
    if (votedData) {
      let merged = 0
      for (const [photo, vote] of Object.entries(votedData)) {
        if (!localVotes[photo]) { localVotes[photo] = vote; merged++ }
      }
      if (merged > 0) {
        try { localStorage.setItem('isit-votes', JSON.stringify(localVotes)) } catch { /* empty */ }
      }
    }
    setVotes(localVotes)

    /* Load labels data */
    fetch('/data/photo_labels.json?v=' + Date.now())
      .then(r => r.json())
      .then(d => setLabelsData(d))
      .catch(() => setLabelsData({}))

    /* Filter photos by orientation */
    const orientation = mobile ? 'portrait' : 'landscape'
    const filtered = data.photos.filter(p => p.orientation === orientation)
    const sorted = [...filtered].sort((a, b) => {
      const aestheticDiff = (b.aesthetic || 0) - (a.aesthetic || 0)
      if (Math.abs(aestheticDiff) > 1) return aestheticDiff
      return Math.abs((a.hue || 0) - (b.hue || 0))
    })

    allPhotosRef.current = sorted
    setPhotos(sorted)
    setIndex(0)

    /* Preload first 3 images + show loading */
    const tier = cardImageTier()
    const toPreload: string[] = []
    for (let i = 0; i < Math.min(3, sorted.length); i++) {
      const p = sorted[i]
      const src = p[tier] || p.mobile || p.thumb
      if (src) toPreload.push(src)
    }

    if (toPreload.length === 0) {
      setLoading(false)
      return
    }

    let loaded = 0
    const promises = toPreload.map(src =>
      new Promise<void>(resolve => {
        const img = new Image()
        const timeout = setTimeout(resolve, 5000)
        img.onload = img.onerror = () => {
          clearTimeout(timeout)
          loaded++
          setLoadProgress(Math.round((loaded / toPreload.length) * 100))
          resolve()
        }
        img.src = src
      })
    )

    Promise.all(promises).then(() => {
      setTimeout(() => setLoading(false), 200)
    })

    /* Store hasTouch/hasHover in closure for card building */
    ;_isitHasTouch = hasTouch
    ;_isitHasHover = window.matchMedia('(any-hover: hover)').matches
  }, [data, votedData])

  /* Preload buffer */
  const preloadBuffer = useCallback(() => {
    const tier = cardImageTier()
    const end = Math.min(indexRef.current + 1 + PRELOAD_AHEAD, photosRef.current.length)
    for (let i = indexRef.current + 1; i < end; i++) {
      const photo = photosRef.current[i]
      if (!photo || cacheRef.current[photo.id]) continue
      const src = photo[tier] || photo.mobile || photo.thumb
      if (!src) continue
      const img = new Image()
      img.decoding = 'async'
      img.src = src
      if (typeof img.decode === 'function') {
        img.decode()
          .then(() => { if (cacheRef.current[photo.id]) cacheRef.current[photo.id].decoded = true })
          .catch(() => {})
      }
      cacheRef.current[photo.id] = { src, img, decoded: false }
    }
  }, [])

  /* Build card image */
  const buildCardImage = useCallback((photo: Photo, isFront: boolean): HTMLImageElement => {
    const img = document.createElement('img')
    img.alt = photo.alt || photo.caption || ''
    img.draggable = false
    if (photo.focus) img.style.objectPosition = `${photo.focus[0]}% ${photo.focus[1]}%`

    const cached = cacheRef.current[photo.id]
    if (cached && cached.decoded) {
      img.src = cached.src
    } else {
      if (photo.thumb) img.src = photo.thumb
      const tier = cardImageTier()
      const fullSrc = cached ? cached.src : (photo[tier] || photo.mobile || photo.thumb)
      if (fullSrc && fullSrc !== photo.thumb) {
        const pre = cached ? cached.img : new Image()
        if (!cached) { pre.decoding = 'async'; pre.src = fullSrc }
        const doUpgrade = () => { if (img.isConnected !== false) img.src = fullSrc }
        if (cached?.img && typeof cached.img.decode === 'function') {
          cached.img.decode().then(doUpgrade).catch(doUpgrade)
        } else if (typeof pre.decode === 'function') {
          pre.decode().then(doUpgrade).catch(doUpgrade)
        } else {
          pre.onload = doUpgrade
        }
      }
    }
    if (isFront) img.fetchPriority = 'high'
    return img
  }, [])

  /* Custom cursor */
  const createCursor = useCallback((): CursorState => {
    if (cursorRef.current) return cursorRef.current

    const el = document.createElement('div')
    el.className = 'isit-custom-cursor'
    el.style.display = 'none'

    const icon = document.createElement('div')
    icon.className = 'isit-cursor-icon'

    const ring1 = document.createElement('div')
    ring1.className = 'isit-cursor-ring isit-cursor-ring-1'
    const ring2 = document.createElement('div')
    ring2.className = 'isit-cursor-ring isit-cursor-ring-2'

    el.appendChild(ring1)
    el.appendChild(ring2)
    el.appendChild(icon)
    document.body.appendChild(el)

    const state: CursorState = { element: el, icon, x: 0, y: 0, targetX: 0, targetY: 0 }
    cursorRef.current = state
    return state
  }, [])

  /* Animate cursor position */
  const updateCursorPosition = useCallback(() => {
    const cursor = cursorRef.current
    if (!cursor) return
    cursor.x += (cursor.targetX - cursor.x) * 0.2
    cursor.y += (cursor.targetY - cursor.y) * 0.2
    cursor.element.style.transform = `translate3d(${cursor.x}px, ${cursor.y}px, 0)`
    if (cursor.element.style.display !== 'none') {
      requestAnimationFrame(updateCursorPosition)
    }
  }, [])

  /* Setup hover zones on a card's image wrap */
  const setupHoverZones = useCallback((wrap: HTMLDivElement, voteCallback: (vote: 'accept' | 'reject') => void) => {
    const cursor = createCursor()
    const body = document.body

    const zoneReject = document.createElement('div')
    zoneReject.className = 'isit-hover-zone isit-hover-left'
    const iconReject = document.createElement('div')
    iconReject.className = 'isit-hover-icon isit-hover-icon-reject'
    iconReject.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>'
    zoneReject.appendChild(iconReject)

    const zoneAccept = document.createElement('div')
    zoneAccept.className = 'isit-hover-zone isit-hover-right'
    const iconAccept = document.createElement('div')
    iconAccept.className = 'isit-hover-icon isit-hover-icon-accept'
    iconAccept.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>'
    zoneAccept.appendChild(iconAccept)

    function clearBgTint() { body.classList.remove('picks-bg-reject', 'picks-bg-accept') }

    function showCursor(type: 'reject' | 'accept') {
      cursor.element.style.display = 'block'
      cursor.element.className = `isit-custom-cursor isit-cursor-${type}`
      cursor.icon.innerHTML = type === 'reject' ? '\uD83E\uDD4A' : '\u2B50\uFE0F'
      requestAnimationFrame(updateCursorPosition)
    }

    function hideCursor() { cursor.element.style.display = 'none' }
    function updateCursorPos(e: PointerEvent) { cursor.targetX = e.clientX; cursor.targetY = e.clientY }

    zoneReject.addEventListener('pointerenter', () => { zoneReject.classList.add('hovered'); clearBgTint(); body.classList.add('picks-bg-reject'); showCursor('reject') })
    zoneReject.addEventListener('pointermove', updateCursorPos)
    zoneReject.addEventListener('pointerleave', () => { zoneReject.classList.remove('hovered'); clearBgTint(); hideCursor() })
    zoneReject.addEventListener('click', (e) => { e.stopPropagation(); zoneReject.classList.remove('hovered'); clearBgTint(); hideCursor(); voteCallback('reject') })

    zoneAccept.addEventListener('pointerenter', () => { zoneAccept.classList.add('hovered'); clearBgTint(); body.classList.add('picks-bg-accept'); showCursor('accept') })
    zoneAccept.addEventListener('pointermove', updateCursorPos)
    zoneAccept.addEventListener('pointerleave', () => { zoneAccept.classList.remove('hovered'); clearBgTint(); hideCursor() })
    zoneAccept.addEventListener('click', (e) => { e.stopPropagation(); zoneAccept.classList.remove('hovered'); clearBgTint(); hideCursor(); voteCallback('accept') })

    wrap.appendChild(zoneReject)
    wrap.appendChild(zoneAccept)
  }, [createCursor, updateCursorPosition])

  /* Vote handler */
  const doVote = useCallback((vote: 'accept' | 'reject', swipeVelocity?: number) => {
    if (animatingRef.current) return
    if (indexRef.current >= photosRef.current.length) return

    setAnimating(true)
    animatingRef.current = true
    const photo = photosRef.current[indexRef.current]
    const stack = stackRef.current
    const card = stack?.querySelector('.isit-card-front') as HTMLElement | null

    /* Record vote */
    const newVotes = { ...votesRef.current, [photo.id]: vote }
    setVotes(newVotes)
    votesRef.current = newVotes
    try { localStorage.setItem('isit-votes', JSON.stringify(newVotes)) } catch { /* empty */ }

    /* Firestore */
    fireAndForget('isit-votes', {
      photo: photo.id,
      vote,
      device: window.innerWidth < window.innerHeight ? 'mobile' : 'desktop',
    })

    if (card) {
      const dir = vote === 'accept' ? 1 : -1
      const vel = Math.max(swipeVelocity || 0, MIN_EXIT_V)
      const dist = Math.min(200 + vel * 280, 600)
      const dur = Math.max(0.18, Math.min(0.38, 200 / (vel * 1000)))
      const rot = dir * Math.min(6 + vel * 5, 15)

      card.style.transition = `transform ${dur}s cubic-bezier(0.25, 0.46, 0.45, 0.94), opacity ${dur}s ease-out`
      card.style.transform = `translate3d(${dir * dist}px,0,0) rotate(${rot}deg)`
      card.style.opacity = '0'
      card.style.pointerEvents = 'none'

      let advanced = false
      const onEnd = () => {
        if (advanced) return
        advanced = true
        card.removeEventListener('transitionend', onEnd)
        advance()
      }
      card.addEventListener('transitionend', onEnd)
      setTimeout(onEnd, dur * 1000 + 50)
    } else {
      advance()
    }
  }, [])

  /* Advance to next card */
  const advance = useCallback(() => {
    const newIndex = indexRef.current + 1
    setIndex(newIndex)
    indexRef.current = newIndex
    setAnimating(false)
    animatingRef.current = false

    const stack = stackRef.current
    if (!stack) return

    if (newIndex >= photosRef.current.length) {
      stack.innerHTML = '<div class="isit-empty">No more photos to review</div>'
      return
    }

    /* Remove old front card */
    const oldFront = stack.querySelector('.isit-card-front')
    if (oldFront) oldFront.remove()

    /* Promote back card to front */
    const backCard = stack.querySelector('.isit-card-back') as HTMLElement | null
    if (backCard) {
      backCard.classList.add('isit-card-promoting')
      backCard.classList.remove('isit-card-back')
      backCard.classList.add('isit-card-front')
      setTimeout(() => backCard.classList.remove('isit-card-promoting'), 320)

      if (_isitHasTouch) {
        if (swipeCleanupRef.current) swipeCleanupRef.current()
        swipeCleanupRef.current = setupSwipe(backCard, {
          onVote: (v, vel) => doVote(v, vel),
          isAnimating: () => animatingRef.current,
        })
      }
      if (_isitHasHover) {
        const wrap = backCard.querySelector('.isit-image-wrap') as HTMLDivElement | null
        if (wrap) setupHoverZones(wrap, v => doVote(v))
      }
    }

    /* Build new back card */
    if (newIndex + 1 < photosRef.current.length) {
      const newBack = buildCard(photosRef.current[newIndex + 1], false)
      if (backCard) {
        stack.insertBefore(newBack, backCard)
      } else {
        stack.appendChild(newBack)
      }
    }

    preloadBuffer()
  }, [doVote, preloadBuffer, setupHoverZones])

  /* Build a card element imperatively */
  const buildCard = useCallback((photo: Photo, isFront: boolean): HTMLDivElement => {
    const card = document.createElement('div')
    card.className = 'isit-card' + (isFront ? ' isit-card-front' : ' isit-card-back')
    card.dataset.photoId = photo.id

    const wrap = document.createElement('div')
    wrap.className = 'isit-image-wrap'

    const img = buildCardImage(photo, isFront)
    wrap.appendChild(img)

    if (isFront && _isitHasHover) {
      setupHoverZones(wrap, v => doVote(v))
    }

    card.appendChild(wrap)
    return card
  }, [buildCardImage, setupHoverZones, doVote])

  /* Render the two-card stack imperatively */
  const renderStack = useCallback(() => {
    const stack = stackRef.current
    if (!stack) return

    const idx = indexRef.current
    const p = photosRef.current

    if (idx >= p.length) {
      stack.innerHTML = '<div class="isit-empty">No more photos to review</div>'
      return
    }

    stack.innerHTML = ''

    /* Back card (next photo) */
    if (idx + 1 < p.length) {
      stack.appendChild(buildCard(p[idx + 1], false))
    }

    /* Front card (current photo) */
    const front = buildCard(p[idx], true)
    stack.appendChild(front)

    if (_isitHasTouch) {
      if (swipeCleanupRef.current) swipeCleanupRef.current()
      swipeCleanupRef.current = setupSwipe(front, {
        onVote: (v, vel) => doVote(v, vel),
        isAnimating: () => animatingRef.current,
      })
    }

    preloadBuffer()
  }, [buildCard, doVote, preloadBuffer])

  /* Render stack when loading finishes or photos change */
  useEffect(() => {
    if (!loading && photos.length > 0) {
      renderStack()
    }
  }, [loading, photos, renderStack])

  /* Keyboard controls */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        doVote('reject')
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        doVote('accept')
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [doVote])

  /* Cleanup on unmount */
  useEffect(() => {
    return () => {
      if (swipeCleanupRef.current) swipeCleanupRef.current()
      if (cursorRef.current) {
        cursorRef.current.element.remove()
        cursorRef.current = null
      }
    }
  }, [])

  /* Go back to a previous card */
  const goBack = useCallback((targetIndex: number) => {
    const photo = photosRef.current[targetIndex]
    if (!photo) return

    const newVotes = { ...votesRef.current }
    delete newVotes[photo.id]
    setVotes(newVotes)
    votesRef.current = newVotes
    try { localStorage.setItem('isit-votes', JSON.stringify(newVotes)) } catch { /* empty */ }

    setIndex(targetIndex)
    indexRef.current = targetIndex
    setAnimating(false)
    animatingRef.current = false
    renderStack()
  }, [renderStack])

  /* Signal filtering */
  const filterBySignal = useCallback((signalType: string, signalValue: string) => {
    if (activeFilter && activeFilter.type === signalType && activeFilter.value === signalValue) {
      /* Clear filter */
      setActiveFilter(null)
      setPhotos(allPhotosRef.current)
      photosRef.current = allPhotosRef.current
      setIndex(0)
      indexRef.current = 0
    } else {
      setActiveFilter({ type: signalType, value: signalValue })
      const filtered = allPhotosRef.current.filter(p => {
        switch (signalType) {
          case 'consensus': return p.consensus && p.consensus.includes(signalValue)
          case 'scene': return p.scene === signalValue
          case 'emotion': return p.emotion === signalValue
          case 'vibe': return p.vibes && p.vibes.includes(signalValue)
          case 'time': return p.time === signalValue
          case 'grading': return p.grading === signalValue
          default: return true
        }
      })
      setPhotos(filtered)
      photosRef.current = filtered
      setIndex(0)
      indexRef.current = 0
    }
    /* Re-render will happen via the photos/index useEffect */
  }, [activeFilter])

  /* Floating buttons (desktop only) */
  const floatingButtons = !isMobile ? (
    <FloatingButtons photos={photos} navigate={navigate} />
  ) : null

  const currentPhoto = photos.length > 0 && index < photos.length ? photos[index] : null

  /* Loading screen */
  if (loading) {
    return (
      <div className="isit-container">
        <div className="isit-loader">
          <div className="isit-loader-content">
            <div className="isit-loader-spinner" />
            <div className="isit-loader-text">Loading images... {loadProgress}%</div>
            <div className="isit-loader-progress">
              <div className="isit-loader-bar" style={{ width: `${loadProgress}%` }} />
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="isit-container">
      <div className="isit-stack" ref={stackRef} />
      <div className="isit-bottom">
        <IsitPills
          photo={currentPhoto}
          labelsData={labelsData}
          isMobile={isMobile}
          activeFilter={activeFilter}
          onFilterSignal={filterBySignal}
        />
        <IsitMinimap
          photos={photos}
          index={index}
          votes={votes}
          onGoBack={goBack}
          animating={animating}
        />
      </div>
      {floatingButtons}
    </div>
  )
}

/* Floating glass disk + ninja button */
function FloatingButtons({ photos, navigate }: { photos: Photo[]; navigate: (path: string) => void }) {
  const diskRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!diskRef.current || photos.length === 0) return

    const disk = diskRef.current
    const diskImages: HTMLImageElement[] = []
    const count = Math.min(8, photos.length)
    const step = Math.max(1, Math.floor(photos.length / count))

    /* Clear old images */
    disk.innerHTML = ''

    for (let i = 0; i < count; i++) {
      const idx = Math.min(i * step, photos.length - 1)
      const photo = photos[idx]
      if (photo?.thumb) {
        const img = document.createElement('img')
        img.src = photo.thumb
        img.className = 'isit-disk-image'
        img.alt = ''
        img.draggable = false
        diskImages.push(img)
        disk.appendChild(img)
      }
    }

    let currentIdx = 0
    if (diskImages.length > 0) {
      diskImages[0].classList.add('active')
      const interval = setInterval(() => {
        diskImages[currentIdx].classList.remove('active')
        currentIdx = (currentIdx + 1) % diskImages.length
        diskImages[currentIdx].classList.add('active')
      }, 4000)
      return () => clearInterval(interval)
    }
  }, [photos])

  /* Navigate to next experience (bento) */
  const goNext = () => navigate('/bento')

  return (
    <div className="isit-floating-container">
      <button
        ref={diskRef}
        className="isit-float-disk isit-float-right"
        aria-label="Next: Bento"
        title="Next: Bento"
        onClick={goNext}
      />
      <button
        className="isit-float-btn isit-float-left"
        aria-label="Next: Bento"
        title="Next: Bento"
        onClick={goNext}
      >
        {'\uD83E\uDD77'}
      </button>
    </div>
  )
}
