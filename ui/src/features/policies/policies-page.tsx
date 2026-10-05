import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '@/api/endpoints'
import type { PolicyVersion } from '@/api/types'
import { EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/governance/states'
import { cn, formatTime } from '@/lib/utils'

export function PolicyDocument({ policy }: { policy: PolicyVersion }) {
  return (
    <section aria-label={`Policy version ${policy.version}`}>
      <div className="mb-2 flex items-center justify-between">
        <h3>Version <span className="mono">{policy.version}</span></h3>
        <span className="text-footnote text-fg-secondary">{policy.active ? 'Active' : 'Superseded'}, created {formatTime(policy.created_at)}{policy.created_by ? ` by ${policy.created_by}` : ''}</span>
      </div>
      <pre className="mono overflow-x-auto rounded-sm bg-muted p-3 text-footnote leading-relaxed" tabIndex={0} aria-label="Policy document JSON">{JSON.stringify(policy.document, null, 2)}</pre>
    </section>
  )
}

export default function PoliciesPage() {
  const list = useQuery({ queryKey: ['policies'], queryFn: api.policies, retry: false })
  const [params, setParams] = useSearchParams()
  const versions = list.data?.versions ?? []
  const selected = Number(params.get('v')) || versions[0]?.version
  const doc = versions.find((v) => v.version === selected)

  return (
    <div>
      <PageHeader title="Policies">Versions of the tenant policy. Edit them with the admin CLI.</PageHeader>
      {list.isLoading ? <TableSkeleton rows={4} cols={2} /> : null}
      {list.error ? <ErrorState error={list.error} onRetry={() => void list.refetch()} title="Could not load policies." /> : null}
      {list.data?.default_in_effect ? (
        <p role="note" className="mb-3 rounded-sm bg-muted px-3 py-2 text-callout text-fg-secondary">No tenant policy is active. Scopes grant against the platform defaults.</p>
      ) : null}
      {list.data && versions.length === 0 ? (
        <EmptyState title="No policy versions yet.">Set one with <code className="mono">scripts/admin/identity.py set-policy</code>. Until then the platform default applies.</EmptyState>
      ) : null}
      {versions.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-[240px_minmax(0,1fr)]">
          <ul aria-label="Policy versions" className="m-0 flex list-none flex-col gap-1 p-0">
            {versions.map((v) => (
              <li key={v.version}>
                <button
                  type="button"
                  aria-current={v.version === selected ? 'true' : undefined}
                  onClick={() => setParams({ v: String(v.version) }, { replace: true })}
                  className={cn('flex w-full items-center justify-between rounded-sm border border-hairline px-3 py-2 text-left text-callout', v.version === selected ? 'bg-brand-tint' : 'bg-surface hover:bg-muted')}
                >
                  <span className="mono">v{v.version}</span>
                  <span className="text-footnote text-fg-secondary">{v.active ? 'Active' : formatTime(v.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="min-w-0 rounded-sm border border-hairline bg-surface p-4">{doc ? <PolicyDocument policy={doc} /> : null}</div>
        </div>
      ) : null}
    </div>
  )
}
