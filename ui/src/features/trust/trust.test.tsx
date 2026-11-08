import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import type { Receipt, TrustSummary, VerifyResult } from '@/api/types'
import { renderWithProviders } from '@/test/render'
import { detail } from '@/test/fixtures'
import TrustPage from './trust-page'

const receipt: Receipt = {
  decision: detail({ record_version: 1 }), chain: { prev_hash: 'b'.repeat(64), row_hash: 'c'.repeat(64), position: 12 },
  signature: 'sig', key_id: 'k'.repeat(16), alg: 'Ed25519',
  canonical: JSON.stringify({ chain: { position: 12, prev_hash: 'b'.repeat(64), row_hash: 'c'.repeat(64) }, decision: { id: 'dec-1', action: 'kb.read', outcome: 'allow', reason: 'allowed' } }),
}
const good: VerifyResult = { valid: true, checks: [
  { name: 'alg', ok: true, detail: 'algorithm Ed25519' }, { name: 'signature', ok: true, detail: 'the signature is valid' },
] }
const bad: VerifyResult = { valid: false, checks: [
  { name: 'alg', ok: true, detail: 'algorithm Ed25519' }, { name: 'signature', ok: false, detail: 'the signature does not match the signed text' },
] }
const summary = (over: Partial<TrustSummary> = {}): TrustSummary => ({
  retention_days: 90, retention_is_default: true, oldest_decision_at: '2026-09-01T10:00:00Z', last_purge_at: null,
  eval_gate: null, eval_history: [], metrics_public: true, grafana_url: null, ...over,
})
const run = (status: 'passed' | 'failed', latest = 0.83) => ({
  status, run_at: '2026-10-01T10:00:00Z', baseline: { answer_fact: 0.83 }, latest: { answer_fact: latest },
})

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'trustSummary').mockResolvedValue(summary())
})

