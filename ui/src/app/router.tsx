import { lazy, Suspense } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { Skeleton } from '@/components/ui/skeleton'
import AskPage from '@/features/ask/ask-page'
import SignInPage from '@/features/auth/signin-page'
import DecisionsPage from '@/features/decisions/decisions-page'
import HistoryPage from '@/features/history/history-page'
import KeysPage from '@/features/keys/keys-page'
import LibraryPage from '@/features/library/library-page'
import PoliciesPage from '@/features/policies/policies-page'
import RunsPage from '@/features/runs/runs-page'
import SystemPage from '@/features/system/system-page'
import TrustPage from '@/features/trust/trust-page'
import UsagePage from '@/features/usage/usage-page'
import { AppShell } from './shell'
import { useSession } from './session'

// The landing page is its own chunk. It is the only place that loads GSAP and three.js.
const LandingPage = lazy(() => import('@/landing/landing-page'))

function RequireSession() {
  const { session, isLoading } = useSession()
  const location = useLocation()
  if (isLoading) return <div role="status" aria-label="Loading session" className="p-6"><Skeleton className="h-8 w-48" /></div>
  if (!session) return <Navigate to="/signin" replace state={{ from: location.pathname + location.search }} />
  return <Outlet />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Suspense fallback={<div className="min-h-screen" />}><LandingPage /></Suspense>} />
      <Route path="/signin" element={<SignInPage />} />
      <Route path="/app" element={<RequireSession />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="ask" replace />} />
          <Route path="ask" element={<AskPage />} />
          <Route path="library" element={<LibraryPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="decisions" element={<DecisionsPage />} />
          <Route path="decisions/:id" element={<DecisionsPage />} />
          <Route path="policies" element={<PoliciesPage />} />
          <Route path="keys" element={<KeysPage />} />
          <Route path="usage" element={<UsagePage />} />
          <Route path="runs" element={<RunsPage />} />
          <Route path="trust" element={<TrustPage />} />
          <Route path="system" element={<SystemPage />} />
          <Route path="*" element={<Navigate to="/app/ask" replace />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
