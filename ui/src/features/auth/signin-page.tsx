import { useQuery } from '@tanstack/react-query'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { Logo } from '@/components/governance/logo'
import { useSession } from '@/app/session'
import { SignInForm } from './signin-form'

export default function SignInPage() {
  const { session, isLoading, signIn, startPreview } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: false })
  const from = (location.state as { from?: string } | null)?.from ?? '/app/ask'

  if (!isLoading && session) return <Navigate to={from} replace />

  const previewAvailable = health.data?.mode === 'public-preview'
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-4 py-10">
      <Logo />
      <div>
        <h1>Sign in</h1>
        <p className="mt-1 text-callout text-fg-secondary">Use an API key issued for your tenant.</p>
      </div>
      <SignInForm
        onSubmit={async (key) => { await signIn(key); navigate(from, { replace: true }) }}
        onPreview={previewAvailable ? async () => { await startPreview(); navigate(from, { replace: true }) } : undefined}
      />
    </main>
  )
}
