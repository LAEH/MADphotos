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

  if (saveData || cores <= 2 || mem <= 2) {
    return 'tier-c'
  } else if (isWebKit || (cores >= 4 && dpr <= 3 && mem >= 4)) {
    return 'tier-a'
  } else {
    return 'tier-b'
  }
}

export function applyTier(tier: PerformanceTier): void {
  document.documentElement.classList.add(tier)
}
