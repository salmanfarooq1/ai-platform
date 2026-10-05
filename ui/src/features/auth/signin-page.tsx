import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { Logo } from '@/components/governance/logo'
import { useSession } from '@/app/session'
import { firstRunPath, markWalkthroughSeen } from '@/features/walkthrough/walkthrough-store'
import { SignInForm } from './signin-form'

export default function SignInPage() {
  const { session, isLoading, signIn, startPreview } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: false })
  // A new browser opens the walkthrough first. After that the app opens on the Overview.
  // The destination is fixed on the first render, so marking the walkthrough as seen cannot change it.
  const requested = (location.state as { from?: string } | null)?.from
  const from = useRef(requested && requested !== '/app' ? requested : firstRunPath()).current
  useEffect(() => { if (session && from === '/app/walkthrough') markWalkthroughSeen() }, [session, from])

  if (!isLoading && session) return <Navigate to={from} replace />

  /** Go to the destination, and remember that the walkthrough was opened. */
  function leave() {
    if (from === '/app/walkthrough') markWalkthroughSeen()
    navigate(from, { replace: true })
  }

  const previewAvailable = health.data?.mode === 'public-preview'
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-4 py-10">
      <Logo />
      <div>
        <h1>Sign in</h1>
        <p className="mt-1 text-callout text-fg-secondary">Use an API key issued for your tenant.</p>
      </div>
      <SignInForm
        onSubmit={async (key) => { await signIn(key); leave() }}
        onPreview={previewAvailable ? async () => { await startPreview(); leave() } : undefined}
      />
    </main>
  )
}
