import { Link } from 'react-router-dom'
import type { Overview, ReasonCode } from '@/api/types'
import { cn, formatNumber } from '@/lib/utils'
import { formatPercent, requestsHref } from './overview-format'

interface TileProps {
  label: string
  value: string
  hint: string
  to: string
  testId: string
  tone?: 'deny'
}

function Tile({ label, value, hint, to, testId, tone }: TileProps) {
  return (
    <Link
      to={to}
      data-testid={testId}
      aria-label={`${label}: ${value}. ${hint}`}
      className="group flex flex-col gap-1 rounded-sm border border-hairline bg-surface p-4 transition-colors duration-fast hover:bg-muted"
    >
      <span className="eyebrow">{label}</span>
      <span className={cn('tabular text-title-1 font-semibold', tone === 'deny' && 'text-deny')}>{value}</span>
      <span className="text-footnote text-fg-secondary group-hover:text-fg">{hint}</span>
    </Link>
  )
}

/** The four numbers. Each one links to the requests list with the matching filter. Overview counts requests. */
export function OverviewTiles({ overview }: { overview: Overview }) {
  const days = overview.days
  const budgetPct = overview.budget.limit_tokens > 0 ? overview.budget.used_tokens / overview.budget.limit_tokens : 0
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Tile testId="tile-checked" label="Checked" value={formatNumber(overview.checked)} hint="Requests checked. See all." to={requestsHref(days)} />
      <Tile testId="tile-blocked" label="Blocked" value={formatNumber(overview.blocked)} hint="Requests with a deny. See them." to={requestsHref(days, { outcome: 'deny' })} tone={overview.blocked > 0 ? 'deny' : undefined} />
      <Tile testId="tile-deny-rate" label="Deny rate" value={formatPercent(overview.deny_rate)} hint="Blocked out of checked." to={requestsHref(days, { outcome: 'deny' })} />
      <Tile
        testId="tile-budget"
        label="Budget used today"
        value={formatPercent(budgetPct)}
        hint={`${formatNumber(overview.budget.used_tokens)} of ${formatNumber(overview.budget.limit_tokens)} tokens`}
        to="/app/usage"
      />
    </div>
  )
}

/** The reasons behind the blocked requests, with the plain title from the catalogue. */
export function TopDenyReasons({ overview, reasons }: { overview: Overview; reasons?: Record<string, ReasonCode> }) {
  const list = overview.top_deny_reasons
  if (list.length === 0) {
    return <p className="text-callout text-fg-secondary">No request was blocked in this period.</p>
  }
  const max = Math.max(...list.map((r) => r.count))
  return (
    <ul aria-label="Top deny reasons" className="m-0 flex list-none flex-col gap-2 p-0">
      {list.map((r) => {
        const info = reasons?.[r.reason]
        return (
          <li key={r.reason}>
            <Link
              to={requestsHref(overview.days, { outcome: 'deny' })}
              className="block rounded-sm border border-hairline bg-surface p-3 transition-colors duration-fast hover:bg-muted"
            >
              <span className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-callout font-medium">{info?.title ?? r.reason}</span>
                <span className="tabular mono text-callout">{formatNumber(r.count)}</span>
              </span>
              <span className="mt-0.5 block text-footnote text-fg-secondary">{info?.sentence ?? 'The gateway stopped these calls.'}</span>
              <span className="mono mt-1 block text-footnote text-fg-tertiary">{r.reason}</span>
              <span aria-hidden="true" className="mt-2 block h-1 rounded-full bg-muted">
                <span className="block h-1 rounded-full bg-deny" style={{ width: `${Math.max(4, (r.count / max) * 100)}%` }} />
              </span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

/** Requests per day: checked in ink, blocked in the deny colour. A hidden table carries the same numbers. */
export function ByDayBars({ days }: { days: Overview['by_day'] }) {
  const max = Math.max(1, ...days.map((d) => d.checked))
  return (
    <figure className="m-0">
      <div role="img" aria-label={`Requests per day over ${days.length} days, peak ${max}`} className="flex h-28 items-end gap-1">
        {days.map((d) => (
          <div key={d.date} className="flex h-full min-w-0 flex-1 flex-col justify-end" title={`${d.date}: ${d.checked} checked, ${d.blocked} blocked`}>
            <div className="relative w-full rounded-t-[3px] bg-ink opacity-80" style={{ height: `${(d.checked / max) * 100}%` }}>
              {d.blocked > 0 ? <div className="absolute inset-x-0 bottom-0 rounded-t-[3px] bg-deny" style={{ height: `${(d.blocked / d.checked) * 100}%` }} /> : null}
            </div>
          </div>
        ))}
      </div>
      <table className="sr-only">
        <caption>Requests per day</caption>
        <thead><tr><th scope="col">Date</th><th scope="col">Checked</th><th scope="col">Blocked</th></tr></thead>
        <tbody>{days.map((d) => <tr key={d.date}><td>{d.date}</td><td>{d.checked}</td><td>{d.blocked}</td></tr>)}</tbody>
      </table>
      <figcaption className="mt-1 flex items-center justify-between text-footnote text-fg-secondary">
        <span>{days[0]?.date.slice(5)}</span>
        <span className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1"><span aria-hidden="true" className="h-2 w-2 rounded-[2px] bg-ink" />Checked</span>
          <span className="inline-flex items-center gap-1"><span aria-hidden="true" className="h-2 w-2 rounded-[2px] bg-deny" />Blocked</span>
        </span>
        <span>{days[days.length - 1]?.date.slice(5)}</span>
      </figcaption>
    </figure>
  )
}
