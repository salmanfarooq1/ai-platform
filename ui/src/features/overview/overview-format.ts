import { daysToPreset } from '@/lib/time-range'

export function requestsHref(days: number, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams(extra)
  const since = daysToPreset(days)
  if (since) params.set('since', since)
  const qs = params.toString()
  return qs ? `/app/requests?${qs}` : '/app/requests'
}

export function formatPercent(rate: number): string {
  const pct = rate * 100
  return `${pct >= 10 || pct === 0 ? Math.round(pct) : pct.toFixed(1)}%`
}

