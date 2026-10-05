import { useState } from 'react'
import { Link } from 'react-router-dom'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { EmptyState, PageHeader } from '@/components/governance/states'
import { Button } from '@/components/ui/button'
import { formatTime } from '@/lib/utils'
import { clearHistory, readHistory } from './history-store'

export default function HistoryPage() {
  const [items, setItems] = useState(readHistory)
  return (
    <div>
      <PageHeader
        title="History"
        actions={items.length > 0 ? <Button variant="secondary" size="sm" onClick={() => { clearHistory(); setItems([]) }}>Clear history</Button> : undefined}
      >
        Questions asked in this browser. Each one links to its decision trace.
      </PageHeader>
      {items.length === 0 ? (
        <EmptyState title="No questions yet." action={<Button asChild size="sm"><Link to="/app/ask">Ask a question</Link></Button>}>
          Questions you ask appear here, with the verdict each one received. The list stays in this browser and is not sent anywhere.
        </EmptyState>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {items.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 rounded-md border border-hairline bg-surface p-3">
              <VerdictBadge verdict={r.verdict} reason={r.reason} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-callout text-fg">{r.question}</p>
                <p className="mono text-footnote text-fg-secondary">{formatTime(r.at)} {r.mode} {r.kb}</p>
              </div>
              {r.requestId ? (
                <Link className="text-callout text-brand underline-offset-2 hover:underline" to={`/app/decisions?request_id=${encodeURIComponent(r.requestId)}`}>
                  Open trace
                </Link>
              ) : <span className="text-footnote text-fg-tertiary">No trace id</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
