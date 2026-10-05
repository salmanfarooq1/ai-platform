import { Link } from 'react-router-dom'
import type { DecisionSummary } from '@/api/types'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { EmptyState, ErrorState, TableSkeleton } from '@/components/governance/states'
import { cn, formatTime } from '@/lib/utils'

interface DecisionsTableProps {
  items: DecisionSummary[] | undefined
  isLoading: boolean
  error?: unknown
  onRetry?: () => void
  selectedId?: string
  /** Query string to keep when opening a row, for example the active filters. */
  search?: string
  density?: 'compact' | 'comfortable'
  filtered?: boolean
}

const HEAD = ['Time', 'Verdict', 'Action', 'Resource', 'Principal', 'Policy'] as const

export function DecisionsTable({ items, isLoading, error, onRetry, selectedId, search = '', density = 'compact', filtered = false }: DecisionsTableProps) {
  if (isLoading) return <TableSkeleton rows={8} cols={HEAD.length} />
  if (error) return <ErrorState error={error} onRetry={onRetry} title="Could not load decisions." />
  if (!items || items.length === 0) {
    return filtered ? (
      <EmptyState title="No decisions match these filters.">Clear a filter to see more of the log.</EmptyState>
    ) : (
      <EmptyState title="No decisions yet.">
        Every model, tool and knowledge base call writes one row here. Ask a question in the workspace and its decisions appear in this table.
      </EmptyState>
    )
  }
  const rowH = density === 'compact' ? 'h-8' : 'h-10'
  return (
    <div className="overflow-x-auto rounded-sm border border-hairline bg-surface">
      <table className="w-full border-collapse text-footnote">
        <caption className="sr-only">Gateway decisions, newest first</caption>
        <thead>
          <tr className="bg-muted text-left text-fg-secondary">
            {HEAD.map((h) => <th key={h} scope="col" className={cn('px-3 py-2 font-medium', h === 'Policy' && 'text-right')}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {items.map((d) => {
            const selected = d.id === selectedId
            return (
              <tr key={d.id} data-outcome={d.outcome} aria-selected={selected || undefined} className={cn(rowH, 'border-t border-hairline', selected ? 'bg-selected' : 'hover:bg-muted')}>
                <td className="mono whitespace-nowrap px-3">
                  <Link to={`/app/decisions/${d.id}${search}`} className="rounded-sm underline-offset-2 hover:underline" aria-label={`Open decision ${d.action} at ${formatTime(d.created_at)}`}>
                    {formatTime(d.created_at)}
                  </Link>
                </td>
                <td className="px-3"><VerdictBadge verdict={d.outcome === 'deny' ? 'deny' : 'allow'} reason={d.reason} size="sm" /></td>
                <td className="mono px-3">{d.action}</td>
                <td className="mono px-3 text-fg-secondary">{d.resource ?? 'none'}</td>
                <td className="px-3">{d.principal ? (d.principal.name ?? d.principal.id.slice(0, 8)) : <span className="text-fg-tertiary">unknown</span>}</td>
                <td className="mono tabular px-3 text-right">{d.policy_version ?? 'default'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
