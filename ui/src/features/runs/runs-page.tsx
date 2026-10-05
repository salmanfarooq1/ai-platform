import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/governance/states'
import { TraceTimeline } from '@/components/governance/trace-timeline'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn, formatTime } from '@/lib/utils'

// Runs are decisions with the action agent.run, one per request id, until a runs API exists (blueprint section 4).
function RunTimeline({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['decision', id], queryFn: () => api.decision(id), retry: false })
  if (q.isLoading) return <div role="status" aria-label="Loading run" className="flex flex-col gap-2"><Skeleton className="h-6" /><Skeleton className="h-24" /></div>
  if (q.error) return <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load this run." />
  if (!q.data) return null
  return (
    <div className="flex flex-col gap-3">
      <VerdictBadge verdict={q.data.outcome === 'deny' ? 'deny' : 'allow'} reason={q.data.reason} />
      <h3>Steps</h3>
      <TraceTimeline steps={q.data.trace} currentId={q.data.id} />
      <Link to={`/app/decisions/${q.data.id}`} className="text-callout text-brand underline-offset-2 hover:underline">Open receipt in Decisions</Link>
    </div>
  )
}

export default function RunsPage() {
  const [params, setParams] = useSearchParams()
  const selected = params.get('run') ?? undefined
  const q = useInfiniteQuery({
    queryKey: ['runs'],
    queryFn: ({ pageParam }) => api.decisions({ action: 'agent.run' }, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
  })
  const items = q.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <div>
      <PageHeader title="Agent runs">Each run is one agent request. Select a run to see the calls it made.</PageHeader>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0">
          {q.isLoading ? <TableSkeleton rows={6} cols={4} /> : null}
          {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load runs." /> : null}
          {q.data && items.length === 0 ? <EmptyState title="No agent runs yet.">Ask a question in Agent mode. Each run and every tool call it makes appear here.</EmptyState> : null}
          {items.length > 0 ? (
            <div className="overflow-x-auto rounded-sm border border-hairline bg-surface">
              <table className="w-full border-collapse text-footnote">
                <caption className="sr-only">Agent runs, newest first</caption>
                <thead><tr className="bg-muted text-left text-fg-secondary">{['Started', 'Verdict', 'Principal', 'Request id'].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
                <tbody>
                  {items.map((d) => (
                    <tr key={d.id} className={cn('h-8 border-t border-hairline', d.id === selected ? 'bg-brand-tint' : 'hover:bg-muted')}>
                      <td className="mono px-3">
                        <button type="button" className="underline-offset-2 hover:underline" aria-label={`Open run from ${formatTime(d.created_at)}`} onClick={() => setParams({ run: d.id }, { replace: true })}>{formatTime(d.created_at)}</button>
                      </td>
                      <td className="px-3"><VerdictBadge size="sm" verdict={d.outcome === 'deny' ? 'deny' : 'allow'} reason={d.reason} /></td>
                      <td className="px-3">{d.principal ? (d.principal.name ?? d.principal.id.slice(0, 8)) : 'unknown'}</td>
                      <td className="mono px-3 text-fg-secondary">{d.request_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {q.hasNextPage ? <div className="mt-3"><Button variant="secondary" size="sm" onClick={() => void q.fetchNextPage()}>Load more</Button></div> : null}
        </div>
        <aside aria-label="Run timeline" className="h-fit rounded-sm border border-hairline bg-surface p-4">
          {selected ? <RunTimeline id={selected} /> : <p className="text-callout text-fg-secondary">Select a run to see its step timeline.</p>}
        </aside>
      </div>
    </div>
  )
}
