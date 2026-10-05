import type { DecisionDetail } from '@/api/types'
import { formatTime } from '@/lib/utils'
import { CopyValue } from './copy-value'

/** The decision receipt. Only the SHA-256 of the input is shown. The raw input is never stored. */
const COMPACT = new Set(['Decision id', 'Policy version', 'Action', 'Resource', 'Input SHA-256'])

/** `compact` keeps the five fields that identify the call. The full receipt is the default. */
export function Receipt({ decision, compact = false }: { decision: DecisionDetail; compact?: boolean }) {
  const rows: Array<[string, string | null]> = [
    ['Decision id', decision.id],
    ['Request id', decision.request_id],
    ['Policy version', decision.policy_version === null ? null : String(decision.policy_version)],
    ['Tenant', decision.tenant.slug],
    ['Principal', decision.principal ? (decision.principal.name ?? decision.principal.id) : null],
    ['Action', decision.action],
    ['Resource', decision.resource],
    ['Stage', decision.stage],
    ['Reason', decision.reason],
    ['Input SHA-256', decision.input_sha256],
    ['Recorded', formatTime(decision.created_at)],
  ]
  return (
    <section aria-label="Receipt">
      <h3 className="mb-2">Receipt</h3>
      <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-2 text-footnote">
        {rows.filter(([k]) => !compact || COMPACT.has(k)).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-fg-secondary">{k}</dt>
            <dd className="min-w-0">
              {v === null ? <span className="text-fg-tertiary">none</span> : <CopyValue value={v} label={k.toLowerCase()} />}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-footnote text-fg-tertiary">The platform keeps a hash of the input, not the text.</p>
    </section>
  )
}
