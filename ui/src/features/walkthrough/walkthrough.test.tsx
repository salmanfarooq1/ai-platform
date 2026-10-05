import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { api } from '@/api/endpoints'
import type { RequestDetail } from '@/api/types'
import { REASONS_KEY } from '@/lib/reasons'
import { CATALOGUE, decision } from '@/test/fixtures'
import { renderWithProviders, testClient } from '@/test/render'
import { firstRunPath, walkthroughSeen } from './walkthrough-store'
import WalkthroughPage, { ALLOWED_QUESTION, BLOCKED_QUESTION } from './walkthrough-page'

const config = (namespaces: Record<string, string>) => ({
  namespaces, confidence_floor: 0.5, max_query_length: 1000, daily_token_budget: 1, rate_limit_rpm: 1, rate_limit_window_seconds: 60, reranker_enabled: false,
  agent_defaults: { max_iterations: 1, enable_verifier: false, max_verify_retries: 0 },
})

const allowedDetail: RequestDetail = {
  request_id: 'req-a', started_at: '2026-09-14T09:30:12.000Z', principal: { id: 'p', name: 'e2e-user' }, tenant: { id: 't', slug: 'e2e' }, policy_version: 1, outcome: 'allow',
  decisions: [decision({ id: 'a1', request_id: 'req-a' }), decision({ id: 'a2', request_id: 'req-a', action: 'model.invoke', resource: null })],
}
const blockedDetail: RequestDetail = {
  request_id: 'req-b', started_at: '2026-09-14T09:30:13.000Z', principal: { id: 'p', name: 'e2e-user' }, tenant: { id: 't', slug: 'e2e' }, policy_version: 1, outcome: 'deny',
  decisions: [decision({ id: 'b1', request_id: 'req-b', outcome: 'deny', stage: 'guardrails', reason: 'query_blocked', resource: 'default', policy_version: 1 })],
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

function page() {
  const client = testClient()
  client.setQueryData(REASONS_KEY, CATALOGUE)
  return renderWithProviders(<WalkthroughPage />, { client })
}

describe('WalkthroughPage', () => {
  it('runs one allowed and one blocked request and shows both side by side, the blocked one at the guardrails stage', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ default: 'General' }))
    const search = vi.spyOn(api, 'search').mockImplementation(async ({ query }) => {
      if (query === BLOCKED_QUESTION) throw new ApiError(400, 'query_blocked', 'Query matches a known prompt injection pattern', 'req-b')
      return { data: { answer: 'The documents cover retention.' } as never, requestId: 'req-a', headers: new Headers(), status: 200 }
    })
    vi.spyOn(api, 'requestDetail').mockImplementation(async (id) => (id === 'req-b' ? blockedDetail : allowedDetail))
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Run both' }))

    const allowed = await screen.findByTestId('walkthrough-allowed')
    const blocked = await screen.findByTestId('walkthrough-blocked')
    expect(search).toHaveBeenCalledTimes(2)
    expect(search.mock.calls.map((c) => c[0].query).sort()).toEqual([ALLOWED_QUESTION, BLOCKED_QUESTION].sort())
    expect(search.mock.calls.every((c) => c[0].namespace === 'default')).toBe(true)

    expect(allowed).toHaveAttribute('data-verdict', 'allow')
    expect(allowed.querySelector('[data-verdict="allow"]')).toHaveTextContent('Allowed')
    expect(within(allowed).getByTestId('walkthrough-answer')).toHaveTextContent('retention')
    expect(blocked).toHaveAttribute('data-verdict', 'deny')
    expect(within(blocked).getByTestId('deny-stage')).toHaveTextContent('Denied at Input guardrails')
    expect(within(blocked).getByText('guardrails', { selector: 'code' })).toBeInTheDocument()
    expect(within(blocked).getByTestId('deny-sentence')).toHaveTextContent('The input matched a guardrail.')
    expect(within(blocked).getByRole('link', { name: /Open the request/ })).toHaveAttribute('href', '/app/requests/req-b')
    // Both are in one two-column grid.
    expect(allowed.parentElement).toBe(blocked.parentElement)
    expect(allowed.parentElement?.className).toMatch(/md:grid-cols-2/)
  })

  it('treats "no passage matched" as allowed by the gateway, and still shows the trace', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ default: '' }))
    vi.spyOn(api, 'search').mockImplementation(async ({ query }) => {
      if (query === BLOCKED_QUESTION) throw new ApiError(400, 'query_blocked', 'blocked', 'req-b')
      throw new ApiError(404, 'not_found', "No documents found in namespace 'default'.", 'req-a')
    })
    vi.spyOn(api, 'requestDetail').mockImplementation(async (id) => (id === 'req-b' ? blockedDetail : allowedDetail))
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Run both' }))
    const allowed = await screen.findByTestId('walkthrough-allowed')
    expect(allowed).toHaveAttribute('data-verdict', 'allow')
    expect(within(allowed).getByTestId('walkthrough-no-passages')).toBeInTheDocument()
    expect(within(allowed).getByRole('list', { name: 'Request trace' })).toBeInTheDocument()
    expect(await screen.findByTestId('walkthrough-blocked')).toHaveAttribute('data-verdict', 'deny')
  })

  it.each([
    ['the request detail cannot be loaded', () => Promise.reject(new ApiError(404, 'not_found', 'Request not found', 'req-a'))],
    ['the request detail holds no allow decision', async () => ({ ...allowedDetail, outcome: 'deny' as const, decisions: [blockedDetail.decisions[0]!] })],
    ['the request detail holds no decisions', async () => ({ ...allowedDetail, decisions: [] })],
  ])('shows the error state for a 404 not_found when %s', async (_name, detail) => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ default: '' }))
    vi.spyOn(api, 'search').mockImplementation(async ({ query }) => {
      if (query === BLOCKED_QUESTION) throw new ApiError(400, 'query_blocked', 'blocked', 'req-b')
      throw new ApiError(404, 'not_found', 'Not found.', 'req-a')
    })
    vi.spyOn(api, 'requestDetail').mockImplementation(async (id) => (id === 'req-b' ? blockedDetail : detail()))
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Run both' }))
    expect(await screen.findByText('The walkthrough could not run.')).toBeInTheDocument()
    expect(screen.queryByTestId('walkthrough-no-passages')).not.toBeInTheDocument()
    expect(screen.queryByTestId('walkthrough-allowed')).not.toBeInTheDocument()
  })

  it('explains itself and links to the Library when the session has no knowledge base', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({}))
    page()
    expect(await screen.findByText('This session cannot read a knowledge base.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the Library' })).toHaveAttribute('href', '/app/library')
    expect(screen.queryByRole('button', { name: 'Run both' })).not.toBeInTheDocument()
  })

  it('shows the error code when a call fails for another reason', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ default: '' }))
    vi.spyOn(api, 'search').mockRejectedValue(new ApiError(500, 'internal_error', 'boom', 'r-1'))
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Run both' }))
    expect(await screen.findByTestId('error-code')).toHaveTextContent('internal_error')
  })

  it('remembers that it was seen, so sign-in opens the Overview next time', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ default: '' }))
    expect(walkthroughSeen()).toBe(false)
    expect(firstRunPath()).toBe('/app/walkthrough')
    page()
    await screen.findByRole('button', { name: 'Run both' })
    expect(walkthroughSeen()).toBe(true)
    expect(firstRunPath()).toBe('/app')
  })
})
