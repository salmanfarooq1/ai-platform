import { CheckCircle, XCircle } from '@phosphor-icons/react'
import type { EvalGate } from '@/api/types'
import { EmptyState } from '@/components/governance/states'
import { cn, formatTime } from '@/lib/utils'

const METRIC_TITLES: Record<string, string> = {
  retrieval_hit: 'Retrieval hit',
  answer_fact: 'Answer fact',
  citation_ok: 'Citation',
}
const title = (m: string) => METRIC_TITLES[m] ?? m
const score = (n: number | undefined) => (n === undefined ? 'none' : n.toFixed(4))

function Status({ status }: { status: EvalGate['status'] }) {
  const passed = status === 'passed'
  const Icon = passed ? CheckCircle : XCircle
  return (
    <span data-status={status} className={cn('inline-flex items-center gap-1 font-medium', passed ? 'text-allow' : 'text-deny')}>
      <Icon size={16} weight="bold" aria-hidden="true" />
      {passed ? 'Passed' : 'Failed'}
    </span>
  )
}

/** The latest run of the eval gate with its scores against the baseline, and the history of earlier runs. */
export function EvalGateCard({ latest, history }: { latest: EvalGate | null; history: EvalGate[] }) {
  if (!latest) {
    return (
      <EmptyState title="No eval gate run has been recorded yet.">
        CI runs <code className="mono">scripts/eval/run_gate.py</code> on every change. Run it with <code className="mono">--record</code> to add a row here.
      </EmptyState>
    )
  }
  const metrics = Object.keys(latest.baseline)
  return (
    <div className="flex flex-col gap-4">
      <p className="m-0 text-callout" data-testid="eval-latest">
        Latest run <Status status={latest.status} /> <span className="text-fg-secondary">at {formatTime(latest.run_at)}</span>
      </p>
      <div className="overflow-x-auto">
        <table aria-label="Latest eval scores" className="w-full min-w-[420px] text-callout">
          <thead>
            <tr className="text-left text-footnote text-fg-secondary">
              <th scope="col" className="py-1 pr-3 font-medium">Metric</th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">Latest</th>
              <th scope="col" className="py-1 text-right font-medium">Baseline</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m} className="border-t border-hairline">
                <th scope="row" className="py-1.5 pr-3 text-left font-normal">{title(m)}</th>
                <td className="mono tabular py-1.5 pr-3 text-right">{score(latest.latest[m])}</td>
                <td className="mono tabular py-1.5 text-right text-fg-secondary">{score(latest.baseline[m])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="overflow-x-auto">
        <table aria-label="Eval gate history" className="w-full min-w-[420px] text-callout">
          <thead>
            <tr className="text-left text-footnote text-fg-secondary">
              <th scope="col" className="py-1 pr-3 font-medium">Run</th>
              <th scope="col" className="py-1 pr-3 font-medium">Result</th>
              <th scope="col" className="py-1 font-medium">Scores</th>
            </tr>
          </thead>
          <tbody>
            {history.map((run, i) => (
              <tr key={`${run.run_at}-${i}`} className="border-t border-hairline">
                <td className="mono py-1.5 pr-3">{formatTime(run.run_at)}</td>
                <td className="py-1.5 pr-3"><Status status={run.status} /></td>
                <td className="mono py-1.5 text-footnote text-fg-secondary">{Object.keys(run.baseline).map((m) => `${title(m)} ${score(run.latest[m])}`).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
