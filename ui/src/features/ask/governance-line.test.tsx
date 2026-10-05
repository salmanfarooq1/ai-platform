import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { api } from '@/api/endpoints'
import { decision } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { GovernanceLine } from './governance-line'
import { governanceLineText } from './governance-text'

const request = (over = {}) => ({
  request_id: 'req-9', started_at: '2026-09-14T09:30:12.000Z', principal: { id: 'p', name: 'e2e-user' }, tenant: { id: 't', slug: 'e2e' },
  policy_version: 3, outcome: 'allow' as const, decisions: [decision(), decision({ id: 'dec-2' })], ...over,
})

afterEach(() => vi.restoreAllMocks())

describe('governanceLineText', () => {
  it('reads "Checked by policy v3 · 2 checks · allowed"', () => {
    expect(governanceLineText(request())).toBe('Checked by policy v3 · 2 checks · allowed')
  })
  it('says check for one, denied for a deny, and the platform default with no tenant policy', () => {
    expect(governanceLineText(request({ decisions: [decision()], outcome: 'deny', policy_version: null }))).toBe('Checked by the platform default policy · 1 check · denied')
  })
})

describe('GovernanceLine', () => {
  it('links the line to the request drawer', async () => {
    vi.spyOn(api, 'requestDetail').mockResolvedValue(request())
    renderWithProviders(<GovernanceLine requestId="req-9" />)
    const link = await screen.findByRole('link', { name: /Checked by policy v3/ })
    expect(link).toHaveAttribute('href', '/app/requests/req-9')
    expect(link).toHaveTextContent('2 checks')
  })

  it('shows nothing without a request id', () => {
    const { container } = renderWithProviders(<GovernanceLine requestId={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a skeleton while loading', () => {
    vi.spyOn(api, 'requestDetail').mockReturnValue(new Promise(() => {}))
    const { container } = renderWithProviders(<GovernanceLine requestId="req-9" />)
    expect(container.querySelector('.skeleton')).not.toBeNull()
  })

  it('says the record is not available, with the error code, when the lookup fails', async () => {
    vi.spyOn(api, 'requestDetail').mockRejectedValue(new ApiError(404, 'request_not_found', 'No such request', 'r-1'))
    renderWithProviders(<GovernanceLine requestId="req-9" />)
    expect(await screen.findByTestId('governance-line-error')).toHaveTextContent('request_not_found')
  })
})
