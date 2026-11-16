import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import type { Receipt, VerifyResult } from '@/api/types'
import { detail } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import TrustPage from './trust-page'

const good: VerifyResult = { valid: true, checks: [{ name: 'signature', ok: true, detail: 'the signature is valid' }] }

function receipt(record_version: number, extensions?: Record<string, unknown>): Receipt {
  const model = { name: 'local/chat', provider: 'ollama', source: 'local', digest: `sha256:${'a'.repeat(64)}`, processing_scope: 'local', region: 'eu', route: `sha256:${'b'.repeat(64)}`, phase: 'attempt' }
  const stages = [{ stage: 'principal', status: 'passed', reason: null, duration_us: 8 }, { stage: 'policy', status: 'denied', reason: 'model_not_allowed', duration_us: 3 }]
  const signedExtensions = extensions ?? (record_version === 2 ? { model, stages } : undefined)
  const signedDecision: Record<string, unknown> = { id: `dec-v${record_version}`, request_id: 'req-1', action: 'model.invoke', outcome: 'deny', reason: 'model_not_allowed' }
  if (signedExtensions) signedDecision.extensions = signedExtensions
  return {
    decision: detail({ id: `dec-v${record_version}`, record_version, action: 'model.invoke', outcome: 'deny', reason: 'model_not_allowed', extensions: signedExtensions ?? {} }),
    chain: { prev_hash: 'b'.repeat(64), row_hash: 'c'.repeat(64), position: 12 },
    signature: 'sig', key_id: 'k'.repeat(16), alg: 'Ed25519',
    canonical: JSON.stringify({ chain: { position: 12, prev_hash: 'b'.repeat(64), row_hash: 'c'.repeat(64) }, decision: signedDecision }),
  }
}

describe('receipt verifier signed model fields', () => {
  it('lists the signed model and stages fields and verifies a v2 receipt', async () => {
    const v2 = receipt(2)
    vi.spyOn(api, 'trustSummary').mockResolvedValue({ retention_days: 90, retention_is_default: true, oldest_decision_at: null, last_purge_at: null, eval_gate: null, eval_history: [], metrics_public: true, grafana_url: null })
    vi.spyOn(api, 'receipt').mockResolvedValue(v2)
    const verify = vi.spyOn(api, 'verifyReceipt').mockResolvedValue(good)
    renderWithProviders(<TrustPage />, { route: '/app/trust?decision=dec-v2' })
    const result = await screen.findByTestId('receipt-result')
    expect(result).toHaveAttribute('data-valid', 'true')
    const verified = within(result).getByTestId('verified-fields')
    expect(within(verified).getByText('Model', { exact: true }).parentElement).toHaveTextContent('"name":"local/chat"')
    expect(within(verified).getByText('Stages', { exact: true }).parentElement).toHaveTextContent('"stage":"principal"')
    expect(verify).toHaveBeenCalledWith(v2)
  })

  it('verifies a v1 receipt with its original signed fields', async () => {
    const v1 = receipt(1)
    vi.spyOn(api, 'trustSummary').mockResolvedValue({ retention_days: 90, retention_is_default: true, oldest_decision_at: null, last_purge_at: null, eval_gate: null, eval_history: [], metrics_public: true, grafana_url: null })
    vi.spyOn(api, 'receipt').mockResolvedValue(v1)
    vi.spyOn(api, 'verifyReceipt').mockResolvedValue(good)
    renderWithProviders(<TrustPage />, { route: '/app/trust?decision=dec-v1' })
    const result = await screen.findByTestId('receipt-result')
    expect(result).toHaveAttribute('data-valid', 'true')
    const verified = within(result).getByTestId('verified-fields')
    expect(within(verified).getByText('Decision id').parentElement).toHaveTextContent('dec-v1')
    expect(within(verified).queryByText('Model', { exact: true })).not.toBeInTheDocument()
    expect(within(verified).queryByText('Stages', { exact: true })).not.toBeInTheDocument()
  })
})
