import { useQuery } from '@tanstack/react-query'
import { useSearchParams, Link } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { EmptyState, ErrorState, PageHeader } from '@/components/governance/states'
import { Segmented } from '@/components/ui/segmented'
import { Skeleton } from '@/components/ui/skeleton'
import { useReasonCodes } from '@/lib/reasons'
import { ByDayBars, OverviewTiles, TopDenyReasons } from './overview-tiles'

const PERIODS = [{ value: '1', label: 'Today' }, { value: '7', label: '7 days' }, { value: '30', label: '30 days' }]

export default function OverviewPage() {
  const [params, setParams] = useSearchParams()
  const days = ['1', '7', '30'].includes(params.get('days') ?? '') ? Number(params.get('days')) : 7
  const q = useQuery({ queryKey: ['overview', days], queryFn: () => api.overview(days), retry: false })
  const { byCode } = useReasonCodes()

  return (
    <div>
      <PageHeader
        title="Overview"
        actions={
          <Segmented
            label="Period"
            value={String(days)}
            onChange={(v) => setParams(v === '7' ? new URLSearchParams() : new URLSearchParams({ days: v }), { replace: true })}
            options={PERIODS}
          />
        }
      >
        What the gateway checked, and what it stopped.
      </PageHeader>
      {q.isLoading ? (
        <div role="status" aria-label="Loading overview" className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
          <Skeleton className="h-40" />
        </div>
      ) : null}
      {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load the overview." /> : null}
      {q.data && q.data.checked === 0 ? (
        <EmptyState
          title="Nothing has been checked in this period."
          action={<Link to="/app/walkthrough" className="text-callout font-medium text-seal underline-offset-2 hover:underline">Open the walkthrough</Link>}
        >
          Every call through the gateway counts here. Run the walkthrough, or ask a question in the workspace, and the numbers appear.
        </EmptyState>
      ) : null}
      {q.data && q.data.checked > 0 ? (
        <div className="flex flex-col gap-6">
          <OverviewTiles overview={q.data} />
          <div className="grid gap-6 lg:grid-cols-2">
            <section aria-labelledby="top-reasons">
              <h2 id="top-reasons" className="mb-2 text-headline">Top deny reasons</h2>
              <TopDenyReasons overview={q.data} reasons={byCode} />
            </section>
            <section aria-labelledby="by-day">
              <h2 id="by-day" className="mb-2 text-headline">Requests per day</h2>
              <div className="rounded-sm border border-hairline bg-surface p-4"><ByDayBars days={q.data.by_day} /></div>
            </section>
          </div>
          <p className="text-footnote text-fg-secondary">Console views, such as this page, are not counted.</p>
        </div>
      ) : null}
    </div>
  )
}
