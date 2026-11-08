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
