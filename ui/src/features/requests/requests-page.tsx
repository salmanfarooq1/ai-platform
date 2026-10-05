import { useInfiniteQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '@/api/endpoints'
import type { Outcome, RequestFilters } from '@/api/types'
import { PageHeader } from '@/components/governance/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { Select } from '@/components/ui/select'
import { useDensity } from '@/lib/density'
import { useReasonCodes } from '@/lib/reasons'
import { sinceToIso } from '@/lib/time-range'
import { RequestDrawer } from './request-drawer'
import { RequestsTable } from './requests-table'

export default function RequestsPage() {
  const { requestId } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [density, setDensity] = useDensity()
  const { byCode } = useReasonCodes()

  const outcome = (params.get('outcome') as Outcome | null) ?? undefined
  const action = params.get('action') ?? ''
  const since = params.get('since') ?? ''
  const policy = params.get('policy_version') ?? ''
  const consoleViews = params.get('console') === '1'

  // `since` becomes a timestamp once per change, so the query key stays stable between renders.
  const sinceIso = useMemo(() => sinceToIso(since), [since])
  const filters: RequestFilters = {
    outcome, action: action || undefined, since: sinceIso,
    policy_version: policy ? Number(policy) : undefined,
    include_console_reads: consoleViews || undefined,
  }
  const active = Boolean(outcome || action || since || policy || consoleViews)

  const q = useInfiniteQuery({
    queryKey: ['requests', filters],
    queryFn: ({ pageParam }) => api.requests(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
  })
  const items = useMemo(() => q.data?.pages.flatMap((p) => p.items), [q.data])

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const search = params.toString() ? `?${params.toString()}` : ''

  return (
    <div>
      <PageHeader title="Requests">Every call to the gateway, grouped by request. Open one to see its checks and why it was allowed or denied.</PageHeader>
      <div className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Filters">
        <Segmented
          label="Outcome"
          value={outcome ?? 'all'}
          onChange={(v) => setParam('outcome', v === 'all' ? '' : v)}
          options={[{ value: 'all', label: 'All' }, { value: 'allow', label: 'Allowed' }, { value: 'deny', label: 'Denied' }]}
        />
        <Input aria-label="Action" placeholder="Action, e.g. kb.read" className="mono w-44" value={action} onChange={(e) => setParam('action', e.target.value)} />
        <Input aria-label="Policy version" placeholder="Policy v" inputMode="numeric" className="mono w-24" value={policy} onChange={(e) => setParam('policy_version', e.target.value.replace(/\D/g, ''))} />
        <Select aria-label="Time range" value={since} onChange={(e) => setParam('since', e.target.value)}>
          <option value="">Any time</option>
          <option value="1h">Last hour</option>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </Select>
        <label className="flex h-9 items-center gap-2 text-footnote text-fg-secondary">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--ink)]"
            checked={consoleViews}
            onChange={(e) => setParam('console', e.target.checked ? '1' : '')}
          />
          Include console views
        </label>
        {active ? <Button variant="ghost" size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</Button> : null}
        <Segmented
          className="ml-auto"
          label="Row density"
          value={density}
          onChange={setDensity}
          options={[{ value: 'compact', label: 'Compact' }, { value: 'comfortable', label: 'Comfortable' }]}
        />
      </div>
      <RequestsTable
        items={items}
        isLoading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        selectedId={requestId}
        search={search}
        density={density}
        filtered={active}
        reasons={byCode}
      />
      {q.hasNextPage ? (
        <div className="mt-3">
          <Button variant="secondary" size="sm" disabled={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
            {q.isFetchingNextPage ? 'Loading' : 'Load more'}
          </Button>
        </div>
      ) : null}
      <RequestDrawer requestId={requestId} onClose={() => navigate(`/app/requests${search}`)} />
    </div>
  )
}
