import type { DecisionSummary, ReasonCode } from '@/api/types'
import { stageLabel } from '@/lib/stages'
import { cn, formatTime } from '@/lib/utils'
import { VerdictBadge } from './verdict-badge'

interface TraceTimelineProps {
  steps: DecisionSummary[]
  /** The decision the viewer opened. It is marked in the rail. */
  currentId?: string
  /** The reason catalogue. With it, a denied step shows its plain sentence. */
  reasons?: Record<string, ReasonCode>
}

function stepDurationMs(steps: DecisionSummary[], i: number): number | null {
  const next = steps[i + 1]
  const cur = steps[i]
  if (!next || !cur) return null
  return Math.max(0, new Date(next.created_at).getTime() - new Date(cur.created_at).getTime())
}

/** A vertical rail of the gateway decisions in one request, oldest first. The deny step anchors a denied trace. */
export function TraceTimeline({ steps, currentId, reasons }: TraceTimelineProps) {
  if (steps.length === 0) {
    return <p className="text-footnote text-fg-secondary">No steps were recorded for this request.</p>
  }
  return (
    <ol aria-label="Request trace" className="relative m-0 list-none p-0">
      {steps.map((s, i) => {
        const denied = s.outcome === 'deny'
        const ms = stepDurationMs(steps, i)
        return (
          <li key={s.id} data-outcome={s.outcome} aria-current={s.id === currentId ? 'step' : undefined} className="relative flex gap-3 pb-4 last:pb-0">
            {i < steps.length - 1 ? <span aria-hidden="true" className="absolute left-[7px] top-4 h-[calc(100%-8px)] w-px bg-fg-tertiary opacity-40" /> : null}
            <span
              aria-hidden="true"
              className={cn('relative mt-1 h-[15px] w-[15px] shrink-0 rounded-full border-2 bg-surface', denied ? 'border-deny bg-deny' : 'border-allow')}
            />
            <div className={cn('min-w-0 flex-1 rounded-sm px-2 py-1', denied && 'border-l-2 border-l-deny [background:linear-gradient(var(--deny-tint),var(--deny-tint)),var(--bg-surface)]', s.id === currentId && !denied && 'bg-selected')}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <code className="mono text-footnote font-medium">{s.action}</code>
                {s.resource ? <code className="mono text-footnote text-fg-secondary">{s.resource}</code> : null}
                <VerdictBadge verdict={denied ? 'deny' : 'allow'} reason={s.reason} size="sm" />
              </div>
              <div className="mono mt-0.5 flex flex-wrap gap-x-3 text-footnote text-fg-secondary">
                <span>{formatTime(s.created_at)}</span>
                <span className={denied ? 'font-semibold text-deny' : undefined}>stage {s.stage}</span>
                {ms !== null ? <span>{ms} ms to next</span> : null}
              </div>
              {denied ? (
                <p className="mt-1 text-footnote text-fg" data-testid="trace-deny-sentence">
                  <span className="font-semibold text-deny">{stageLabel(s.stage)}.</span>{' '}
                  {reasons?.[s.reason]?.sentence ?? 'The gateway stopped this call.'}
                </p>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
