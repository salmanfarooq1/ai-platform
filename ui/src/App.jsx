import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import Layout from './components/layout/Layout'
import Ask from './pages/Ask'
import Library from './pages/Library'
import Insights from './pages/Insights'
import System from './pages/System'
import { ToastProvider } from './context/ToastContext'
import { CollectionProvider } from './context/CollectionContext'
import { getHealth } from './api/health'
import { getConfig } from './api/config'

// Four destinations (BRANDING.md §6). Old routes redirect so bookmarks and
// links into the previous six-tab UI still land somewhere sensible.
export default function App() {
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)

  // Health: poll every 30s — connectivity and uptime change.
  useEffect(() => {
    async function check() {
      try { setHealth(await getHealth()) } catch { setHealth(null) }
    }
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  // Config: fetch once — static for the session.
  useEffect(() => {
    getConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  return (
    // Respect prefers-reduced-motion everywhere motion is used (BRANDING.md §12, §14)
    <MotionConfig reducedMotion="user">
      <ToastProvider>
        <CollectionProvider config={config}>
          <Routes>
            <Route element={<Layout health={health} />}>
              <Route index          element={<Ask config={config} />} />
              <Route path="library"  element={<Library config={config} />} />
              <Route path="insights" element={<Insights />} />
              <Route path="system"   element={<System health={health} config={config} />} />

              {/* Old six-tab routes → new four-destination routes */}
              <Route path="search"    element={<Navigate to="/" replace />} />
              <Route path="agent"     element={<Navigate to="/" replace />} />
              <Route path="ingest"    element={<Navigate to="/library" replace />} />
              <Route path="documents" element={<Navigate to="/library" replace />} />
              <Route path="analytics" element={<Navigate to="/insights" replace />} />
              <Route path="dashboard" element={<Navigate to="/system" replace />} />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </CollectionProvider>
      </ToastProvider>
    </MotionConfig>
  )
}
