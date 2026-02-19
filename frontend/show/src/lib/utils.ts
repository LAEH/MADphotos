export function shuffleArray<T>(arr: T[]): T[] {
  const copy = arr.slice()
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

/** Pick a random element. Callers must ensure arr is non-empty. */
export function randomFrom<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

export function debounce<T extends (...args: never[]) => void>(
  fn: T,
  ms: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout>
  return (...args: Parameters<T>) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }
}

export function titleCase(str: string): string {
  if (!str) return ''
  return str.replace(/\b\w/g, c => c.toUpperCase())
}

export function canonKey(idA: string, idB: string): string {
  return idA < idB ? idA + '|' + idB : idB + '|' + idA
}