describe('Trust page', () => {
  it('verifies a decision id: fetches the receipt, checks it, shows valid, each check and the chain position', async () => {
    const fetchReceipt = vi.spyOn(api, 'receipt').mockResolvedValue(receipt)
    const verify = vi.spyOn(api, 'verifyReceipt').mockResolvedValue(good)
    renderWithProviders(<TrustPage />, { route: '/app/trust' })
    await userEvent.type(screen.getByLabelText('Decision id'), ' dec-1 ')
    await userEvent.click(screen.getByRole('button', { name: 'Verify receipt' }))
    const result = await screen.findByTestId('receipt-result')
    expect(fetchReceipt).toHaveBeenCalledWith('dec-1')
    expect(verify).toHaveBeenCalledWith(receipt)
    expect(result).toHaveAttribute('data-valid', 'true')
    expect(within(result).getByRole('heading', { name: 'Valid' })).toBeInTheDocument()
    expect(within(result).getByTestId('chain-position')).toHaveTextContent('12')
    expect(within(result).getAllByText('Passed')).toHaveLength(2)
    expect(within(result).getByText('k'.repeat(16))).toBeInTheDocument()
  })

  it('shows invalid with the failing check, as a word and an icon, for a tampered pasted receipt', async () => {
    vi.spyOn(api, 'verifyReceipt').mockResolvedValue(bad)
    renderWithProviders(<TrustPage />, { route: '/app/trust' })
    await userEvent.click(screen.getByText('Check a receipt you already hold'))
    const box = screen.getByLabelText('Receipt (JSON)')
    await userEvent.click(box)
    await userEvent.paste(JSON.stringify(receipt))
    await userEvent.click(screen.getByRole('button', { name: 'Verify pasted receipt' }))
    const result = await screen.findByTestId('receipt-result')
    expect(result).toHaveAttribute('data-valid', 'false')
    expect(within(result).getByRole('heading', { name: 'Invalid' })).toBeInTheDocument()
    expect(within(result).getByText('Failed')).toBeInTheDocument()
    expect(within(result).getByText('the signature does not match the signed text')).toBeInTheDocument()
  })

  it('refuses text that is not JSON without calling the API', async () => {
    const verify = vi.spyOn(api, 'verifyReceipt')
    renderWithProviders(<TrustPage />, { route: '/app/trust' })
    await userEvent.click(screen.getByText('Check a receipt you already hold'))
    await userEvent.type(screen.getByLabelText('Receipt (JSON)'), 'not json')
    await userEvent.click(screen.getByRole('button', { name: 'Verify pasted receipt' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That is not a receipt')
    expect(verify).not.toHaveBeenCalled()
  })

  it('opens from a decision link and runs the check once', async () => {
    const fetchReceipt = vi.spyOn(api, 'receipt').mockResolvedValue(receipt)
    vi.spyOn(api, 'verifyReceipt').mockResolvedValue(good)
    renderWithProviders(<TrustPage />, { route: '/app/trust?decision=dec-9' })
    await screen.findByTestId('receipt-result')
    expect(screen.getByLabelText('Decision id')).toHaveValue('dec-9')
    expect(fetchReceipt).toHaveBeenCalledTimes(1)
  })

  it('verifies a v2 receipt', async () => {
    const v2Receipt: Receipt = { ...receipt, decision: detail({ record_version: 2 }) }
    const fetchReceipt = vi.spyOn(api, 'receipt').mockResolvedValue(v2Receipt)
    const verify = vi.spyOn(api, 'verifyReceipt').mockResolvedValue(good)
    renderWithProviders(<TrustPage />, { route: '/app/trust?decision=dec-v2' })
    expect(await screen.findByTestId('receipt-result')).toHaveAttribute('data-valid', 'true')
    expect(fetchReceipt).toHaveBeenCalledWith('dec-v2')
    expect(verify).toHaveBeenCalledWith(v2Receipt)
  })

  it('shows the API error code for an unknown decision', async () => {
    const { ApiError } = await import('@/api/client')
    vi.spyOn(api, 'receipt').mockRejectedValue(new ApiError(404, 'not_found', 'Receipt not found', 'req-7'))
    renderWithProviders(<TrustPage />, { route: '/app/trust' })
    await userEvent.type(screen.getByLabelText('Decision id'), 'nope')
    await userEvent.click(screen.getByRole('button', { name: 'Verify receipt' }))
    expect(await screen.findByTestId('error-code')).toHaveTextContent('not_found')
    expect(screen.getByTestId('error-request-id')).toHaveTextContent('req-7')
  })

  it('shows retention read only, the empty eval state and the Grafana hint', async () => {
    renderWithProviders(<TrustPage />, { route: '/app/trust' })
    expect(await screen.findByTestId('retention-days')).toHaveTextContent('90 days (platform default)')
    expect(screen.getByTestId('last-purge')).toHaveTextContent('never')
    expect(screen.getByText('No eval gate run has been recorded yet.')).toBeInTheDocument()
    expect(screen.getByText(/Grafana is not linked/)).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /retention/i })).toBeNull()
  })

  it('shows a tenant override, the eval history with pass and fail words, and the Grafana link', async () => {
    vi.spyOn(api, 'trustSummary').mockResolvedValue(summary({
      retention_days: 30, retention_is_default: false, last_purge_at: '2026-10-02T03:00:00Z',
      eval_gate: run('failed', 0.5), eval_history: [run('failed', 0.5), run('passed')], grafana_url: 'http://localhost:3000',
    }))
    renderWithProviders(<TrustPage />, { route: '/app/trust' })
    expect(await screen.findByTestId('retention-days')).toHaveTextContent('30 days (set for this tenant)')
    await waitFor(() => expect(screen.getByTestId('eval-latest')).toHaveTextContent('Failed'))
    const history = screen.getByRole('table', { name: 'Eval gate history' })
    expect(within(history).getByText('Failed')).toBeInTheDocument()
    expect(within(history).getByText('Passed')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Grafana/ })).toHaveAttribute('href', 'http://localhost:3000')
  })

  it('shows an error with a retry when the summary cannot load', async () => {
    vi.spyOn(api, 'trustSummary').mockRejectedValue(new Error('down'))
    renderWithProviders(<TrustPage />, { route: '/app/trust' })
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the trust summary.')
  })

  it('L5: only the signed text is shown under Verified; names and labels are context, and nothing is Verified when invalid', async () => {
    const tampered: Receipt = { ...receipt, decision: { ...receipt.decision, outcome: 'deny', principal: { id: 'p', name: 'Somebody Else' }, tenant: { id: 't', slug: 'forged-label' } } }
    vi.spyOn(api, 'receipt').mockResolvedValue(tampered)
    vi.spyOn(api, 'verifyReceipt').mockResolvedValue(good)
    renderWithProviders(<TrustPage />, { route: '/app/trust?decision=dec-1' })
    const verified = await screen.findByTestId('verified-fields')
    expect(within(verified).getByText('allow')).toBeInTheDocument() // the signed text says allow, the loose field says deny
    expect(within(verified).queryByText('deny')).toBeNull()
    expect(within(verified).queryByText(/Somebody Else|forged-label/)).toBeNull()
    const context = screen.getByTestId('context-fields')
    expect(within(context).getByText('Somebody Else')).toBeInTheDocument()
    expect(within(context).getByText('forged-label')).toBeInTheDocument()
    expect(screen.getByText('Context, not signed')).toBeInTheDocument()
  })

  it('L5: an invalid receipt has no Verified list', async () => {
    vi.spyOn(api, 'receipt').mockResolvedValue(receipt)
    vi.spyOn(api, 'verifyReceipt').mockResolvedValue(bad)
    renderWithProviders(<TrustPage />, { route: '/app/trust?decision=dec-1' })
    await screen.findByTestId('receipt-result')
    expect(screen.queryByTestId('verified-fields')).toBeNull()
  })
})
