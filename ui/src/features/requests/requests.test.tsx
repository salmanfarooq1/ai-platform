import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { api } from '@/api/endpoints'
import type { RequestDetail, RequestSummary } from '@/api/types'
import { indexReasons } from '@/lib/reasons'
import { CATALOGUE, decision } from '@/test/fixtures'
import { renderWithProviders, testClient } from '@/test/render'
import { REASONS_KEY } from '@/lib/reasons'
import { RequestDrawer } from './request-drawer'
import RequestsPage from './requests-page'
import { RequestsTable } from './requests-table'

const summary = (over: Partial<RequestSummary> = {}): RequestSummary => ({
  request_id: 'req-allow-1', started_at: '2026-09-14T09:30:12.000Z', principal: { id: 'pri-1', name: 'e2e-user' }, checks: 2,
  outcome: 'allow', first_deny: null, policy_version: 3, ...over,
})
const denied = summary({ request_id: 'req-deny-2', outcome: 'deny', checks: 1, policy_version: null, first_deny: { stage: 'guardrails', reason: 'query_blocked', action: 'kb.read', resource: 'default' } })

const detail = (over: Partial<RequestDetail> = {}): RequestDetail => ({
  request_id: 'req-deny-2', started_at: '2026-09-14T09:30:12.000Z', principal: { id: 'pri-1', name: 'e2e-user' }, tenant: { id: 't', slug: 'e2e' },
  policy_version: 3, outcome: 'deny',
  decisions: [
    decision({ id: 'dec-1', request_id: 'req-deny-2', action: 'kb.read', resource: 'legal', outcome: 'deny', stage: 'policy', reason: 'kb_not_allowed', policy_version: 3 }),
  ],
  ...over,
})

afterEach(() => vi.restoreAllMocks())

