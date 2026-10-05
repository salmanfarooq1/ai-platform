import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { describe, expect, it } from 'vitest'
import type { SearchResponse } from '@/api/types'
import { AnswerView } from './answer-view'
import { confidenceLevel } from './confidence'
import { denyReason } from './deny'

describe('denyReason', () => {
  it('reads the reason code from the gateway message', () => {
    expect(denyReason('Denied by policy (reason: kb_not_allowed)')).toBe('kb_not_allowed')
    expect(denyReason('something else')).toBe('policy_denied')
  })
})

describe('confidenceLevel', () => {
  it('maps the confidence scale', () => {
    expect(confidenceLevel(0.9)).toBe('high')
    expect(confidenceLevel(0.6)).toBe('medium')
    expect(confidenceLevel(0.2)).toBe('low')
    expect(confidenceLevel(0.5, 0.6)).toBe('low')
  })
})

describe('AnswerView', () => {
  const data: SearchResponse = {
    query: 'q', answer: 'Records are kept for **seven years**.', confidence: 0.9, needs_clarification: false, flagged: false, flag_reason: null,
    rerank_applied: false, total_results: 1,
    results: [{ document_id: 'retention.md', namespace: 'default', content: 'Customer records must be kept for seven years.', score: 0.03, metadata: { chunk_index: 0 } }],
  }

  it('shows the verdict, confidence, evidence and the receipt link', () => {
    renderWithProviders(<AnswerView kind="search" data={data} requestId="req-1" />)
    expect(screen.getByText('Allowed')).toBeInTheDocument()
    expect(screen.getByTestId('confidence')).toHaveTextContent('HIGH 90%')
    expect(screen.getByText('seven years', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Evidence' })).toHaveTextContent('retention.md')
    expect(screen.getByRole('link', { name: /Open receipt in Decisions/ })).toHaveAttribute('href', '/app/decisions?request_id=req-1')
  })

  it('has no receipt link without a request id, and says when there is no evidence', () => {
    renderWithProviders(<AnswerView kind="search" data={{ ...data, results: [], total_results: 0 }} requestId={null} />)
    expect(screen.queryByRole('link', { name: /Open receipt/ })).not.toBeInTheDocument()
    expect(screen.getByText('No sources were returned for this answer.')).toBeInTheDocument()
  })

  it('shows the flag reason when the answer is flagged', () => {
    renderWithProviders(<AnswerView kind="search" data={{ ...data, flagged: true, flag_reason: 'low confidence' }} requestId="r" />)
    expect(screen.getByRole('note')).toHaveTextContent('low confidence')
  })
})
