export function hexToHue(hex: string): number {
  if (!hex || hex.length < 7) return -1
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const d = max - min
  if (d < 0.08) return -1
  const l = (max + min) / 2
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  if (s < 0.12) return -1
  let h: number
  if (max === r) h = ((g - b) / d + 6) % 6
  else if (max === g) h = (b - r) / d + 2
  else h = (r - g) / d + 4
  return h * 60
}

export function hexToLightness(hex: string): number {
  if (!hex || hex.length < 7) return 50
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  return ((Math.max(r, g, b) + Math.min(r, g, b)) / 2) * 100
}

export function hueDiff(h1: number, h2: number): number {
  const d = Math.abs(h1 - h2)
  return d > 180 ? 360 - d : d
}

export function hueLabel(h: number): string {
  if (h < 15 || h >= 345) return 'red'
  if (h < 45) return 'orange'
  if (h < 75) return 'yellow'
  if (h < 150) return 'green'
  if (h < 210) return 'cyan'
  if (h < 270) return 'blue'
  if (h < 330) return 'purple'
  return 'pink'
}
