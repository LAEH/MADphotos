/* IsitSwipe — Standalone touch swipe handler for ISIT cards.
   Returns a cleanup function. Uses rAF-throttled touch tracking,
   velocity-aware exit, spring-back, and grab micro-interaction. */

const SWIPE_THRESHOLD = 80
const ROTATION_FACTOR = 0.03
const GRAB_SCALE = 0.985

interface SwipeCallbacks {
  onVote: (vote: 'accept' | 'reject', velocity: number) => void
  isAnimating: () => boolean
}

export function setupSwipe(card: HTMLElement, callbacks: SwipeCallbacks): () => void {
  let startX = 0
  let startY = 0
  let deltaX = 0
  let tracking = false
  let rafId = 0
  let dirLocked = false
  let swipeDir: 'h' | 'v' | null = null
  let vSamples: { x: number; t: number }[] = []

  function resetSwipe() {
    tracking = false
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = 0
    }
  }

  function onTouchStart(e: TouchEvent) {
    if (callbacks.isAnimating()) return
    startX = e.touches[0].clientX
    startY = e.touches[0].clientY
    deltaX = 0
    tracking = true
    dirLocked = false
    swipeDir = null
    vSamples = [{ x: startX, t: performance.now() }]
    card.style.transition = 'none'
    card.style.transform = `translate3d(0,0,0) scale(${GRAB_SCALE})`
  }

  function onTouchMove(e: TouchEvent) {
    if (!tracking) return
    const cx = e.touches[0].clientX
    const dx = cx - startX
    const dy = e.touches[0].clientY - startY

    if (!dirLocked && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
      dirLocked = true
      swipeDir = Math.abs(dx) >= Math.abs(dy) ? 'h' : 'v'
    }
    if (swipeDir === 'v') return
    e.preventDefault()
    deltaX = dx

    const now = performance.now()
    vSamples.push({ x: cx, t: now })
    if (vSamples.length > 3) vSamples.shift()

    if (!rafId) {
      rafId = requestAnimationFrame(() => {
        rafId = 0
        const rot = deltaX * ROTATION_FACTOR
        card.style.transform = `translate3d(${deltaX}px,0,0) rotate(${rot}deg)`
      })
    }
  }

  function endTouch() {
    if (!tracking) return
    resetSwipe()

    if (swipeDir === 'h' && Math.abs(deltaX) > SWIPE_THRESHOLD) {
      let vel = 0
      if (vSamples.length >= 2) {
        const a = vSamples[0]
        const b = vSamples[vSamples.length - 1]
        const dt = b.t - a.t
        if (dt > 0) vel = Math.abs(b.x - a.x) / dt
      }
      callbacks.onVote(deltaX > 0 ? 'accept' : 'reject', vel)
    } else {
      card.style.transition = 'transform 0.3s ease-out'
      card.style.transform = ''
    }
  }

  card.addEventListener('touchstart', onTouchStart, { passive: false })
  card.addEventListener('touchmove', onTouchMove, { passive: false })
  card.addEventListener('touchend', endTouch, { passive: true })
  card.addEventListener('touchcancel', endTouch, { passive: true })

  return () => {
    resetSwipe()
    card.removeEventListener('touchstart', onTouchStart)
    card.removeEventListener('touchmove', onTouchMove)
    card.removeEventListener('touchend', endTouch)
    card.removeEventListener('touchcancel', endTouch)
  }
}
