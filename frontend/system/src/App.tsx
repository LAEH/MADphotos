import { Routes, Route, Navigate } from 'react-router-dom'
import { ThemeContext, useThemeProvider } from './hooks/useTheme'
import { Layout } from './components/layout/Layout'
import { StatusPage } from './pages/StatusPage'
import { JournalPage } from './pages/JournalPage'
import { InstructionsPage } from './pages/InstructionsPage'
import { MosaicsPage } from './pages/MosaicsPage'

import { EnhancedPage } from './pages/EnhancedPage'
import { GemmaPage } from './pages/GemmaPage'
import { UnpickedPage } from './pages/UnpickedPage'
import { SignalInspectorPage } from './pages/SignalInspectorPage'
import { LocationPage } from './pages/LocationPage'
import { GeneratedPage } from './pages/GeneratedPage'
import { VariantReviewPage } from './pages/VariantReviewPage'
import { BentoExplainerPage } from './pages/BentoExplainerPage'

export default function App() {
  const themeCtx = useThemeProvider()

  return (
    <ThemeContext.Provider value={themeCtx}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="status" replace />} />
          <Route path="status" element={<StatusPage />} />
          <Route path="journal" element={<JournalPage />} />
          <Route path="instructions" element={<InstructionsPage />} />
          <Route path="review/unpicked" element={<UnpickedPage />} />
          <Route path="experiments/gemma" element={<GemmaPage />} />
          <Route path="experiments/mosaics" element={<MosaicsPage />} />

          <Route path="experiments/enhanced" element={<EnhancedPage />} />
          <Route path="experiments/signals" element={<SignalInspectorPage />} />
          <Route path="curation/location" element={<LocationPage />} />
          <Route path="experiments/generated" element={<GeneratedPage />} />
          <Route path="review/variants" element={<VariantReviewPage />} />
          <Route path="docs/bento" element={<BentoExplainerPage />} />
        </Route>
      </Routes>
    </ThemeContext.Provider>
  )
}
