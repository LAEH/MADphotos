import { useState, useEffect } from 'react'
import { dataUrl } from '../config'

interface FetchState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

export function useFetch<T>(url: string | null): FetchState<T> {
  const [state, setState] = useState<FetchState<T>>({
    data: null,
    loading: !!url,
    error: null,
  })

  useEffect(() => {
    if (!url) {
      setState({ data: null, loading: false, error: null })
      return
    }

    let cancelled = false
    setState(s => ({ ...s, loading: true, error: null }))

    const resolved = dataUrl(url)

    fetch(resolved)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
        return r.json()
      })
      .then(data => {
        if (!cancelled) setState({ data, loading: false, error: null })
      })
      .catch(err => {
        if (!cancelled) setState({ data: null, loading: false, error: err.message })
      })

    return () => { cancelled = true }
  }, [url])

  return state
}
