import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import { api } from '@/api/endpoints'
import type { Overview } from '@/api/types'
import { indexReasons } from '@/lib/reasons'
import { CATALOGUE } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { formatPercent, requestsHref } from './overview-format'
import OverviewPage from './overview-page'
import { OverviewTiles, TopDenyReasons } from './overview-tiles'

const overview = (over: Partial<Overview> = {}): Overview => ({
  days: 7, checked: 40, blocked: 6, deny_rate: 0.15,
  budget: { used_tokens: 2500, limit_tokens: 10000, period: 'day' },
  top_deny_reasons: [{ reason: 'kb_not_allowed', count: 4 }, { reason: 'query_blocked', count: 2 }],
  by_day: [{ date: '2026-09-13', checked: 10, blocked: 1 }, { date: '2026-09-14', checked: 30, blocked: 5 }],
  ...over,
})

afterEach(() => vi.restoreAllMocks())

describe('formatting and links', () => {
  it('formats a rate as a percent', () => {
    expect(formatPercent(0)).toBe('0%')
    expect(formatPercent(0.15)).toBe('15%')
    expect(formatPercent(0.034)).toBe('3.4%')
  })
  it('builds the requests link with the period and the filter', () => {
    expect(requestsHref(7, { outcome: 'deny' })).toBe('/app/requests?outcome=deny&since=7d')
    expect(requestsHref(1)).toBe('/app/requests?since=24h')
    expect(requestsHref(90)).toBe('/app/requests')
  })
})

describe('OverviewTiles', () => {
  it('shows checked, blocked, deny rate and budget used, and each links to its filtered records', () => {
    renderWithProviders(<OverviewTiles overview={overview()} />)
    expect(within(screen.getByTestId('tile-checked')).getByText('40')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-blocked')).getByText('6')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-deny-rate')).getByText('15%')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-budget')).getByText('25%')).toBeInTheDocument()
    expect(screen.getByTestId('tile-budget')).toHaveTextContent('2,500 of 10,000 tokens')
    expect(screen.getByTestId('tile-checked')).toHaveAttribute('href', '/app/requests?since=7d')
    expect(screen.getByTestId('tile-blocked')).toHaveAttribute('href', '/app/requests?outcome=deny&since=7d')
    expect(screen.getByTestId('tile-deny-rate')).toHaveAttribute('href', '/app/requests?outcome=deny&since=7d')
    expect(screen.getByTestId('tile-budget')).toHaveAttribute('href', '/app/usage')
  })

  it('does not divide by a zero budget limit', () => {
    renderWithProviders(<OverviewTiles overview={overview({ budget: { used_tokens: 0, limit_tokens: 0, period: 'day' } })} />)
    expect(within(screen.getByTestId('tile-budget')).getByText('0%')).toBeInTheDocument()
  })
})

describe('TopDenyReasons', () => {
  it('lists the reasons with the catalogue title, sentence and count', () => {
    renderWithProviders(<TopDenyReasons overview={overview()} reasons={indexReasons(CATALOGUE)} />)
    const list = screen.getByRole('list', { name: 'Top deny reasons' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Knowledge base not allowed')
    expect(items[0]).toHaveTextContent('The policy does not list this knowledge base.')
    expect(items[0]).toHaveTextContent('kb_not_allowed')
    expect(items[0]).toHaveTextContent('4')
  })
  it('says so when nothing was blocked', () => {
    renderWithProviders(<TopDenyReasons overview={overview({ top_deny_reasons: [], blocked: 0 })} />)
    expect(screen.getByText('No request was blocked in this period.')).toBeInTheDocument()
  })
})

describe('OverviewPage', () => {
  function Where() { const l = useLocation(); return <p data-testid="where">{l.pathname}{l.search}</p> }

  it('loads the overview and sends the blocked number to the deny-filtered list', async () => {
    vi.spyOn(api, 'overview').mockResolvedValue(overview())
    vi.spyOn(api, 'reasonCodes').mockResolvedValue(CATALOGUE)
    renderWithProviders(<Routes><Route path="/app" element={<OverviewPage />} /><Route path="/app/requests" element={<Where />} /></Routes>, { route: '/app' })
    const blocked = await screen.findByTestId('tile-blocked')
    await userEvent.click(blocked)
    expect(screen.getByTestId('where')).toHaveTextContent('/app/requests?outcome=deny&since=7d')
  })

  it('has an empty state that says how to fill it', async () => {
    vi.spyOn(api, 'overview').mockResolvedValue(overview({ checked: 0, blocked: 0, deny_rate: 0, top_deny_reasons: [] }))
    vi.spyOn(api, 'reasonCodes').mockResolvedValue(CATALOGUE)
    renderWithProviders(<OverviewPage />)
    expect(await screen.findByText('Nothing has been checked in this period.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the walkthrough' })).toHaveAttribute('href', '/app/walkthrough')
  })

  it('shows the error code and a retry when the overview fails', async () => {
    const { ApiError } = await import('@/api/client')
    vi.spyOn(api, 'overview').mockRejectedValue(new ApiError(403, 'forbidden', 'Missing scope audit:read', 'req-5'))
    vi.spyOn(api, 'reasonCodes').mockResolvedValue(CATALOGUE)
    renderWithProviders(<OverviewPage />)
    expect(await screen.findByTestId('error-code')).toHaveTextContent('forbidden')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
