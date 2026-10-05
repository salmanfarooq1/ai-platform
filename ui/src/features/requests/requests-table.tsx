import { Link } from 'react-router-dom'
import type { ReasonCode, RequestSummary } from '@/api/types'
import { EmptyState, ErrorState, TableSkeleton } from '@/components/governance/states'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import type { Density } from '@/lib/density'
import { stageLabel } from '@/lib/stages'
import { cn, formatTime } from '@/lib/utils'

interface RequestsTableProps {
  items: RequestSummary[] | undefined
  isLoading: boolean
  error?: unknown
  onRetry?: () => void
  selectedId?: string
  /** Query string to keep when opening a row, for example the active filters. */
  search?: string
  density?: Density
  filtered?: boolean
  reasons?: Record<string, ReasonCode>
}

const HEAD = ['Time', 'Outcome', 'Request', 'Principal', 'Checks', 'Stopped by', 'Policy'] as const
const RIGHT = new Set<string>(['Checks', 'Policy'])

/** One row per request. A request is a deny when any of its decisions was a deny. */
export function RequestsTable({ items, isLoading, error, onRetry, selectedId, search = '', density = 'compact', filtered = false, reasons }: RequestsTableProps) {
  if (isLoading) return <TableSkeleton rows={8} cols={HEAD.length} />
  if (error) return <ErrorState error={error} onRetry={onRetry} title="Could not load requests." />
  if (!items || items.length === 0) {
    return filtered ? (
      <EmptyState title="No requests match these filters.">Clear a filter to see more requests. Console views are left out unless you include them.</EmptyState>
    ) : (
      <EmptyState title="No requests yet.">
        Every call to the gateway is grouped into a request here. Run the walkthrough or ask a question in the workspace and its request appears in this table.
      </EmptyState>
    )
  }
  const rowH = density === 'compact' ? 'h-8' : 'h-10'
  return (
    <div className="overflow-x-auto rounded-sm border border-hairline bg-surface">
      <table className="w-full border-collapse text-footnote">
        <caption className="sr-only">Requests through the gateway, newest first</caption>
        <thead>
          <tr className="bg-muted text-left text-fg-secondary">
            {HEAD.map((h) => <th key={h} scope="col" className={cn('px-3 py-2 font-medium', RIGHT.has(h) && 'text-right')}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {items.map((r) => {
            const selected = r.request_id === selectedId
            const deny = r.first_deny
            return (
              <tr key={r.request_id} data-outcome={r.outcome} aria-selected={selected || undefined} className={cn(rowH, 'border-t border-hairline transition-colors duration-fast', selected ? 'bg-selected' : 'hover:bg-muted')}>
                <td className="mono whitespace-nowrap px-3">{formatTime(r.started_at)}</td>
                <td className="px-3"><VerdictBadge verdict={r.outcome === 'deny' ? 'deny' : 'allow'} size="sm" /></td>
                <td className="mono px-3">
                  <Link to={`/app/requests/${encodeURIComponent(r.request_id)}${search}`} className="rounded-sm underline-offset-2 hover:underline" aria-label={`Open request ${r.request_id}`}>
                    {r.request_id.length > 14 ? `${r.request_id.slice(0, 12)}...` : r.request_id}
                  </Link>
                </td>
                <td className="px-3">{r.principal ? (r.principal.name ?? r.principal.id.slice(0, 8)) : <span className="text-fg-tertiary">unknown</span>}</td>
                <td className="mono tabular px-3 text-right">{r.checks}</td>
                <td className="px-3">
                  {deny ? (
                    <span className="inline-flex flex-wrap items-baseline gap-x-2">
                      <span className="font-medium text-deny">{stageLabel(deny.stage)}</span>
                      <span className="text-fg-secondary">{reasons?.[deny.reason]?.title ?? deny.reason}</span>
                    </span>
                  ) : <span className="text-fg-tertiary">none</span>}
                </td>
                <td className="mono tabular px-3 text-right">{r.policy_version ?? 'default'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
