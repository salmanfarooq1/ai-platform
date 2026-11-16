import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CATALOGUE, detail } from '@/test/fixtures'
import { renderWithProviders, testClient } from '@/test/render'
import { REASONS_KEY } from '@/lib/reasons'
import { DecisionDetailView } from './decision-panel'

function renderDecision(extensions: Record<string, unknown>, record_version = 2) {
  const client = testClient()
  client.setQueryData(REASONS_KEY, CATALOGUE)
  return renderWithProviders(<DecisionDetailView decision={detail({
    action: 'model.invoke', outcome: 'deny', stage: 'policy', reason: 'model_not_allowed',
    record_version, extensions,
  })} />, { client })
}

describe('Decision model evidence', () => {
  it('shows model and stages for a model decision', () => {
    renderDecision({
      model: { name: 'local/chat', provider: 'ollama', source: 'local', digest: `sha256:${'a'.repeat(64)}`, processing_scope: 'local', region: 'eu', route: `sha256:${'b'.repeat(64)}`, phase: 'attempt' },
      stages: [
        { stage: 'principal', status: 'passed', reason: null, duration_us: 8 },
        { stage: 'policy', status: 'denied', reason: 'model_not_allowed', duration_us: 3 },
        { stage: 'model', status: 'not_reached', reason: null, duration_us: 0 },
      ],
    })
    const evidence = screen.getByRole('region', { name: 'Model evidence' })
    const model = within(evidence).getByRole('heading', { name: 'Model' }).parentElement as HTMLElement
    expect(within(model).getByText('Alias').parentElement).toHaveTextContent('local/chat')
    expect(within(model).getByText('Source').parentElement).toHaveTextContent('local')
    expect(within(model).getByText('Digest').parentElement).toHaveTextContent(`sha256:${'a'.repeat(64)}`)
    expect(within(model).getByText('Region').parentElement).toHaveTextContent('eu')
    expect(within(model).getByText('Phase').parentElement).toHaveTextContent('attempt')
    const stages = within(evidence).getByRole('list', { name: 'Stages' })
    expect(within(stages).getAllByRole('listitem')).toHaveLength(3)
    expect(within(stages).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'principal · passed', 'policy · denied · model_not_allowed', 'model · not_reached',
    ])
  })

  it('old decisions show no model or stages', () => {
    renderDecision({}, 1)
    expect(screen.queryByRole('region', { name: 'Model evidence' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Model' })).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Stages' })).not.toBeInTheDocument()
  })
})
