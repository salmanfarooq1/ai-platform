import type { DecisionDetail, DecisionSummary } from '@/api/types'
import { Receipt } from '@/components/governance/receipt'
import { TraceTimeline } from '@/components/governance/trace-timeline'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import type { StepId } from './story-data'

// These panels use the real console components with an example request. The data is labelled as an example.
const T0 = Date.UTC(2026, 8, 14, 9, 30, 12)
const base = { request_id: 'req_example', principal: { id: 'p1', name: 'contracts-agent' }, policy_version: 3 }
const SHA = '725918da651359d33209d0642f3b31a83cbf4fbc7e0d25040e56c279b0d0cdf2'.slice(0, 64)

const askDecision: DecisionSummary = { ...base, id: 'd1', created_at: new Date(T0).toISOString(), action: 'agent.run', resource: null, outcome: 'allow', stage: 'policy', reason: 'allowed' }
const kbAllow: DecisionSummary = { ...base, id: 'd2', created_at: new Date(T0 + 140).toISOString(), action: 'kb.read', resource: 'contracts', outcome: 'allow', stage: 'policy', reason: 'allowed' }
const kbDeny: DecisionSummary = { ...base, id: 'd3', created_at: new Date(T0 + 310).toISOString(), action: 'kb.read', resource: 'payroll', outcome: 'deny', stage: 'policy', reason: 'kb_not_allowed' }

const detail: DecisionDetail = {
  ...kbAllow,
  id: 'd2',
  tenant: { id: 't1', slug: 'northwind' },
  input_sha256: SHA,
  trace: [askDecision, kbAllow, kbDeny],
}

const STAGES = ['principal', 'boundary', 'policy', 'input guardrails', 'rate limit', 'token budget']

function Frame({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col gap-3 rounded-xl border border-hairline bg-surface p-5">
      <p className="eyebrow">{label}</p>
      {children}
    </div>
  )
}

export function StoryPanel({ id }: { id: StepId }) {
  switch (id) {
    case 'ask':
      return (
        <Frame label="Example request">
          <dl className="grid grid-cols-[90px_1fr] gap-x-3 gap-y-2 text-callout">
            <dt className="text-fg-secondary">Caller</dt><dd>contracts-agent</dd>
            <dt className="text-fg-secondary">Action</dt><dd className="mono">agent.run</dd>
            <dt className="text-fg-secondary">Question</dt><dd>Which contracts renew this quarter?</dd>
            <dt className="text-fg-secondary">Tenant</dt><dd className="mono">northwind, from the key</dd>
          </dl>
        </Frame>
      )
    case 'gateway':
      return (
        <Frame label="Gateway stages">
          <ol className="m-0 flex list-none flex-col gap-1.5 p-0 text-callout">
            {STAGES.map((s, i) => (
              <li key={s} className="flex items-center gap-3 rounded-sm bg-muted px-3 py-1.5">
                <span className="mono tabular w-5 text-fg-secondary">{i + 1}</span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </Frame>
      )
    case 'policy':
      return (
        <Frame label="Example tenant policy">
          <pre className="mono overflow-x-auto rounded-sm bg-muted p-3 text-footnote leading-relaxed">{JSON.stringify({ allowed_kbs: ['contracts', 'handbook'], allowed_tools: '*', allowed_models: '*', max_tool_calls: 8, max_tokens_per_request: 4000 }, null, 2)}</pre>
        </Frame>
      )
    case 'verdict':
      return (
        <Frame label="Two example verdicts">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3"><VerdictBadge verdict="allow" /><code className="mono text-footnote">kb.read on contracts</code></div>
            <div className="flex flex-wrap items-center gap-3"><VerdictBadge verdict="deny" reason="kb_not_allowed" /><code className="mono text-footnote">kb.read on payroll</code></div>
          </div>
          <TraceTimeline steps={[askDecision, kbAllow, kbDeny]} />
        </Frame>
      )
    case 'receipt':
      return (
        <Frame label="Example receipt">
          <Receipt decision={detail} />
        </Frame>
      )
  }
}
