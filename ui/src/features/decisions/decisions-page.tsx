import { useInfiniteQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '@/api/endpoints'
import type { DecisionFilters, Outcome } from '@/api/types'
import { PageHeader } from '@/components/governance/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { Select } from '@/components/ui/select'
import { DecisionPanel } from './decision-panel'
import { DecisionsTable } from './decisions-table'

const SINCE: Record<string, number> = { '1h': 3_600_000, '24h': 86_400_000, '7d': 604_800_000 }

export default function DecisionsPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [density, setDensity] = useState<'compact' | 'comfortable'>('compact')

  const outcome = (params.get('outcome') as Outcome | null) ?? undefined
  const action = params.get('action') ?? ''
  const requestId = params.get('request_id') ?? ''
  const since = params.get('since') ?? ''
  const policy = params.get('policy_version') ?? ''

  // `since` is turned into a timestamp once per change, so the query key stays stable between renders.
  const sinceIso = useMemo(() => (since && SINCE[since] ? new Date(Date.now() - (SINCE[since] ?? 0)).toISOString() : undefined), [since])
  const filters: DecisionFilters = {
    outcome, action: action || undefined, request_id: requestId || undefined, since: sinceIso,
    policy_version: policy ? Number(policy) : undefined,
  }
  const active = Boolean(outcome || action || requestId || since || policy)

  const q = useInfiniteQuery({
    queryKey: ['decisions', filters],
    queryFn: ({ pageParam }) => api.decisions(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
  })
  const items = useMemo(() => q.data?.pages.flatMap((p) => p.items), [q.data])

  // Arriving with a request id and no selection (the "Open receipt" link from Ask): open the entry call of that request.
  useEffect(() => {
    if (!id && requestId && items && items.length > 0) {
      const entry = items[items.length - 1]
      if (entry) navigate(`/app/decisions/${entry.id}?${params.toString()}`, { replace: true })
    }
  }, [id, requestId, items, navigate, params])

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const search = params.toString() ? `?${params.toString()}` : ''

  return (
    <div>
      <PageHeader title="Decisions">Every governed call and the policy verdict it received.</PageHeader>

      <div className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Filters">
        <Segmented
          label="Verdict"
          value={outcome ?? 'all'}
          onChange={(v) => setParam('outcome', v === 'all' ? '' : v)}
          options={[{ value: 'all', label: 'All' }, { value: 'allow', label: 'Allowed' }, { value: 'deny', label: 'Denied' }]}
        />
        <Input aria-label="Action" placeholder="Action, e.g. kb.read" className="mono w-44" value={action} onChange={(e) => setParam('action', e.target.value)} />
        <Input aria-label="Request id" placeholder="Request id" className="mono w-56" value={requestId} onChange={(e) => setParam('request_id', e.target.value)} />
        <Input aria-label="Policy version" placeholder="Policy v" inputMode="numeric" className="mono w-24" value={policy} onChange={(e) => setParam('policy_version', e.target.value.replace(/\D/g, ''))} />
        <Select aria-label="Time range" value={since} onChange={(e) => setParam('since', e.target.value)}>
          <option value="">Any time</option>
          <option value="1h">Last hour</option>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
        </Select>
        {active ? <Button variant="ghost" size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</Button> : null}
        <Segmented
          className="ml-auto"
          label="Row density"
          value={density}
          onChange={setDensity}
          options={[{ value: 'compact', label: 'Compact' }, { value: 'comfortable', label: 'Comfortable' }]}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0">
          <DecisionsTable
            items={items}
            isLoading={q.isLoading}
            error={q.error}
            onRetry={() => void q.refetch()}
            selectedId={id}
            search={search}
            density={density}
            filtered={active}
          />
          {q.hasNextPage ? (
            <div className="mt-3">
              <Button variant="secondary" size="sm" disabled={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
                {q.isFetchingNextPage ? 'Loading' : 'Load more'}
              </Button>
            </div>
          ) : null}
        </div>
        <aside aria-label="Decision detail" className="h-fit rounded-sm border border-hairline bg-surface p-4 lg:sticky lg:top-[calc(var(--topbar-height)+16px)]">
          <DecisionPanel id={id} />
        </aside>
      </div>
    </div>
  )
}
