import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { REASONS_KEY } from '@/lib/reasons'
import { CATALOGUE } from '@/test/fixtures'
import { renderWithProviders, testClient } from '@/test/render'
import { DenyCallout, DenyCalloutView } from './deny-callout'

describe('DenyCalloutView (deny emphasis)', () => {
  const props = { reason: 'kb_not_allowed', sentence: 'The policy does not list this knowledge base.', policyField: 'allowed_kbs', stage: 'policy', policyVersion: 3 as number | null, action: 'kb.read', resource: 'legal' }

  it('names the failing stage in red, with an icon and the word Denied', () => {
    const { container } = renderWithProviders(<DenyCalloutView {...props} />)
    const stage = screen.getByTestId('deny-stage')
    expect(stage).toHaveTextContent('Denied at Tenant policy')
    expect(stage.parentElement?.className).toMatch(/text-deny/)
    expect(container.querySelector('svg')).not.toBeNull()
    expect(screen.getByText('policy', { selector: 'code' })).toBeInTheDocument()
  })

  it('says why in a plain sentence', () => {
    renderWithProviders(<DenyCalloutView {...props} />)
    expect(screen.getByTestId('deny-sentence')).toHaveTextContent('The policy does not list this knowledge base.')
  })

  it('shows the policy field and the policy version behind the stop, in mono', () => {
    renderWithProviders(<DenyCalloutView {...props} />)
    expect(within(screen.getByTestId('deny-policy-field')).getByText('allowed_kbs').tagName).toBe('CODE')
    expect(within(screen.getByTestId('deny-policy-version')).getByText('3').tagName).toBe('CODE')
    expect(screen.getByText('reason code', { exact: false })).toBeInTheDocument()
  })

  it('says so when no policy key or no tenant policy is behind the stop', () => {
    renderWithProviders(<DenyCalloutView {...props} policyField={null} policyVersion={null} stage="rate" reason="rate_limit_exceeded" />)
    expect(screen.getByTestId('deny-policy-field')).toHaveTextContent('none')
    expect(screen.getByTestId('deny-policy-version')).toHaveTextContent('platform default')
    expect(screen.getByTestId('deny-stage')).toHaveTextContent('Denied at Rate limit')
  })
})

describe('DenyCallout (reads the catalogue)', () => {
  it('uses the catalogue sentence and field, and the stage from the decision row', () => {
    const client = testClient()
    client.setQueryData(REASONS_KEY, CATALOGUE)
    // The catalogue says policy. The decision row says guardrails. The row wins.
    renderWithProviders(<DenyCallout reason="kb_not_allowed" stage="guardrails" policyVersion={2} />, { client })
    expect(screen.getByTestId('deny-sentence')).toHaveTextContent('The policy does not list this knowledge base.')
    expect(screen.getByTestId('deny-policy-field')).toHaveTextContent('allowed_kbs')
    expect(screen.getByTestId('deny-stage')).toHaveTextContent('Denied at Input guardrails')
  })

  it('does not name blocked_terms for query_blocked when the tenant has none', () => {
    const client = testClient()
    client.setQueryData(REASONS_KEY, CATALOGUE)
    renderWithProviders(<DenyCallout reason="query_blocked" stage="guardrails" policyVersion={null} />, { client })
    expect(screen.getByTestId('deny-policy-field')).toHaveTextContent('none')
  })
})
