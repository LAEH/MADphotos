import { lazy, Suspense, useEffect, useState, useCallback } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useAppStore } from './store/appStore'
import { Shell } from './components/layout/Shell'
import { ErrorBoundary } from './components/ErrorBoundary'
import { EXPERIENCES } from './components/layout/experiences'

const BentoView = lazy(() => import('./views/BentoView').then(m => ({ default: m.BentoView })))
const BoomView = lazy(() => import('./views/BoomView').then(m => ({ default: m.BoomView })))
const GameView = lazy(() => import('./views/GameView').then(m => ({ default: m.GameView })))
const IsitView = lazy(() => import('./views/IsitView').then(m => ({ default: m.IsitView })))
const ScrollView = lazy(() => import('./views/ScrollView').then(m => ({ default: m.ScrollView })))
const AllView = lazy(() => import('./views/AllView').then(m => ({ default: m.AllView })))
const LovedView = lazy(() => import('./views/LovedView').then(m => ({ default: m.LovedView })))

/* Derive valid routes from the single source of truth */
const VALID_ROUTES = new Set(EXPERIENCES.map(e => e.route))

export function App() {
  const loadData = useAppStore(s => s.loadData)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const attemptLoad = useCallback(() => {
    setError(false)
    loadData()
      .then(() => setLoaded(true))
      .catch(() => setError(true))
  }, [loadData])

  useEffect(() => {
    attemptLoad()
  }, [attemptLoad])

  /* Hash-compat redirect: if user arrives with /#bento, navigate to /bento */
  useEffect(() => {
    if (location.hash && location.pathname === '/') {
      const route = location.hash.slice(1)
      if (VALID_ROUTES.has(route)) {
        navigate('/' + route, { replace: true })
      }
    }
  }, [location.hash, location.pathname, navigate])

  if (error) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 16, color: 'var(--text-muted)' }}>
        <p style={{ margin: 0 }}>Failed to load photos.</p>
        <button
          onClick={attemptLoad}
          style={{
            padding: '8px 20px', border: '1px solid currentColor',
            borderRadius: 8, background: 'none', color: 'inherit',
            cursor: 'pointer', fontSize: 14,
          }}
        >
          Retry
        </button>
      </div>
    )
  }

  if (!loaded) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--text-muted)' }}>
        Curating your photographs
      </div>
    )
  }

  return (
    <Shell>
      <ErrorBoundary>
        <Suspense fallback={null}>
          <Routes>
            <Route path="/bento" element={<BentoView />} />
            <Route path="/game" element={<GameView />} />
            <Route path="/boom" element={<BoomView />} />
            <Route path="/isit" element={<IsitView />} />
            <Route path="/scroll" element={<ScrollView />} />
            <Route path="/all" element={<AllView />} />
            <Route path="/loved" element={<LovedView />} />
            <Route path="*" element={<Navigate to="/bento" replace />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </Shell>
  )
}
