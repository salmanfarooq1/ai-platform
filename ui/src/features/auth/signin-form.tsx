import { useState, type FormEvent } from 'react'
import { isApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface SignInFormProps {
  onSubmit: (apiKey: string) => Promise<unknown>
  /** Shown only in public-preview mode. */
  onPreview?: () => Promise<unknown>
}

export function SignInForm({ onSubmit, onPreview }: SignInFormProps) {
  const [key, setKey] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<{ code: string; message: string; requestId: string | null } | null>(null)

  async function run(fn: () => Promise<unknown>) {
    setPending(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(isApiError(e)
        ? { code: e.code, message: e.message, requestId: e.requestId }
        : { code: 'unknown_error', message: 'Sign-in failed.', requestId: null })
    } finally {
      setPending(false)
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!key.trim()) return
    void run(() => onSubmit(key.trim()))
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3" aria-label="Sign in">
      <label htmlFor="api-key" className="text-callout font-medium">API key</label>
      <Input
        id="api-key"
        name="api_key"
        type="password"
        autoComplete="off"
        spellCheck={false}
        placeholder="Paste your API key"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? 'signin-error' : 'signin-hint'}
        className="mono"
      />
      <p id="signin-hint" className="text-footnote text-fg-secondary">
        The server checks the key and opens a session. The browser never stores the key.
      </p>
      {error ? (
        <p id="signin-error" role="alert" className="text-callout text-deny">
          {error.message}
          <span className="mono ml-2 text-footnote">{error.code}{error.requestId ? ` ${error.requestId}` : ''}</span>
        </p>
      ) : null}
      <Button type="submit" disabled={pending || !key.trim()}>{pending ? 'Signing in' : 'Sign in'}</Button>
      {onPreview ? (
        <Button type="button" variant="secondary" disabled={pending} onClick={() => void run(onPreview)}>
          Continue in read-only preview
        </Button>
      ) : null}
    </form>
  )
}
