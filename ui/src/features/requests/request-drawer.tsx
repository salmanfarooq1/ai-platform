import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/api/endpoints'
import type { RequestDetail } from '@/api/types'
import { CopyValue } from '@/components/governance/copy-value'
import { DenyCallout } from '@/components/governance/deny-callout'
import { ErrorState } from '@/components/governance/states'
import { TraceTimeline } from '@/components/governance/trace-timeline'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { isApiError } from '@/api/client'
import { useReasonCodes } from '@/lib/reasons'
import { formatTime } from '@/lib/utils'

/** The body of the drawer: the verdict, the deny emphasis, the stage trace and one receipt link per decision. */
export function RequestDetailView({ request }: { request: RequestDetail }) {
  const { byCode } = useReasonCodes()
  const denied = request.outcome === 'deny'
  const firstDeny = request.decisions.find((d) => d.outcome === 'deny')
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <VerdictBadge verdict={denied ? 'deny' : 'allow'} reason={firstDeny?.reason} />
        <p className="text-callout text-fg-secondary">
          {request.decisions.length} {request.decisions.length === 1 ? 'check' : 'checks'}
          {request.policy_version !== null ? <> under policy version <code className="mono">{request.policy_version}</code></> : <> under the platform default policy</>}.
        </p>
      </div>
      {firstDeny ? (
        <DenyCallout
          reason={firstDeny.reason}
          stage={firstDeny.stage}
          policyVersion={firstDeny.policy_version}
          action={firstDeny.action}
          resource={firstDeny.resource}
        />
      ) : null}
      <section aria-label="Stage trace">
        <h3 className="mb-2">Trace</h3>
        <TraceTimeline steps={request.decisions} reasons={byCode} />
      </section>
      <section aria-label="Request details">
        <h3 className="mb-2">Request</h3>
        <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-2 text-footnote">
          <dt className="text-fg-secondary">Request id</dt>
          <dd className="min-w-0"><CopyValue value={request.request_id} label="request id" /></dd>
          <dt className="text-fg-secondary">Started</dt>
          <dd className="mono">{formatTime(request.started_at)}</dd>
          <dt className="text-fg-secondary">Principal</dt>
          <dd>{request.principal ? (request.principal.name ?? request.principal.id) : <span className="text-fg-tertiary">unknown</span>}</dd>
          <dt className="text-fg-secondary">Tenant</dt>
          <dd className="mono">{request.tenant.slug}</dd>
        </dl>
      </section>
      <section aria-label="Receipts">
        <h3 className="mb-2">Receipts</h3>
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-callout">
          {request.decisions.map((d) => (
            <li key={d.id}>
              <Link to={`/app/decisions/${d.id}`} className="inline-flex flex-wrap items-baseline gap-x-2 rounded-sm text-seal underline-offset-2 hover:underline">
                Open receipt <code className="mono text-footnote">{d.action}{d.resource ? ` ${d.resource}` : ''}</code>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

interface RequestDrawerProps {
  requestId: string | undefined
  onClose: () => void
}

/** A slide-over on Radix Dialog. It opens at /app/requests/:requestId and closes back to the list. */
export function RequestDrawer({ requestId, onClose }: RequestDrawerProps) {
  const q = useQuery({
    queryKey: ['request', requestId],
    queryFn: () => api.requestDetail(requestId as string),
    enabled: !!requestId,
    retry: false,
  })
  const notFound = isApiError(q.error) && q.error.status === 404
  return (
    <Sheet open={!!requestId} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent aria-describedby="request-drawer-desc">
        <SheetTitle className="pr-8 text-title-2 font-semibold">Request</SheetTitle>
        <SheetDescription id="request-drawer-desc" className="mono mb-4 mt-1 break-all text-footnote text-fg-secondary">{requestId}</SheetDescription>
        {q.isLoading ? (
          <div role="status" aria-label="Loading request" className="flex flex-col gap-3">
            <Skeleton className="h-7 w-32" /><Skeleton className="h-24" /><Skeleton className="h-32" />
          </div>
        ) : null}
        {notFound ? <p className="text-callout text-fg-secondary">No request with this id was found for your tenant.</p> : null}
        {q.error && !notFound ? <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load this request." /> : null}
        {q.data ? <RequestDetailView request={q.data} /> : null}
      </SheetContent>
    </Sheet>
  )
}
