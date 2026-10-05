import type { DecisionDetail, DecisionSummary } from '@/api/types'

// Example data for the landing page and How it works. It is shown next to the label "Example", never as real data.
const T0 = Date.UTC(2026, 8, 14, 9, 30, 12)
const base = { request_id: 'req_example', principal: { id: 'p1', name: 'contracts-agent' }, policy_version: 3 }

export const EXAMPLE_SHA = '725918da651359d33209d0642f3b31a83cbf4fbc7e0d25040e56c279b0d0cdf2'

export const askDecision: DecisionSummary = { ...base, id: 'd1', created_at: new Date(T0).toISOString(), action: 'agent.run', resource: null, outcome: 'allow', stage: 'policy', reason: 'allowed' }
export const kbAllow: DecisionSummary = { ...base, id: 'd2', created_at: new Date(T0 + 140).toISOString(), action: 'kb.read', resource: 'contracts', outcome: 'allow', stage: 'policy', reason: 'allowed' }
export const kbDeny: DecisionSummary = { ...base, id: 'd3', created_at: new Date(T0 + 310).toISOString(), action: 'kb.read', resource: 'payroll', outcome: 'deny', stage: 'policy', reason: 'kb_not_allowed' }

export const exampleTrace: DecisionSummary[] = [askDecision, kbAllow, kbDeny]

export const exampleReceipt: DecisionDetail = {
  ...kbAllow,
  tenant: { id: 't1', slug: 'northwind' },
  input_sha256: EXAMPLE_SHA,
  trace: exampleTrace,
}

/** The catalogue sentence for kb_not_allowed, written out so the public page needs no API call. */
export const EXAMPLE_DENY_SENTENCE = 'The policy does not list this knowledge base.'

export const EXAMPLE_POLICY = { allowed_kbs: ['contracts', 'handbook'], allowed_tools: '*', allowed_models: '*', max_tool_calls: 8, max_tokens_per_request: 4000 }

export const EXAMPLE_STAGES = [
  { name: 'Identity check', code: 'principal', text: 'Who is calling, and which tenant they belong to.' },
  { name: 'Scope check', code: 'boundary', text: 'Whether the key holds the scope this kind of call needs.' },
  { name: 'Tenant policy', code: 'policy', text: 'Whether the policy lists the knowledge base, tool or model.' },
  { name: 'Input guardrails', code: 'guardrails', text: 'Whether the input is too long, holds a blocked term, or looks like an injection attempt.' },
  { name: 'Rate limit', code: 'rate', text: 'Whether this identity sent too many requests in the current window.' },
  { name: 'Token budget', code: 'budget', text: 'Whether the tenant still has tokens left for today.' },
] as const
