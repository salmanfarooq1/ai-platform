import { PageHeader } from '@/components/governance/states'

export default function TrustPage() {
  return (
    <div>
      <PageHeader title="Trust">Evaluation results, cost and tracing will be here.</PageHeader>
      <div className="max-w-prose rounded-md border border-dashed border-hairline p-6 text-callout text-fg-secondary">
        <p>Nothing is measured on this page yet. The trust checks arrive in a later release. Until then, the Decisions explorer holds the record of every governed call.</p>
      </div>
    </div>
  )
}
