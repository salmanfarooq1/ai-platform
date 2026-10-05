import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/endpoints'
import { EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/governance/states'
import { formatTime } from '@/lib/utils'

export default function KeysPage() {
  const q = useQuery({ queryKey: ['principals'], queryFn: api.principals, retry: false })
  const rows = (q.data ?? []).flatMap((p) => p.keys.map((k) => ({ p, k })))
  return (
    <div>
      <PageHeader title="Keys and principals">Key prefixes and scopes. The secret is shown once when a key is created and is never stored.</PageHeader>
      {q.isLoading ? <TableSkeleton rows={4} cols={6} /> : null}
      {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load keys." /> : null}
      {q.data && rows.length === 0 ? <EmptyState title="No keys yet.">Create a key with <code className="mono">scripts/admin/identity.py create-key</code>. It appears here by prefix.</EmptyState> : null}
      {rows.length > 0 ? (
        <div className="overflow-x-auto rounded-sm border border-hairline bg-surface">
          <table className="w-full border-collapse text-footnote">
            <caption className="sr-only">API keys by principal</caption>
            <thead>
              <tr className="bg-muted text-left text-fg-secondary">
                {['Principal', 'Kind', 'Prefix', 'Scopes', 'Created', 'Last used', 'Status'].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ p, k }) => (
                <tr key={k.prefix} className="h-8 border-t border-hairline">
                  <td className="px-3">{p.name}</td>
                  <td className="px-3 text-fg-secondary">{p.kind}</td>
                  <td className="mono px-3">{k.prefix}</td>
                  <td className="mono px-3">{k.scopes.join(' ')}</td>
                  <td className="mono px-3 text-fg-secondary">{formatTime(k.created_at)}</td>
                  <td className="mono px-3 text-fg-secondary">{k.last_used_at ? formatTime(k.last_used_at) : 'not tracked'}</td>
                  <td className="px-3">{k.revoked ? 'Revoked' : 'Active'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
