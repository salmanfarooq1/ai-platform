import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { indexReasons } from '@/lib/reasons'
import { CATALOGUE, decision, detail } from '@/test/fixtures'
import { renderWithProviders, testClient } from '@/test/render'
import { DecisionDetailView } from '@/features/decisions/decision-panel'
import { REASONS_KEY } from '@/lib/reasons'
import { TraceTimeline } from './trace-timeline'

describe('TraceTimeline deny emphasis', () => {
  it('shows the failing stage in red and the plain sentence on the denied step', () => {
    renderWithProviders(<TraceTimeline steps={detail().trace} reasons={indexReasons(CATALOGUE)} />)
    const sentence = screen.getByTestId('trace-deny-sentence')
    expect(sentence).toHaveTextContent('Tenant policy.')
    expect(sentence).toHaveTextContent('The policy does not list this knowledge base.')
    expect(screen.getByText('stage policy', { selector: 'span' }).className).toMatch(/text-deny/)
  })

  it('shows a plain fallback when the catalogue has not loaded, and no sentence for allowed steps', () => {
    renderWithProviders(<TraceTimeline steps={[decision(), decision({ id: 'd2', outcome: 'deny', stage: 'guardrails', reason: 'query_blocked' })]} />)
    expect(screen.getAllByTestId('trace-deny-sentence')).toHaveLength(1)
    expect(screen.getByTestId('trace-deny-sentence')).toHaveTextContent('Input guardrails.')
  })
})

describe('DecisionDetailView', () => {
  it('adds the deny callout and a link to the whole request for a denied decision', () => {
    const client = testClient()
    client.setQueryData(REASONS_KEY, CATALOGUE)
    const denied = detail({ outcome: 'deny', stage: 'policy', reason: 'kb_not_allowed', request_id: 'req-9' })
    renderWithProviders(<DecisionDetailView decision={denied} />, { client })
    expect(screen.getByTestId('deny-sentence')).toHaveTextContent('The policy does not list this knowledge base.')
    expect(screen.getByRole('link', { name: 'Open the whole request' })).toHaveAttribute('href', '/app/requests/req-9')
  })

  it('has no deny callout for an allowed decision', () => {
    renderWithProviders(<DecisionDetailView decision={detail()} />, { client: (() => { const c = testClient(); c.setQueryData(REASONS_KEY, CATALOGUE); return c })() })
    expect(screen.queryByTestId('deny-callout')).not.toBeInTheDocument()
  })
})
