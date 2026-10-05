import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '@/api/endpoints'
import type { UsageSummary } from '@/api/types'
import { EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/governance/states'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { formatNumber, formatUsd } from '@/lib/utils'
import { DayChart } from './day-chart'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-hairline bg-surface p-4">
      <p className="eyebrow">{label}</p>
      <p className="tabular mt-1 text-title-1 font-semibold" data-testid={`stat-${label.toLowerCase()}`}>{value}</p>
    </div>
  )
}

export function UsageView({ data }: { data: UsageSummary }) {
  const empty = data.totals.requests === 0 && data.by_day.length === 0
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Requests" value={formatNumber(data.totals.requests)} />
        <Stat label="Tokens" value={formatNumber(data.totals.tokens)} />
        <Stat label="Cost" value={formatUsd(data.totals.cost_usd)} />
      </div>
      {empty ? (
        <EmptyState title="No usage in this period.">Usage is counted from requests that reach the model. Ask a question and it shows up here.</EmptyState>
      ) : (
        <div className="rounded-sm border border-hairline bg-surface p-4">
          <h2 className="mb-2 text-headline">Requests per day</h2>
          <DayChart days={data.by_day} />
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-sm border border-hairline bg-surface p-4" aria-label="Denied requests">
          <h2 className="mb-2 text-headline">Denied by stage</h2>
          <dl className="grid grid-cols-[1fr_auto] gap-y-1 text-callout">
            <dt>Policy</dt><dd className="mono tabular">{formatNumber(data.denied.policy)}</dd>
            <dt>Rate limit</dt><dd className="mono tabular">{formatNumber(data.denied.rate)}</dd>
            <dt>Budget</dt><dd className="mono tabular">{formatNumber(data.denied.budget)}</dd>
          </dl>
        </section>
        <section className="rounded-sm border border-hairline bg-surface p-4" aria-label="By principal">
          <h2 className="mb-2 text-headline">By principal</h2>
          {data.by_principal.length === 0 ? <p className="text-callout text-fg-secondary">No principal has made a request in this period.</p> : (
            <table className="w-full text-footnote">
              <thead><tr className="text-left text-fg-secondary"><th scope="col" className="py-1 font-medium">Principal</th><th scope="col" className="py-1 text-right font-medium">Requests</th><th scope="col" className="py-1 text-right font-medium">Tokens</th><th scope="col" className="py-1 text-right font-medium">Cost</th></tr></thead>
              <tbody>
                {data.by_principal.map((r) => (
                  <tr key={r.principal.id} className="border-t border-hairline">
                    <td className="py-1">{r.principal.name ?? r.principal.id.slice(0, 8)}</td>
                    <td className="mono tabular py-1 text-right">{formatNumber(r.requests)}</td>
                    <td className="mono tabular py-1 text-right">{formatNumber(r.tokens)}</td>
                    <td className="mono tabular py-1 text-right">{formatUsd(r.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  )
}

export default function UsagePage() {
  const [days, setDays] = useState(7)
  const q = useQuery({ queryKey: ['usage', days], queryFn: () => api.usage(days), retry: false })
  return (
    <div>
      <PageHeader
        title="Budgets and usage"
        actions={
          <label className="flex items-center gap-2 text-footnote text-fg-secondary">
            Period
            <Select aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option>
            </Select>
          </label>
        }
      >
        Requests, tokens and cost for the tenant, and what the gateway denied.
      </PageHeader>
      {q.isLoading ? (
        <div role="status" aria-label="Loading usage" className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-3"><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></div>
          <TableSkeleton rows={3} cols={3} />
        </div>
      ) : null}
      {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load usage." /> : null}
      {q.data ? <UsageView data={q.data} /> : null}
    </div>
  )
}
