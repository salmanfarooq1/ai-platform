import type { UsageSummary } from '@/api/types'

/** A bar chart of requests per day. Bars use the brand token. A visually hidden table carries the same numbers. */
export function DayChart({ days }: { days: UsageSummary['by_day'] }) {
  const W = 640
  const H = 160
  const pad = { l: 36, r: 8, t: 8, b: 24 }
  const max = Math.max(1, ...days.map((d) => d.requests))
  const bw = days.length > 0 ? (W - pad.l - pad.r) / days.length : 0
  const ticks = [0, Math.round(max / 2), max]
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Requests per day over ${days.length} days, peak ${max}`} className="h-auto w-full">
        {ticks.map((t) => {
          const y = pad.t + (H - pad.t - pad.b) * (1 - t / max)
          return (
            <g key={t}>
              <line x1={pad.l} x2={W - pad.r} y1={y} y2={y} stroke="var(--hairline)" />
              <text x={pad.l - 6} y={y + 4} textAnchor="end" fontSize="11" fill="var(--text-secondary)" className="tabular">{t}</text>
            </g>
          )
        })}
        {days.map((d, i) => {
          const h = (H - pad.t - pad.b) * (d.requests / max)
          const x = pad.l + i * bw + bw * 0.15
          return (
            <g key={d.date}>
              <rect x={x} y={H - pad.b - h} width={bw * 0.7} height={h} rx="3" fill="var(--brand)">
                <title>{`${d.date}: ${d.requests} requests`}</title>
              </rect>
              {days.length <= 14 || i % Math.ceil(days.length / 10) === 0 ? (
                <text x={x + bw * 0.35} y={H - 8} textAnchor="middle" fontSize="10" fill="var(--text-secondary)">{d.date.slice(5)}</text>
              ) : null}
            </g>
          )
        })}
      </svg>
      <table className="sr-only">
        <caption>Requests per day</caption>
        <thead><tr><th scope="col">Date</th><th scope="col">Requests</th><th scope="col">Tokens</th></tr></thead>
        <tbody>{days.map((d) => <tr key={d.date}><td>{d.date}</td><td>{d.requests}</td><td>{d.tokens}</td></tr>)}</tbody>
      </table>
    </figure>
  )
}
