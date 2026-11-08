import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/governance/states'
import { CopyValue } from '@/components/governance/copy-value'
import { RunSteps } from '@/components/governance/run-steps'
import { TraceTimeline } from '@/components/governance/trace-timeline'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useReasonCodes } from '@/lib/reasons'
import { sandboxSummary } from '@/lib/sandbox'
import { cn, formatTime } from '@/lib/utils'
import { runDuration, runStatusWord } from './run-status'
import { useModuleAvailability } from '@/app/modules'

// Runs are listed from their decisions (the verdict, and the runs that were refused before they started) and joined
// by execution id to GET /v1/agent/runs, which gives each run's status and times (see run-status.ts).
function RunTimeline({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['decision', id], queryFn: () => api.decision(id), retry: false })
  const { byCode } = useReasonCodes()
  // The run's own record: its sandbox events, merged by time with every decision it caused. A run that was refused before
  // it started, or that the caller may not read, has none: the page then shows the request's trace as before.
  const executionId = q.data?.execution_id ?? undefined
  const run = useQuery({ queryKey: ['agent-run', executionId], queryFn: () => api.agentRunDetail(executionId ?? ''), enabled: !!executionId, retry: false })
  const sandboxed = (run.data?.sandbox_events.length ?? 0) > 0
  const stopped = sandboxSummary(run.data?.sandbox_events ?? [])
  if (q.isLoading) return <div role="status" aria-label="Loading run" className="flex flex-col gap-2"><Skeleton className="h-6" /><Skeleton className="h-24" /></div>
  if (q.error) return <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load this run." />
  if (!q.data) return null
  return (
    <div className="flex flex-col gap-3">
      <VerdictBadge verdict={q.data.outcome === 'deny' ? 'deny' : 'allow'} reason={q.data.reason} />
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-footnote">
        <dt className="text-fg-secondary">Run status</dt>
        <dd data-testid="run-status">{runStatusWord(q.data.run_status)}</dd>
        <dt className="text-fg-secondary">Execution id</dt>
        <dd>{q.data.execution_id ? <CopyValue value={q.data.execution_id} label="execution id" /> : 'None'}</dd>
      </dl>
      {sandboxed ? (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-footnote">
          <dt className="text-fg-secondary">Sandbox</dt>
          <dd data-testid="run-sandbox-summary">{stopped ?? 'Ran inside the sandbox. Nothing was blocked.'}</dd>
        </dl>
      ) : null}
      <h3>Steps</h3>
      {sandboxed && run.data ? (
        <RunSteps items={run.data.timeline} reasons={byCode} />
      ) : (
        <TraceTimeline steps={q.data.trace} currentId={q.data.id} reasons={byCode} />
      )}
      <Link to={`/app/decisions/${q.data.id}`} className="text-callout text-seal underline-offset-2 hover:underline">Open receipt in Decisions</Link>
    </div>
  )
}

export default function RunsPage() {
  const availability = useModuleAvailability()
  const [params, setParams] = useSearchParams()
  const selected = params.get('run') ?? undefined
  const q = useInfiniteQuery({
    queryKey: ['runs'],
    queryFn: ({ pageParam }) => api.decisions({ action: 'agent.run' }, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
    enabled: availability.agentEnabled,
  })
  // The runs endpoint is where status and times come from. Poll it only while a run is queued or running.
  const runs = useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => api.agentRuns(),
    retry: false,
    enabled: availability.agentEnabled,
    refetchInterval: (r) => (r.state.data?.items.some((x) => x.status === 'queued' || x.status === 'running') ? 3000 : false),
  })
  const byExecution = new Map((runs.data?.items ?? []).map((r) => [r.execution_id, r]))
  const items = q.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <div>
      <PageHeader title="Agent runs">Each run is one agent request, with its execution id and status. Select a run to see the calls it made.</PageHeader>
      {availability.ready && !availability.agentEnabled ? <div role="status" className="mb-4 rounded-sm border border-hairline bg-surface p-4 text-callout text-fg-secondary">Agent runs are unavailable in this edition.</div> : null}
      {!availability.ready && !availability.modules.isLoading && !availability.modules.error ? <div role="status" className="mb-4 rounded-sm border border-hairline bg-surface p-4 text-callout text-fg-secondary">Module availability is not known. Run data stays hidden until it can be checked.</div> : null}
      {availability.modules.isLoading ? <div role="status" aria-label="Loading module availability"><Skeleton className="mb-4 h-16" /></div> : null}
      {availability.modules.error ? <ErrorState error={availability.modules.error} onRetry={() => void availability.modules.refetch()} title="Could not load module availability." /> : null}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0">
          {availability.agentEnabled && q.isLoading ? <TableSkeleton rows={6} cols={7} /> : null}
          {availability.agentEnabled && q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load runs." /> : null}
          {availability.agentEnabled && q.data && items.length === 0 ? <EmptyState title="No agent runs yet.">Ask a question in Agent mode. Each run and every tool call it makes appear here.</EmptyState> : null}
          {availability.agentEnabled && items.length > 0 ? (
            <div className="overflow-x-auto rounded-sm border border-hairline bg-surface">
              <table className="w-full border-collapse text-footnote">
                <caption className="sr-only">Agent runs, newest first</caption>
                <thead><tr className="bg-muted text-left text-fg-secondary">{['Started', 'Verdict', 'Status', 'Duration', 'Execution id', 'Principal', 'Request id'].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
                <tbody>
                  {items.map((d) => (
                    <tr key={d.id} className={cn('h-8 border-t border-hairline', d.id === selected ? 'bg-selected' : 'hover:bg-muted')}>
                      <td className="mono px-3">
                        <button type="button" className="underline-offset-2 hover:underline" aria-label={`Open run from ${formatTime(d.created_at)}`} onClick={() => setParams({ run: d.id }, { replace: true })}>{formatTime(d.created_at)}</button>
                      </td>
                      <td className="px-3"><VerdictBadge size="sm" verdict={d.outcome === 'deny' ? 'deny' : 'allow'} reason={d.reason} /></td>
                      <td className="px-3" data-testid="run-row-status">{runStatusWord(byExecution.get(d.execution_id ?? '')?.status ?? d.run_status)}</td>
                      <td className="mono tabular px-3 text-fg-secondary" data-testid="run-row-duration">{d.execution_id && byExecution.has(d.execution_id) ? runDuration(byExecution.get(d.execution_id)?.started_at, byExecution.get(d.execution_id)?.finished_at) : 'None'}</td>
                      <td className="mono px-3 text-fg-secondary" data-testid="run-row-execution-id" title={d.execution_id ?? undefined}>{d.execution_id ? d.execution_id.slice(0, 8) : 'None'}</td>
                      <td className="px-3">{d.principal ? (d.principal.name ?? d.principal.id.slice(0, 8)) : 'unknown'}</td>
                      <td className="mono px-3 text-fg-secondary">{d.request_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {availability.agentEnabled && q.hasNextPage ? <div className="mt-3"><Button variant="secondary" size="sm" onClick={() => void q.fetchNextPage()}>Load more</Button></div> : null}
        </div>
        <aside aria-label="Run timeline" className="h-fit rounded-sm border border-hairline bg-surface p-4">
          {availability.agentEnabled && selected ? <RunTimeline id={selected} /> : <p className="text-callout text-fg-secondary">{availability.agentEnabled ? 'Select a run to see its step timeline.' : 'Run details are hidden while Agent mode is unavailable.'}</p>}
        </aside>
      </div>
    </div>
  )
}
