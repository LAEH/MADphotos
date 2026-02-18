import { Routes, Route, Navigate } from 'react-router-dom'
import { ThemeContext, useThemeProvider } from './hooks/useTheme'
import { Layout } from './components/layout/Layout'
import { StatusPage } from './pages/StatusPage'
import { JournalPage } from './pages/JournalPage'
import { InstructionsPage } from './pages/InstructionsPage'
import { MosaicsPage } from './pages/MosaicsPage'
import { CartoonPage } from './pages/CartoonPage'
import { GemmaCartoonPage } from './pages/GemmaCartoonPage'
import { BlindTestPage } from './pages/BlindTestPage'
import { GemmaPage } from './pages/GemmaPage'
import { DatabasePage } from './pages/DatabasePage'
import { UnpickedPage } from './pages/UnpickedPage'

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
          <Route path="db/overview" element={<DatabasePage />} />
          <Route path="experiments/gemma" element={<GemmaPage />} />
          <Route path="experiments/mosaics" element={<MosaicsPage />} />
          <Route path="experiments/cartoon" element={<CartoonPage />} />
          <Route path="experiments/gemma-cartoon" element={<GemmaCartoonPage />} />
          <Route path="experiments/blind-test" element={<BlindTestPage />} />
        </Route>
      </Routes>
    </ThemeContext.Provider>
  )
}
