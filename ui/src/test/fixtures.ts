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

import type { AgentRunDetail, RunTimelineItem, SandboxEvent } from '@/api/types'

/** One sandbox event, as the runs API returns it. */
export function sandboxEvent(over: Partial<SandboxEvent> = {}): SandboxEvent {
  return { id: 'ev-1', kind: 'log', at: '2026-09-14T09:30:12.500Z', detail: {}, ...over }
}

/** A step of a sandboxed run: a decision or a sandbox event. */
export function decisionStep(over: Partial<DecisionSummary> = {}): RunTimelineItem {
  const d = decision(over)
  return {
    source: 'decision', at: d.created_at,
    decision: { id: d.id, at: d.created_at, action: d.action, resource: d.resource ?? null, outcome: d.outcome, stage: d.stage, reason: d.reason },
    sandbox: null,
  }
}

export function sandboxStep(over: Partial<SandboxEvent> = {}): RunTimelineItem {
  const e = sandboxEvent(over)
  return { source: 'sandbox', at: e.at, decision: null, sandbox: e }
}

/** A sandboxed run whose sandbox stopped a network call and a file read, between a start and an exit. */
export function sandboxedRun(execution_id: string, over: Partial<AgentRunDetail> = {}): AgentRunDetail {
  const events = [
    sandboxEvent({ id: 'ev-start', kind: 'start', at: '2026-09-14T09:30:11.000Z', detail: { host: 'gateway.internal', port: 8000, limit: 'cpu 1, memory 512Mi, wall 300s' } }),
    sandboxEvent({ id: 'ev-net', kind: 'network_denied', at: '2026-09-14T09:30:12.000Z', detail: { host: 'api.openai.com', port: 443 } }),
    sandboxEvent({ id: 'ev-file', kind: 'file_denied', at: '2026-09-14T09:30:13.000Z', detail: { path: '/var/lib/dpkg/status' } }),
    sandboxEvent({ id: 'ev-exit', kind: 'exit', at: '2026-09-14T09:30:15.000Z', detail: { code: 0 } }),
  ]
  const timeline: RunTimelineItem[] = [
    decisionStep({ id: 'dec-run', action: 'agent.run', resource: null, created_at: '2026-09-14T09:30:10.500Z' }),
    { source: 'sandbox', at: events[0]!.at, decision: null, sandbox: events[0]! },
    decisionStep({ id: 'dec-tool', action: 'tool.call', resource: 'retrieve_chunks', created_at: '2026-09-14T09:30:11.500Z' }),
    { source: 'sandbox', at: events[1]!.at, decision: null, sandbox: events[1]! },
    { source: 'sandbox', at: events[2]!.at, decision: null, sandbox: events[2]! },
    decisionStep({ id: 'dec-deny', action: 'tool.call', resource: 'retrieve_chunks', outcome: 'deny', stage: 'policy', reason: 'kb_not_allowed', created_at: '2026-09-14T09:30:14.000Z' }),
    { source: 'sandbox', at: events[3]!.at, decision: null, sandbox: events[3]! },
  ]
  return {
    execution_id, job_id: 'job-1', status: 'succeeded', error_code: null, created_at: '2026-09-14T09:30:10.000Z',
    started_at: '2026-09-14T09:30:10.600Z', finished_at: '2026-09-14T09:30:15.100Z', result: null, decisions_url: '/v1/decisions',
    sandbox_events: events, timeline, ...over,
  }
}
