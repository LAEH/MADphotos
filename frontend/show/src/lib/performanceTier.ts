export type PerformanceTier = 'tier-a' | 'tier-b' | 'tier-c'

export interface NavigatorExtended extends Navigator {
  deviceMemory?: number
  connection?: {
    saveData?: boolean
    effectiveType?: string
  }
}

export function detectTier(): PerformanceTier {
  const ua = navigator.userAgent
  const isWebKit = /AppleWebKit/.test(ua) && !/Chrome/.test(ua)
  const cores = navigator.hardwareConcurrency || 2
  const dpr = devicePixelRatio || 1
  const nav = navigator as NavigatorExtended
  const mem = nav.deviceMemory || 4
  const saveData = nav.connection?.saveData
  const slowNet = nav.connection?.effectiveType === '2g' || nav.connection?.effectiveType === 'slow-2g'

  if (saveData || slowNet || (cores <= 2 && mem <= 2)) {
    return 'tier-c'
  } else if (isWebKit && (cores >= 4 || mem >= 4)) {
    /* Modern WebKit: iPhone 12+, iPad Pro M1+, desktop Safari */
    return 'tier-a'
  } else if (!isWebKit && cores >= 4 && dpr <= 3 && mem >= 4) {
    /* High-end Chrome/Firefox desktop */
    return 'tier-a'
  } else {
    /* Old WebKit (iPad Air 2, iPhone SE 1), mid-range Android */
    return 'tier-b'
  }
}

export function applyTier(tier: PerformanceTier): void {
  document.documentElement.classList.add(tier)
}
