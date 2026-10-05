import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/endpoints'
import { ErrorState, PageHeader } from '@/components/governance/states'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

function uptime(s: number | undefined): string {
  if (!s) return 'not reported'
  const d = Math.floor(s / 86400); const h = Math.floor((s % 86400) / 3600); const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${s % 60}s`
}

export default function SystemPage() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: false, refetchInterval: 30_000 })
  const config = useQuery({ queryKey: ['config'], queryFn: api.config, retry: false, staleTime: 300_000 })
  const h = health.data
  const services = h ? [
    { name: 'Database', ok: h.db === 'ok', detail: h.db },
    { name: 'Redis', ok: h.redis === 'ok', detail: h.redis },
    ...(h.embedding ? [{ name: 'Embeddings', ok: h.embedding === 'ok', detail: h.embedding }] : []),
  ] : []
  return (
    <div>
      <PageHeader title="System">Service health, mode and the limits this deployment applies.</PageHeader>
      {health.isLoading ? <div role="status" aria-label="Loading health" className="grid gap-3 sm:grid-cols-3"><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></div> : null}
      {health.error ? <ErrorState error={health.error} onRetry={() => void health.refetch()} title="Could not load service health." /> : null}
      {h ? (
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            {services.map((s) => (
              <div key={s.name} className="rounded-md border border-hairline bg-surface p-4">
                <p className="eyebrow">{s.name}</p>
                <p className={cn('mt-1 text-headline font-semibold', s.ok ? 'text-allow' : 'text-deny')}>{s.ok ? 'Healthy' : 'Unavailable'}</p>
                <p className="mono text-footnote text-fg-secondary">{s.detail}</p>
              </div>
            ))}
          </div>
          <dl className="grid max-w-xl grid-cols-[160px_1fr] gap-y-1.5 rounded-md border border-hairline bg-surface p-4 text-callout">
            <dt className="text-fg-secondary">Status</dt><dd className="mono">{h.status}</dd>
            <dt className="text-fg-secondary">Mode</dt><dd className="mono">{h.mode ?? 'not reported'}</dd>
            <dt className="text-fg-secondary">API version</dt><dd className="mono">{h.version}</dd>
            <dt className="text-fg-secondary">Uptime</dt><dd className="mono">{uptime(h.uptime_seconds)}</dd>
            {config.data ? (
              <>
                <dt className="text-fg-secondary">Reranker</dt><dd className="mono">{config.data.reranker_enabled ? 'enabled' : 'disabled in this mode'}</dd>
                <dt className="text-fg-secondary">Rate limit</dt><dd className="mono">{config.data.rate_limit_rpm} per {config.data.rate_limit_window_seconds}s</dd>
                <dt className="text-fg-secondary">Daily token budget</dt><dd className="mono tabular">{config.data.daily_token_budget.toLocaleString('en-US')}</dd>
              </>
            ) : null}
          </dl>
        </div>
      ) : null}
    </div>
  )
}
