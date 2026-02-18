import { useState, useEffect, useCallback, type ImgHTMLAttributes } from 'react'
import { imageUrl } from '../config'
import { PageShell } from '../components/layout/PageShell'

function FadeImg({ style, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className={`img-wrap${loaded ? ' loaded' : ''}`} style={{ width: '100%', height: '100%', ...style }}>
      <img {...props} onLoad={() => setLoaded(true)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
    </div>
  )
}

interface LocationPhoto {
  uuid: string
  category: string
  thumb_url: string
}

interface LocationData {
  photos: LocationPhoto[]
  locations: string[]
  tagged_count: number
  total_count: number
}

export function LocationPage() {
  const [data, setData] = useState<LocationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [tagging, setTagging] = useState(false)
  const [taggedInSession, setTaggedInSession] = useState(0)

  const fetchData = useCallback(() => {
    setLoading(true)
    setError(null)
    fetch('/api/locations')
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then((d: LocationData) => { setData(d); setIndex(0); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const photo = data?.photos[index]
  const totalTagged = (data?.tagged_count ?? 0) + taggedInSession
  const totalCount = data?.total_count ?? 0

  const handleTag = useCallback((location: string) => {
    if (!photo || tagging) return
    setTagging(true)
    fetch('/api/location/tag', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uuid: photo.uuid, location }),
    })
      .then(r => r.json())
      .then(() => {
        setTaggedInSession(n => n + 1)
        setIndex(i => i + 1)
        setTagging(false)
      })
      .catch(() => { setTagging(false) })
  }, [photo, tagging])

  const handleSkip = useCallback(() => {
    setIndex(i => i + 1)
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    if (!data) return
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      const locations = data.locations
      if (e.key >= '1' && e.key <= String(locations.length)) {
        e.preventDefault()
        handleTag(locations[parseInt(e.key) - 1])
      } else if (e.key === 's' || e.key === 'S') {
        e.preventDefault()
        handleSkip()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [data, handleTag, handleSkip])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading locations...</div>
  if (error) return <div style={{ color: 'var(--red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  const remaining = data.photos.length - index

  if (remaining <= 0) {
    return (
      <PageShell title="Location Tagger" subtitle={`${totalTagged} / ${totalCount} tagged`}>
        <div className="sys-card" style={{ textAlign: 'center', padding: 'var(--space-16)' }}>
          <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: 'var(--space-3)' }}>
            All done
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)' }}>
            No more untagged picks remaining.
          </div>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell title="Location Tagger" subtitle={`${totalTagged} / ${totalCount} tagged`}>
      <div className="loc-grid">
        <div className="loc-image">
          <FadeImg
            key={photo!.uuid}
            src={imageUrl(photo!.thumb_url)}
            alt={photo!.uuid}
          />
        </div>
        <div className="loc-panel">
          <div className="loc-meta">
            <span style={{ fontFamily: 'var(--mono)', fontSize: 'var(--text-xs)', color: 'var(--muted)', opacity: 0.5 }}>
              {photo!.uuid.slice(0, 8)}
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
              {photo!.category}
            </span>
          </div>
          <div className="loc-buttons">
            {data.locations.map((loc, i) => (
              <button
                key={loc}
                className="loc-btn"
                onClick={() => handleTag(loc)}
                disabled={tagging}
              >
                <span className="loc-btn-key">{i + 1}</span>
                {loc}
              </button>
            ))}
            <button
              className="loc-btn loc-btn-skip"
              onClick={handleSkip}
              disabled={tagging}
            >
              <span className="loc-btn-key">S</span>
              Skip
            </button>
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', marginTop: 'auto' }}>
            {remaining} remaining
          </div>
        </div>
      </div>
    </PageShell>
  )
}
