import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { ErrorState, PageHeader, TableSkeleton } from '@/components/governance/states'
import { EvalGateCard } from './eval-gate-card'
import { ReceiptVerifier } from './receipt-verifier'
import { RetentionCard } from './retention-card'

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h2 id={id} className="text-title-2">{title}</h2>
      {children}
    </section>
  )
}

export default function TrustPage() {
  const [params] = useSearchParams()
  const summary = useQuery({ queryKey: ['trust-summary'], queryFn: api.trustSummary, retry: false })
  const s = summary.data
  return (
    <div className="flex max-w-4xl flex-col gap-8">
      <PageHeader title="Trust">Check a signed receipt, see how long decision records are kept, and see whether the eval gate holds.</PageHeader>

      <Section id="trust-receipts" title="Verify a receipt">
        <p className="max-w-prose text-callout text-fg-secondary">
          Every decision can be signed. Paste a decision id to fetch its receipt and check the signature and the chain hash. The same check runs offline with <code className="mono">scripts/verify/receipt.py</code>.
        </p>
        <ReceiptVerifier initialId={params.get('decision') ?? undefined} />
      </Section>

      <Section id="trust-retention" title="Retention">
        {summary.isLoading ? <TableSkeleton rows={3} cols={2} /> : null}
        {summary.error ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} title="Could not load the trust summary." /> : null}
        {s ? <RetentionCard summary={s} /> : null}
      </Section>

      <Section id="trust-eval" title="Eval gate">
        {summary.isLoading ? <TableSkeleton rows={3} cols={3} /> : null}
        {s ? <EvalGateCard latest={s.eval_gate} history={s.eval_history} /> : null}
      </Section>

      <Section id="trust-metrics" title="Metrics">
        {s ? (
          <div className="flex flex-col gap-2 text-callout">
            {s.grafana_url ? (
              <p className="m-0"><a href={s.grafana_url} target="_blank" rel="noreferrer" className="text-seal underline-offset-2 hover:underline">Open the dashboard in Grafana</a></p>
            ) : (
              <p className="m-0 max-w-prose text-fg-secondary">Grafana is not linked. Start the <code className="mono">observability</code> profile with <code className="mono">docker compose --profile observability up -d</code> and set <code className="mono">GRAFANA_URL</code>.</p>
            )}
            <p className="m-0 max-w-prose text-footnote text-fg-secondary">
              The API serves Prometheus metrics at <code className="mono">/metrics</code>. {s.metrics_public ? 'The endpoint is open in this mode.' : 'The endpoint needs a key with the admin scope in this mode.'}
            </p>
          </div>
        ) : null}
      </Section>
    </div>
  )
}
