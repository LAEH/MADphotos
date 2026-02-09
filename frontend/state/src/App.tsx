import { Routes, Route } from 'react-router-dom'
import { ThemeContext, useThemeProvider } from './hooks/useTheme'
import { Layout } from './components/layout/Layout'
import { DashboardPage } from './pages/DashboardPage'
import { JournalPage } from './pages/JournalPage'
import { InstructionsPage } from './pages/InstructionsPage'
import { MosaicsPage } from './pages/MosaicsPage'
import { CartoonPage } from './pages/CartoonPage'
import { SimilarityPage } from './pages/SimilarityPage'
import { BlindTestPage } from './pages/BlindTestPage'
import { StatsPage } from './pages/StatsPage'
import { SignalInspectorPage } from './pages/SignalInspectorPage'
import { EmbeddingAuditPage } from './pages/EmbeddingAuditPage'
import { CollectionCoveragePage } from './pages/CollectionCoveragePage'
import { SeePage } from './pages/SeePage'

export default function App() {
  const themeCtx = useThemeProvider()

  return (
    <ThemeContext.Provider value={themeCtx}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="journal" element={<JournalPage />} />
          <Route path="instructions" element={<InstructionsPage />} />
          <Route path="mosaics" element={<MosaicsPage />} />
          <Route path="cartoon" element={<CartoonPage />} />
          <Route path="similarity" element={<SimilarityPage />} />
          <Route path="blind-test" element={<BlindTestPage />} />
          <Route path="signal-inspector" element={<SignalInspectorPage />} />
          <Route path="embedding-audit" element={<EmbeddingAuditPage />} />
          <Route path="collection-coverage" element={<CollectionCoveragePage />} />
          <Route path="see" element={<SeePage />} />
        </Route>
      </Routes>
    </ThemeContext.Provider>
  )
}
