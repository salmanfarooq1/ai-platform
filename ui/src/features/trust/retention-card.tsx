import type { TrustSummary } from '@/api/types'
import { formatTime } from '@/lib/utils'

/** Retention settings, read only. A change goes through the admin command line tool, like policies. */
export function RetentionCard({ summary }: { summary: TrustSummary }) {
  return (
    <div className="flex flex-col gap-3">
      <dl className="grid max-w-xl grid-cols-[160px_minmax(0,1fr)] gap-x-3 gap-y-1.5 rounded-md border border-hairline bg-surface p-4 text-callout">
        <dt className="text-fg-secondary">Kept for</dt>
        <dd data-testid="retention-days"><span className="mono tabular">{summary.retention_days}</span> days <span className="text-fg-secondary">({summary.retention_is_default ? 'platform default' : 'set for this tenant'})</span></dd>
        <dt className="text-fg-secondary">Oldest record</dt>
        <dd data-testid="oldest-record" className="mono">{summary.oldest_decision_at ? formatTime(summary.oldest_decision_at) : 'none yet'}</dd>
        <dt className="text-fg-secondary">Last purge</dt>
        <dd data-testid="last-purge" className="mono">{summary.last_purge_at ? formatTime(summary.last_purge_at) : 'never'}</dd>
      </dl>
      <p className="max-w-prose text-footnote text-fg-secondary">
        Decision records older than this are deleted once a day. A checkpoint stays in the chain, so the records that remain still verify.
        Change the period with <code className="mono">scripts/admin/identity.py set-retention</code>.
      </p>
    </div>
  )
}
