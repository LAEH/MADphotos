import type { Photo, BorderCrop } from '../types/photo'

type ImageTier = 'thumb' | 'mobile' | 'display'

interface NavigatorExtended extends Navigator {
  connection?: {
    saveData?: boolean
    effectiveType?: string
  }
}

/* ===== Decode Queue (browser-aware concurrency) ===== */
const DECODE_QUEUE = {
  max: /AppleWebKit.*Mobile/.test(navigator.userAgent) ? 2 :
       /AppleWebKit/.test(navigator.userAgent) ? 3 :
       /Android/.test(navigator.userAgent) ? 3 : 6,
  active: 0,
  pending: [] as { img: HTMLImageElement; resolve: () => void }[],
  enqueue(img: HTMLImageElement): Promise<void> {
    return new Promise(resolve => {
      this.pending.push({ img, resolve })
      this._drain()
    })
  },
  _drain() {
    while (this.active < this.max && this.pending.length) {
      this.active++
      const { img, resolve } = this.pending.shift()!
      ;(typeof img.decode === 'function' ? img.decode() : Promise.resolve())
        .then(resolve).catch(resolve)
        .finally(() => { this.active--; this._drain() })
    }
  }
}

/* ===== Image Tier Selection ===== */
export function optimalTier(role: 'card' | 'full'): ImageTier {
  const w = window.innerWidth
  const dpr = Math.min(devicePixelRatio || 1, 3)
  const cssW = role === 'card' ? Math.min(w, 600) : w
  const needed = cssW * dpr
  const nav = navigator as NavigatorExtended
  const slow = nav.connection &&
    (nav.connection.saveData ||
     nav.connection.effectiveType === '2g' ||
     nav.connection.effectiveType === 'slow-2g')

  if (slow) return needed <= 600 ? 'thumb' : 'mobile'
  if (needed <= 540) return 'thumb'
  if (needed <= 1400) return 'mobile'
  return 'display'
}

export function cardImageTier(): ImageTier {
  return optimalTier('card')
}

/* ===== Border Crop ===== */
export function applyBorderCrop(img: HTMLImageElement, crop: BorderCrop): void {
  const t = crop.top || 0, r = crop.right || 0
  const b = crop.bottom || 0, l = crop.left || 0
  const scaleX = 100 / (100 - l - r)
  const scaleY = 100 / (100 - t - b)
  const scale = Math.max(scaleX, scaleY)
  img.style.transform = 'scale(' + scale.toFixed(4) + ')'
}

export function applyBorderClip(img: HTMLImageElement, crop?: BorderCrop): void {
  if (!crop) { img.style.clipPath = ''; return }
  const t = crop.top || 0, r = crop.right || 0
  const b = crop.bottom || 0, l = crop.left || 0
  img.style.clipPath = 'inset(' + t + '% ' + r + '% ' + b + '% ' + l + '%)'
}

/* ===== Image Reveal ===== */
function revealImg(img: HTMLImageElement): void {
  img.classList.remove('img-loading')
  img.classList.add('img-loaded')

  function onEnd(e: TransitionEvent) {
    if (e.propertyName === 'opacity') {
      img.removeEventListener('transitionend', onEnd)
      img.classList.remove('img-loaded')
    }
  }
  img.addEventListener('transitionend', onEnd)

  setTimeout(() => {
    img.classList.remove('img-loaded')
    img.classList.remove('img-loading')
  }, 800)
}

/* ===== Progressive Image Loading ===== */
export function loadProgressive(
  img: HTMLImageElement,
  photo: Photo,
  targetTier: 'thumb' | 'mobile' | 'display'
): void {
  const target = photo[targetTier] || photo.thumb
  if (!target) return

  if (photo.palette?.[0] && img.parentElement
      && !img.parentElement.style.backgroundColor) {
    img.parentElement.style.backgroundColor = photo.palette[0] + '55'
  }

  if (photo.focus) {
    img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%'
  }

  if (photo.border_crop) {
    applyBorderCrop(img, photo.border_crop)
  }

  if (photo.micro) {
    img.src = photo.micro
    img.classList.add('img-blur-up')
    img.classList.remove('img-loading', 'img-loaded')
  } else {
    img.classList.add('img-loading')
    img.classList.remove('img-loaded', 'img-blur-up')
  }

  const pre = new Image()
  pre.decoding = 'async'
  pre.src = target
  const swap = () => {
    img.src = target
    img.classList.remove('img-blur-up')
    img.style.filter = ''
    img.style.transform = ''
    if (photo.border_crop) applyBorderCrop(img, photo.border_crop)
    revealImg(img)
  }
  const doLoad = () => {
    DECODE_QUEUE.enqueue(pre).then(swap).catch(swap)
  }
  pre.onload = doLoad
  pre.onerror = () => {
    if (photo.micro && target !== photo.micro) {
      img.src = photo.micro
    }
    img.classList.remove('img-blur-up')
    revealImg(img)
  }
  if (pre.complete && pre.naturalWidth) doLoad()
}
