import type { Photo, BorderCrop } from '../types/photo'
import { smartObjectPosition } from './cropUtils'
import type { NavigatorExtended } from './performanceTier'

type ImageTier = 'thumb' | 'mobile' | 'display'

/* ===== Srcset / Multi-Resolution ===== */
const TIER_WIDTHS: Record<ImageTier, number> = {
  thumb: 480,
  mobile: 1280,
  display: 2048,
}

/** Default `sizes` per tier context */
const DEFAULT_SIZES: Record<ImageTier, string> = {
  thumb:   '(max-width: 640px) 50vw, 320px',
  mobile:  '(max-width: 640px) 100vw, 50vw',
  display: '100vw',
}

/**
 * Build srcset string from a photo's available tiers.
 * Returns empty string if photo has no distinct tier URLs (e.g. variants).
 */
function buildSrcset(photo: Photo): string {
  const urls: string[] = []
  const seen = new Set<string>()
  for (const tier of ['thumb', 'mobile', 'display'] as const) {
    const url = photo[tier]
    if (url && !seen.has(url)) {
      seen.add(url)
      urls.push(`${url} ${TIER_WIDTHS[tier]}w`)
    }
  }
  // Only useful if we have at least 2 distinct URLs
  return urls.length >= 2 ? urls.join(', ') : ''
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

/* ===== Border Crop =====
   Uses clip-path instead of transform so it doesn't conflict
   with CSS transform animations (.img-loading, .img-blur-up). */
export function applyBorderCrop(img: HTMLImageElement, crop: BorderCrop): void {
  applyBorderClip(img, crop)
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

/*
 * Generation counter per <img> element.
 * Prevents stale callbacks when loadProgressive is called rapidly
 * (e.g. fast lightbox navigation) — only the latest call's callbacks execute.
 */
const _imgGen = new WeakMap<HTMLImageElement, number>()

export function loadProgressive(
  img: HTMLImageElement,
  photo: Photo,
  targetTier: 'thumb' | 'mobile' | 'display',
  sizes?: string,
): void {
  const target = photo[targetTier] || photo.thumb
  if (!target) return

  /* Bump generation — stale callbacks will see a mismatch and bail */
  const gen = (_imgGen.get(img) || 0) + 1
  _imgGen.set(img, gen)

  /* Prepare srcset for after the swap */
  const srcset = buildSrcset(photo)
  const imgSizes = sizes || DEFAULT_SIZES[targetTier]

  if (photo.palette?.[0] && img.parentElement
      && !img.parentElement.style.backgroundColor) {
    img.parentElement.style.backgroundColor = photo.palette[0] + '55'
  }

  {
    const parent = img.parentElement
    const pw = parent?.clientWidth
    const ph = parent?.clientHeight
    if (pw && ph) {
      img.style.objectPosition = smartObjectPosition(photo, pw / ph)
    } else if (photo.focus) {
      img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%'
    }
  }

  if (photo.border_crop) {
    applyBorderCrop(img, photo.border_crop)
  }

  /* Clear any previous srcset during blur phase */
  img.removeAttribute('srcset')
  img.removeAttribute('sizes')

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
  const swap = () => {
    if (_imgGen.get(img) !== gen) return /* stale — newer call superseded us */
    img.src = target
    /* Apply srcset so browser can pick optimal resolution on resize/DPR */
    if (srcset) {
      img.srcset = srcset
      img.sizes = imgSizes
    }
    img.classList.remove('img-blur-up')
    img.style.filter = ''
    img.style.transform = ''
    revealImg(img)
  }
  const doLoad = () => {
    if (_imgGen.get(img) !== gen) return
    DECODE_QUEUE.enqueue(pre).then(swap).catch(swap)
  }
  pre.onload = doLoad
  pre.onerror = () => {
    if (_imgGen.get(img) !== gen) return
    if (photo.micro && target !== photo.micro) {
      img.src = photo.micro
    }
    img.classList.remove('img-blur-up')
    revealImg(img)
  }
  pre.src = target
  if (pre.complete && pre.naturalWidth) doLoad()
}
