import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import type { SessionInfo } from '@/api/types'
import { ROUTER_FUTURE } from './future'
import { SessionProvider } from './session'
import { SessionMenu } from './session-menu'
import { testClient } from '@/test/render'

const info = (over: Partial<SessionInfo> = {}): SessionInfo => ({
  csrf_token: 'csrf', expires_at: '2026-09-15T00:00:00Z', preview: false,
  principal: { id: 'p1', kind: 'user', name: 'e2e-user' }, tenant: { id: 't1', slug: 'northwind' }, scopes: ['audit:read', 'query'], ...over,
})

beforeEach(() => { localStorage.clear(); document.documentElement.removeAttribute('data-theme') })
afterEach(() => vi.restoreAllMocks())

function setup(session: SessionInfo) {
  vi.spyOn(api, 'getSession').mockResolvedValue(session)
  return render(
    <QueryClientProvider client={testClient()}>
      <MemoryRouter future={ROUTER_FUTURE}><SessionProvider><SessionMenu /></SessionProvider></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SessionMenu', () => {
  it('shows who you are, the tenant and the scopes', async () => {
    setup(info())
    await userEvent.click(await screen.findByRole('button', { name: 'Session menu' }))
    const who = await screen.findByTestId('session-identity')
    expect(who).toHaveTextContent('e2e-user')
    expect(who).toHaveTextContent('northwind')
    expect(within(who).getByText('audit:read')).toBeInTheDocument()
    expect(within(who).getByText('query')).toBeInTheDocument()
  })

  it('says when the session is a read-only preview', async () => {
    setup(info({ preview: true }))
    await userEvent.click(await screen.findByRole('button', { name: 'Session menu' }))
    expect(await screen.findByTestId('session-identity')).toHaveTextContent('read-only preview')
  })

  it('sets the theme and remembers it', async () => {
    setup(info())
    await userEvent.click(await screen.findByRole('button', { name: 'Session menu' }))
    await userEvent.click(await screen.findByRole('menuitemradio', { name: 'Dark' }))
    await waitFor(() => expect(document.documentElement).toHaveAttribute('data-theme', 'dark'))
    expect(localStorage.getItem('theme')).toBe('dark')
    await userEvent.click(screen.getByRole('button', { name: 'Session menu' }))
    expect(await screen.findByRole('menuitemradio', { name: 'Dark' })).toBeChecked()
    await userEvent.click(screen.getByRole('menuitemradio', { name: 'Match system' }))
    await waitFor(() => expect(document.documentElement).not.toHaveAttribute('data-theme'))
    expect(localStorage.getItem('theme')).toBeNull()
  })

  it('signs out', async () => {
    const out = vi.spyOn(api, 'signOut').mockResolvedValue()
    setup(info())
    await userEvent.click(await screen.findByRole('button', { name: 'Session menu' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Sign out' }))
    await waitFor(() => expect(out).toHaveBeenCalledOnce())
  })
})
