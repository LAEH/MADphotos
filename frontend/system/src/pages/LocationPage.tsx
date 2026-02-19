import { useState, useEffect, useCallback, useRef, type ImgHTMLAttributes } from 'react'
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
  predicted: string | null
}

interface ObjectOption {
  label: string
  count: number
}

interface LocationData {
  photos: LocationPhoto[]
  locations: string[]
  tagged_count: number
  total_count: number
  cameras: string[]
  objects: ObjectOption[]
}

interface HistoryEntry {
  uuid: string
  action: 'tagged' | 'skipped'
  location?: string
}

export function LocationPage() {
  const [data, setData] = useState<LocationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [tagging, setTagging] = useState(false)
  const [taggedInSession, setTaggedInSession] = useState(0)
  const [newLoc, setNewLoc] = useState('')
  const [addedLocations, setAddedLocations] = useState<string[]>([])
  const [camera, setCamera] = useState<string>('')
  const [objFilter, setObjFilter] = useState<string>('')
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const fetchData = useCallback((cam?: string, obj?: string) => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams()
    if (cam) params.set('camera', cam)
    if (obj) params.set('obj', obj)
    const qs = params.toString() ? `?${params}` : ''
    fetch(`/api/locations${qs}`)
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then((d: LocationData) => { setData(d); setIndex(0); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  useEffect(() => { fetchData(camera, objFilter) }, [fetchData, camera, objFilter])

  const photo = data?.photos[index]
  const totalTagged = (data?.tagged_count ?? 0) + taggedInSession
  const totalCount = data?.total_count ?? 0
  const allLocs = data ? [...data.locations, ...addedLocations] : []
  const predicted = photo?.predicted || null

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
        setHistory(h => [...h, { uuid: photo.uuid, action: 'tagged', location }])
        setTaggedInSession(n => n + 1)
        setIndex(i => i + 1)
        setTagging(false)
      })
      .catch(() => { setTagging(false) })
  }, [photo, tagging])

  const handleSkip = useCallback(() => {
    if (!photo) return
    setHistory(h => [...h, { uuid: photo.uuid, action: 'skipped' }])
    setIndex(i => i + 1)
  }, [photo])

  const handleUndo = useCallback(() => {
    if (!history.length || tagging) return
    const last = history[history.length - 1]
    setHistory(h => h.slice(0, -1))
    setIndex(i => i - 1)
    if (last.action === 'tagged') {
      setTaggedInSession(n => n - 1)
      fetch('/api/location/untag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uuid: last.uuid }),
      }).catch(() => {})
    }
  }, [history, tagging])

  const handleAddLocation = useCallback(() => {
    const name = newLoc.trim()
    if (!name || !data) return
    if (data.locations.includes(name) || addedLocations.includes(name)) return
    setAddedLocations(prev => [...prev, name])
    setNewLoc('')
    inputRef.current?.focus()
    fetch('/api/location/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).catch(() => {})
  }, [newLoc, data, addedLocations])

  // Keyboard shortcuts
  useEffect(() => {
    if (!data) return
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'Backspace' || e.key === 'z' || e.key === 'Z') {
        e.preventDefault()
        handleUndo()
      } else if (e.key >= '1' && e.key <= '9' && parseInt(e.key) <= allLocs.length) {
        e.preventDefault()
        handleTag(allLocs[parseInt(e.key) - 1])
      } else if (e.key === 's' || e.key === 'S') {
        e.preventDefault()
        handleSkip()
      } else if (e.key === 'Enter' && predicted) {
        e.preventDefault()
        handleTag(predicted)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [data, allLocs, handleTag, handleSkip, handleUndo, predicted])

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading locations...</div>
  if (error) return <div style={{ color: 'var(--red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  const remaining = data.photos.length - index

  if (remaining <= 0) {
    return (
      <PageShell title="Location Tagger" subtitle={`${totalTagged} / ${totalCount} tagged`}>
        {(data.cameras.length > 0 || data.objects.length > 0) && (
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <select
              value={camera}
              onChange={e => { setCamera(e.target.value); setTaggedInSession(0) }}
              style={{
                padding: '4px 8px', fontSize: 'var(--text-xs)',
                background: 'var(--bg-secondary)', color: 'var(--text)',
                border: '1px solid var(--border)', borderRadius: '6px',
              }}
            >
              <option value="">All cameras</option>
              {data.cameras.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <select
              value={objFilter}
              onChange={e => { setObjFilter(e.target.value); setTaggedInSession(0) }}
              style={{
                padding: '4px 8px', fontSize: 'var(--text-xs)', marginLeft: '6px',
                background: 'var(--bg-secondary)', color: 'var(--text)',
                border: '1px solid var(--border)', borderRadius: '6px',
              }}
            >
              <option value="">All objects</option>
              {data.objects.map(o => <option key={o.label} value={o.label}>{o.label} ({o.count})</option>)}
            </select>
          </div>
        )}
        <div className="sys-card" style={{ textAlign: 'center', padding: 'var(--space-16)' }}>
          <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: 'var(--space-3)' }}>
            All done
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 'var(--text-sm)' }}>
            No more untagged picks remaining{camera || objFilter ? ` for ${[camera, objFilter].filter(Boolean).join(' + ')}` : ''}.
          </div>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell title="Location Tagger" subtitle={`${totalTagged} / ${totalCount} tagged`}>
      {/* Camera filter */}
      {(data.cameras.length > 0 || data.objects.length > 0) && (
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <select
            value={camera}
            onChange={e => { setCamera(e.target.value); setTaggedInSession(0) }}
            style={{
              padding: '4px 8px', fontSize: 'var(--text-xs)',
              background: 'var(--bg-secondary)', color: 'var(--text)',
              border: '1px solid var(--border)', borderRadius: '6px',
            }}
          >
            <option value="">All cameras</option>
            {data.cameras.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            value={objFilter}
            onChange={e => { setObjFilter(e.target.value); setTaggedInSession(0) }}
            style={{
              padding: '4px 8px', fontSize: 'var(--text-xs)', marginLeft: '6px',
              background: 'var(--bg-secondary)', color: 'var(--text)',
              border: '1px solid var(--border)', borderRadius: '6px',
            }}
          >
            <option value="">All objects</option>
            {data.objects.map(o => <option key={o.label} value={o.label}>{o.label} ({o.count})</option>)}
          </select>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', marginLeft: '8px' }}>
            {remaining} in view
          </span>
        </div>
      )}

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

          {/* Prediction banner */}
          {predicted && (
            <button
              className="loc-predict"
              onClick={() => handleTag(predicted)}
              disabled={tagging}
            >
              <span className="loc-predict-label">{predicted}</span>
              <span className="loc-predict-hint">Enter</span>
            </button>
          )}

          {/* Compact inline location chips */}
          <div className="loc-chips">
            {allLocs.map((loc) => (
              <button
                key={loc}
                className={`loc-chip${loc === predicted ? ' loc-chip-predicted' : ''}`}
                onClick={() => handleTag(loc)}
                disabled={tagging}
              >
                {loc}
              </button>
            ))}
            <button
              className="loc-chip loc-chip-skip"
              onClick={handleSkip}
              disabled={tagging}
            >
              Skip
            </button>
            {history.length > 0 && (
              <button
                className="loc-chip loc-chip-undo"
                onClick={handleUndo}
                disabled={tagging}
              >
                Undo
              </button>
            )}
          </div>

          {/* Add new location */}
          <div style={{ display: 'flex', gap: '6px' }}>
            <input
              ref={inputRef}
              type="text"
              value={newLoc}
              onChange={e => setNewLoc(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleAddLocation() }}
              placeholder="New location..."
              style={{
                flex: 1, padding: '4px 8px', fontSize: 'var(--text-xs)',
                background: 'var(--bg-secondary)', color: 'var(--text)',
                border: '1px solid var(--border)', borderRadius: '6px',
              }}
            />
            <button
              className="loc-chip"
              onClick={handleAddLocation}
              disabled={!newLoc.trim()}
              style={{ padding: '4px 10px' }}
            >
              +
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
