import { lazy, Suspense, useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useAppStore } from './store/appStore'
import { Shell } from './components/layout/Shell'

const ColorsView = lazy(() => import('./views/ColorsView').then(m => ({ default: m.ColorsView })))
const BentoView = lazy(() => import('./views/BentoView').then(m => ({ default: m.BentoView })))
const BoomView = lazy(() => import('./views/BoomView').then(m => ({ default: m.BoomView })))
const GameView = lazy(() => import('./views/GameView').then(m => ({ default: m.GameView })))
const IsitView = lazy(() => import('./views/IsitView').then(m => ({ default: m.IsitView })))
const ScrollView = lazy(() => import('./views/ScrollView').then(m => ({ default: m.ScrollView })))

export function App() {
  const loadData = useAppStore(s => s.loadData)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    loadData()
      .then(() => setLoaded(true))
      .catch(() => setError(true))
  }, [loadData])

  /* Hash-compat redirect: if user arrives with /#couleurs, navigate to /couleurs */
  useEffect(() => {
    if (location.hash && location.pathname === '/') {
      const route = location.hash.slice(1)
      const validRoutes = ['couleurs', 'bento', 'game', 'boom', 'isit', 'scroll']
      if (validRoutes.includes(route)) {
        navigate('/' + route, { replace: true })
      }
    }
  }, [location.hash, location.pathname, navigate])

  if (error) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--text-muted)' }}>
        Failed to load photos. Check data/photos.json.
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
      <Suspense fallback={null}>
        <Routes>
          <Route path="/couleurs" element={<ColorsView />} />
          <Route path="/bento" element={<BentoView />} />
          <Route path="/game" element={<GameView />} />
          <Route path="/boom" element={<BoomView />} />
          <Route path="/isit" element={<IsitView />} />
          <Route path="/scroll" element={<ScrollView />} />
          <Route path="*" element={<Navigate to="/isit" replace />} />
        </Routes>
      </Suspense>
    </Shell>
  )
}
