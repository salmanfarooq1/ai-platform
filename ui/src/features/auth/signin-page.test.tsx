import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { api } from '@/api/endpoints'
import type { SessionInfo } from '@/api/types'
import { ROUTER_FUTURE } from '@/app/future'
import { SessionProvider } from '@/app/session'
import { walkthroughSeen } from '@/features/walkthrough/walkthrough-store'
import { testClient } from '@/test/render'
import SignInPage from './signin-page'

const info: SessionInfo = { csrf_token: 'c', expires_at: '2026-09-15T00:00:00Z', preview: false, principal: { id: 'p', kind: 'user', name: 'u' }, tenant: { id: 't', slug: 'x' }, scopes: ['query'] }

function Where() { const l = useLocation(); return <p data-testid="where">{l.pathname}</p> }

function page(state?: { from: string }) {
  vi.spyOn(api, 'getSession').mockRejectedValue(new ApiError(401, 'unauthenticated', 'no', null))
  vi.spyOn(api, 'health').mockResolvedValue({ mode: 'local' } as never)
  vi.spyOn(api, 'signIn').mockResolvedValue(info)
  return render(
    <QueryClientProvider client={testClient()}>
      <MemoryRouter future={ROUTER_FUTURE} initialEntries={[{ pathname: '/signin', state }]}>
        <SessionProvider>
          <Routes><Route path="/signin" element={<SignInPage />} /><Route path="*" element={<Where />} /></Routes>
        </SessionProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function signIn() {
  await userEvent.type(await screen.findByLabelText('API key'), 'gap_key')
  await userEvent.click(screen.getByRole('button', { name: /^Sign in$/ }))
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('SignInPage destination', () => {
  it('opens the walkthrough the first time, and remembers it', async () => {
    page()
    await signIn()
    expect(await screen.findByTestId('where')).toHaveTextContent('/app/walkthrough')
    expect(walkthroughSeen()).toBe(true)
  })

  it('opens the Overview after the walkthrough has been seen', async () => {
    localStorage.setItem('walkthrough-seen', '1')
    page()
    await signIn()
    expect(await screen.findByTestId('where')).toHaveTextContent(/^\/app$/)
  })

  it('returns to the page that was asked for, whatever the first-run rule says', async () => {
    page({ from: '/app/decisions' })
    await signIn()
    expect(await screen.findByTestId('where')).toHaveTextContent('/app/decisions')
    expect(walkthroughSeen()).toBe(false)
  })
})
