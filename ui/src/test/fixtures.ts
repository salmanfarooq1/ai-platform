import type { DecisionDetail, DecisionSummary, ReasonCode } from '@/api/types'

export function decision(over: Partial<DecisionSummary> = {}): DecisionSummary {
  return {
    id: 'dec-1',
    created_at: '2026-09-14T09:30:12.000Z',
    request_id: 'req-1',
    principal: { id: 'pri-1', name: 'e2e-user' },
    action: 'kb.read',
    resource: 'default',
    outcome: 'allow',
    stage: 'allow',
    reason: 'allowed',
    policy_version: 3,
    ...over,
  }
}

export function detail(over: Partial<DecisionDetail> = {}): DecisionDetail {
  const base = decision()
  return {
    ...base,
    tenant: { id: 'ten-1', slug: 'northwind' },
    input_sha256: 'a'.repeat(64),
    trace: [
      decision({ id: 'dec-0', action: 'agent.run', resource: null, created_at: '2026-09-14T09:30:11.900Z' }),
      base,
      decision({ id: 'dec-2', outcome: 'deny', stage: 'policy', reason: 'kb_not_allowed', resource: 'legal', created_at: '2026-09-14T09:30:12.400Z' }),
    ],
    ...over,
  }
}

/** A short reason catalogue, like GET /v1/reason-codes. */
export const CATALOGUE: ReasonCode[] = [
  { code: 'allowed', title: 'Allowed', sentence: 'The call passed every check.', policy_field: null, stage: 'allow' },
  { code: 'kb_not_allowed', title: 'Knowledge base not allowed', sentence: 'The policy does not list this knowledge base.', policy_field: 'allowed_kbs', stage: 'policy' },
  { code: 'token_limit', title: 'Token limit exceeded', sentence: 'The call would use more tokens than the policy allows for one request.', policy_field: 'max_tokens_per_request', stage: 'policy' },
  { code: 'query_blocked', title: 'Input blocked', sentence: 'The input matched a guardrail.', policy_field: 'blocked_terms', stage: 'guardrails' },
]