describe('RequestsTable', () => {
  it('lists one row per request with outcome, checks, the stage that stopped it and the policy', () => {
    renderWithProviders(<RequestsTable items={[summary(), denied]} isLoading={false} reasons={indexReasons(CATALOGUE)} selectedId="req-deny-2" />)
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveAttribute('data-outcome', 'allow')
    expect(rows[1]).toHaveAttribute('data-outcome', 'deny')
    expect(rows[1]).toHaveAttribute('aria-selected', 'true')
    expect(rows[1]).toHaveTextContent('Input guardrails')
    expect(rows[1]).toHaveTextContent('Input blocked')
    expect(rows[1]).toHaveTextContent('default')
    expect(within(rows[0] as HTMLElement).getByRole('link')).toHaveAttribute('href', '/app/requests/req-allow-1')
  })

  it('keeps the filters in the link that opens a row', () => {
    renderWithProviders(<RequestsTable items={[summary()]} isLoading={false} search="?outcome=deny" />)
    expect(screen.getByRole('link', { name: 'Open request req-allow-1' })).toHaveAttribute('href', '/app/requests/req-allow-1?outcome=deny')
  })

  it('loading shows skeleton rows, empty says how to fill it, error shows the code and retries', async () => {
    const { rerender } = renderWithProviders(<RequestsTable items={undefined} isLoading />)
    expect(screen.getByRole('status', { name: 'Loading' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    rerender(<RequestsTable items={[]} isLoading={false} />)
    expect(screen.getByText('No requests yet.')).toBeInTheDocument()
    rerender(<RequestsTable items={[]} isLoading={false} filtered />)
    expect(screen.getByText('No requests match these filters.')).toBeInTheDocument()
    const onRetry = vi.fn()
    rerender(<RequestsTable items={undefined} isLoading={false} error={new ApiError(500, 'internal_error', 'boom', 'req-1')} onRetry={onRetry} />)
    expect(screen.getByTestId('error-code')).toHaveTextContent('internal_error')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})

describe('RequestDrawer', () => {
  function withCatalogue() {
    const client = testClient()
    client.setQueryData(REASONS_KEY, CATALOGUE)
    return client
  }

  it('opens as a dialog with the verdict, the deny emphasis, the stage trace and a receipt link per decision', async () => {
    vi.spyOn(api, 'requestDetail').mockResolvedValue(detail())
    renderWithProviders(<RequestDrawer requestId="req-deny-2" onClose={() => {}} />, { client: withCatalogue() })
    const dialog = await screen.findByRole('dialog', { name: 'Request' })
    expect(await within(dialog).findByTestId('deny-callout')).toBeInTheDocument()
    expect(within(dialog).getByTestId('deny-sentence')).toHaveTextContent('The policy does not list this knowledge base.')
    expect(within(dialog).getByTestId('deny-policy-field')).toHaveTextContent('allowed_kbs')
    expect(within(dialog).getByTestId('deny-policy-version')).toHaveTextContent('3')
    expect(within(dialog).getByRole('list', { name: 'Request trace' })).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: /Open receipt/ })).toHaveAttribute('href', '/app/decisions/dec-1')
    expect(dialog.querySelector('[data-verdict="deny"]')).toHaveTextContent('Denied')
  })

  it('has no deny callout for an allowed request', async () => {
    vi.spyOn(api, 'requestDetail').mockResolvedValue(detail({ outcome: 'allow', decisions: [decision({ request_id: 'req-deny-2' })] }))
    renderWithProviders(<RequestDrawer requestId="req-deny-2" onClose={() => {}} />, { client: withCatalogue() })
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByRole('list', { name: 'Request trace' })
    expect(within(dialog).queryByTestId('deny-callout')).not.toBeInTheDocument()
    expect(dialog.querySelector('[data-verdict="allow"]')).toHaveTextContent('Allowed')
  })

  it('says so for a request id that is not found, and shows the error code for any other failure', async () => {
    const spy = vi.spyOn(api, 'requestDetail').mockRejectedValue(new ApiError(404, 'request_not_found', 'x', 'r'))
    const { unmount } = renderWithProviders(<RequestDrawer requestId="nope" onClose={() => {}} />, { client: withCatalogue() })
    expect(await screen.findByText('No request with this id was found for your tenant.')).toBeInTheDocument()
    unmount()
    spy.mockRejectedValue(new ApiError(500, 'internal_error', 'boom', 'r-2'))
    renderWithProviders(<RequestDrawer requestId="bad" onClose={() => {}} />, { client: withCatalogue() })
    expect(await screen.findByTestId('error-code')).toHaveTextContent('internal_error')
  })

  it('closes with Escape', async () => {
    vi.spyOn(api, 'requestDetail').mockResolvedValue(detail())
    const onClose = vi.fn()
    renderWithProviders(<RequestDrawer requestId="req-deny-2" onClose={onClose} />, { client: withCatalogue() })
    await screen.findByRole('dialog')
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('is closed when there is no request id', () => {
    renderWithProviders(<RequestDrawer requestId={undefined} onClose={() => {}} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('RequestsPage', () => {
  function Where() { const l = useLocation(); return <p data-testid="where">{l.pathname}{l.search}</p> }
  const page = (route: string) => renderWithProviders(
    <Routes><Route path="/app/requests/:requestId?" element={<><RequestsPage /><Where /></>} /></Routes>,
    { route, client: (() => { const c = testClient(); c.setQueryData(REASONS_KEY, CATALOGUE); return c })() },
  )

  it('asks for console views only when "Include console views" is on', async () => {
    const spy = vi.spyOn(api, 'requests').mockResolvedValue({ items: [summary()], next_cursor: null })
    page('/app/requests')
    await screen.findByRole('table')
    expect(spy.mock.calls.at(-1)?.[0].include_console_reads).toBeUndefined()
    const box = screen.getByLabelText('Include console views')
    expect(box).not.toBeChecked()
    await userEvent.click(box)
    await screen.findByTestId('where')
    expect(screen.getByTestId('where')).toHaveTextContent('console=1')
    await vi.waitFor(() => expect(spy.mock.calls.at(-1)?.[0].include_console_reads).toBe(true))
  })

  it('filters to denied requests from the URL and opens a row in the drawer', async () => {
    const spy = vi.spyOn(api, 'requests').mockResolvedValue({ items: [denied], next_cursor: null })
    vi.spyOn(api, 'requestDetail').mockResolvedValue(detail())
    page('/app/requests?outcome=deny')
    await screen.findByRole('table')
    expect(spy.mock.calls[0]?.[0].outcome).toBe('deny')
    await userEvent.click(screen.getByRole('link', { name: 'Open request req-deny-2' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/app/requests/req-deny-2?outcome=deny')
    expect(await screen.findByRole('dialog', { name: 'Request' })).toBeInTheDocument()
  })
})
