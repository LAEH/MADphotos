import { useEffect, useRef } from 'react'

export function useViewCleanup() {
  const timers = useRef<number[]>([])

  const registerTimer = (id: number) => {
    timers.current.push(id)
    return id
  }

  useEffect(() => {
    return () => {
      for (const id of timers.current) {
        clearInterval(id)
        clearTimeout(id)
        cancelAnimationFrame(id)
      }
      timers.current = []
    }
  }, [])

  return { registerTimer }
}
