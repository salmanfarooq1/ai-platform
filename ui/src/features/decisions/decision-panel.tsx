import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/api/endpoints'
import type { DecisionDetail } from '@/api/types'
import { DenyCallout } from '@/components/governance/deny-callout'
import { Receipt } from '@/components/governance/receipt'
import { ErrorState } from '@/components/governance/states'
import { TraceTimeline } from '@/components/governance/trace-timeline'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useReasonCodes } from '@/lib/reasons'

function extensionObject(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function ExtensionValue({ value }: { value: unknown }) {
  return <code className="mono break-all">{typeof value === 'string' ? value : JSON.stringify(value)}</code>
}

function ModelEvidence({ extensions }: { extensions: DecisionDetail['extensions'] }) {
  const model = extensionObject(extensions.model)
  const stages = Array.isArray(extensions.stages) ? extensions.stages : null
  if (!model && !stages) return null

  const identity = model ? [
    ['Alias', model.name],
    ['Source', model.source],
    ['Digest', model.digest],
    ['Provider model id', model.provider_model_id],
    ['Region', model.region],
    ['Phase', model.phase],
  ] as const : []

  return (
    <section aria-label="Model evidence" className="flex flex-col gap-3">
      {model ? (
        <div>
          <h3 className="mb-2">Model</h3>
          <dl className="grid grid-cols-[120px_minmax(0,1fr)] gap-x-3 gap-y-2 text-footnote">
            {identity.filter(([, value]) => value !== undefined && value !== null).map(([label, value]) => (
              <div key={label} className="contents"><dt className="text-fg-secondary">{label}</dt><dd className="min-w-0"><ExtensionValue value={value} /></dd></div>
            ))}
          </dl>
        </div>
      ) : null}
      {stages ? (
        <div>
          <h3 className="mb-2">Stages</h3>
          <ol aria-label="Stages" className="m-0 list-decimal space-y-2 pl-5 text-footnote">
            {stages.map((value, index) => {
              const stage = extensionObject(value)
              if (!stage) return null
              return (
                <li key={`${String(stage.stage)}-${index}`}>
                  <span className="font-medium">{String(stage.stage ?? 'Unknown stage')}</span>
                  {' · '}{String(stage.status ?? 'Unknown status')}
                  {stage.reason === null || stage.reason === undefined || stage.reason === '' ? null : <> · <ExtensionValue value={stage.reason} /></>}
                </li>
              )
            })}
          </ol>
        </div>
      ) : null}
    </section>
  )
}

export function DecisionDetailView({ decision }: { decision: DecisionDetail }) {
  const denied = decision.outcome === 'deny'
  const { byCode } = useReasonCodes()
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <VerdictBadge verdict={denied ? 'deny' : 'allow'} reason={decision.reason} />
        <p className="text-callout text-fg-secondary">
          <code className="mono">{decision.action}</code>
          {decision.resource ? <> on <code className="mono">{decision.resource}</code></> : null}
          {decision.policy_version !== null ? <> under policy version <code className="mono">{decision.policy_version}</code></> : <> under the platform default policy</>}.
        </p>
        <p className="text-footnote text-fg-secondary">Record v{decision.record_version}</p>
        {denied ? <DenyCallout reason={decision.reason} stage={decision.stage} policyVersion={decision.policy_version} /> : null}
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <Link to={`/app/requests/${encodeURIComponent(decision.request_id)}`} className="text-callout text-seal underline-offset-2 hover:underline">Open the whole request</Link>
          <Link to={`/app/trust?decision=${encodeURIComponent(decision.id)}`} className="text-callout text-seal underline-offset-2 hover:underline">Verify receipt</Link>
        </div>
      </div>
      <section aria-label="Stage trace">
        <h3 className="mb-2">Trace</h3>
        <TraceTimeline steps={decision.trace} currentId={decision.id} reasons={byCode} />
      </section>
      <ModelEvidence extensions={decision.extensions} />
      <Receipt decision={decision} />
    </div>
  )
}

export function DecisionPanel({ id }: { id: string | undefined }) {
  const q = useQuery({ queryKey: ['decision', id], queryFn: () => api.decision(id as string), enabled: !!id, retry: false })
  if (!id) {
    return <p className="text-callout text-fg-secondary">Select a decision to see its verdict, trace and receipt.</p>
  }
  if (q.isLoading) {
    return (
      <div role="status" aria-label="Loading decision" className="flex flex-col gap-3">
        <Skeleton className="h-7 w-32" /><Skeleton className="h-16" /><Skeleton className="h-32" />
      </div>
    )
  }
  if (q.error) return <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load this decision." />
  if (!q.data) return null
  return <DecisionDetailView decision={q.data} />
}
