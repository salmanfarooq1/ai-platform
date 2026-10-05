import { lazy, Suspense } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { Skeleton } from '@/components/ui/skeleton'
import { AppShell } from './shell'
import { useSession } from './session'

// Every route is its own lazy chunk. The landing page and How it works are the marketing chunk group: they are the
// only code that may load GSAP or three.js, and nothing under /app does.
const LandingPage = lazy(() => import('@/landing/landing-page'))
const HowItWorksPage = lazy(() => import('@/landing/how-it-works-page'))
const SignInPage = lazy(() => import('@/features/auth/signin-page'))
const OverviewPage = lazy(() => import('@/features/overview/overview-page'))
const WalkthroughPage = lazy(() => import('@/features/walkthrough/walkthrough-page'))
const AskPage = lazy(() => import('@/features/ask/ask-page'))
const LibraryPage = lazy(() => import('@/features/library/library-page'))
const HistoryPage = lazy(() => import('@/features/history/history-page'))
const RequestsPage = lazy(() => import('@/features/requests/requests-page'))
const DecisionsPage = lazy(() => import('@/features/decisions/decisions-page'))
const PoliciesPage = lazy(() => import('@/features/policies/policies-page'))
const KeysPage = lazy(() => import('@/features/keys/keys-page'))
const UsagePage = lazy(() => import('@/features/usage/usage-page'))
const RunsPage = lazy(() => import('@/features/runs/runs-page'))
const TrustPage = lazy(() => import('@/features/trust/trust-page'))
const SystemPage = lazy(() => import('@/features/system/system-page'))

function PageFallback() {
  return <div role="status" aria-label="Loading page" className="flex flex-col gap-3 p-1"><Skeleton className="h-8 w-48" /><Skeleton className="h-32" /></div>
}

function Lazy({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<PageFallback />}>{children}</Suspense>
}

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
      <Route path="/how-it-works" element={<Suspense fallback={<div className="min-h-screen" />}><HowItWorksPage /></Suspense>} />
      <Route path="/signin" element={<Lazy><SignInPage /></Lazy>} />
      <Route path="/app" element={<RequireSession />}>
        <Route element={<AppShell />}>
          <Route index element={<Lazy><OverviewPage /></Lazy>} />
          <Route path="walkthrough" element={<Lazy><WalkthroughPage /></Lazy>} />
          <Route path="ask" element={<Lazy><AskPage /></Lazy>} />
          <Route path="library" element={<Lazy><LibraryPage /></Lazy>} />
          <Route path="history" element={<Lazy><HistoryPage /></Lazy>} />
          <Route path="requests/:requestId?" element={<Lazy><RequestsPage /></Lazy>} />
          <Route path="decisions" element={<Lazy><DecisionsPage /></Lazy>} />
          <Route path="decisions/:id" element={<Lazy><DecisionsPage /></Lazy>} />
          <Route path="policies" element={<Lazy><PoliciesPage /></Lazy>} />
          <Route path="keys" element={<Lazy><KeysPage /></Lazy>} />
          <Route path="usage" element={<Lazy><UsagePage /></Lazy>} />
          <Route path="runs" element={<Lazy><RunsPage /></Lazy>} />
          <Route path="trust" element={<Lazy><TrustPage /></Lazy>} />
          <Route path="system" element={<Lazy><SystemPage /></Lazy>} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
