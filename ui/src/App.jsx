import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Search from './pages/Search'
import Agent from './pages/Agent'
import Ingest from './pages/Ingest'
import Analytics from './pages/Analytics'
import Documents from './pages/Documents'
import { getHealth } from './api/health'
import { getConfig } from './api/config'

export default function App() {
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)

  // Health: poll every 30s — connectivity and uptime change
  useEffect(() => {
    async function check() {
      try { setHealth(await getHealth()) } catch { setHealth(null) }
    }
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  // Config: fetch once — static for the session
  useEffect(() => {
    getConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  return (
    <Routes>
      <Route element={<Layout health={health} />}>
        <Route index element={<Dashboard health={health} />} />
        <Route path="search"    element={<Search config={config} />} />
        <Route path="agent"     element={<Agent config={config} />} />
        <Route path="ingest"    element={<Ingest config={config} />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="documents" element={<Documents config={config} />} />
        <Route path="*"         element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
