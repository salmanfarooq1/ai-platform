import { Receipt } from '@/components/governance/receipt'
import { TraceTimeline } from '@/components/governance/trace-timeline'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { EXAMPLE_POLICY, EXAMPLE_STAGES, exampleReceipt, exampleTrace } from './example-data'
import type { StepId } from './story-data'

// These panels use the real console components with an example request. The data is labelled as an example.
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
        <Frame label="Example gateway stages">
          <ol className="m-0 flex list-none flex-col gap-1.5 p-0 text-callout">
            {EXAMPLE_STAGES.map((s, i) => (
              <li key={s.code} className="flex items-center gap-3 rounded-sm bg-muted px-3 py-1.5">
                <span className="mono tabular w-5 text-fg-secondary">{i + 1}</span>
                <span>{s.name}</span>
              </li>
            ))}
          </ol>
        </Frame>
      )
    case 'policy':
      return (
        <Frame label="Example tenant policy">
          <pre className="mono overflow-x-auto rounded-sm bg-muted p-3 text-footnote leading-relaxed">{JSON.stringify(EXAMPLE_POLICY, null, 2)}</pre>
        </Frame>
      )
    case 'verdict':
      return (
        <Frame label="Two example verdicts">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3"><VerdictBadge verdict="allow" /><code className="mono text-footnote">kb.read on contracts</code></div>
            <div className="flex flex-wrap items-center gap-3"><VerdictBadge verdict="deny" reason="kb_not_allowed" /><code className="mono text-footnote">kb.read on payroll</code></div>
          </div>
          <TraceTimeline steps={exampleTrace} />
        </Frame>
      )
    case 'receipt':
      return (
        <Frame label="Example receipt">
          <Receipt decision={exampleReceipt} />
        </Frame>
      )
  }
}
