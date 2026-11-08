import type { RequestSummary } from '@/api/types'
import { formatTime } from '@/lib/utils'
import { NAV } from './nav'

export interface PaletteItem {
  id: string
  group: 'Go to' | 'Requests'
  label: string
  hint?: string
  to: string
}

const SCREENS: PaletteItem[] = NAV.flatMap((g) => g.items.map((i) => ({ id: `screen:${i.to}`, group: 'Go to' as const, label: i.label, hint: g.group, to: i.to })))

/** A request id looks like one token of letters, digits and a few separators. */
export function looksLikeRequestId(q: string): boolean {
  return /^[A-Za-z0-9_.:-]{4,}$/.test(q)
}

/** The list for the palette: screens that match the text, recent requests that match, and the typed id. */
export function buildPaletteItems(query: string, recent: RequestSummary[] = [], enabledModules?: ReadonlySet<string>): PaletteItem[] {
  const q = query.trim()
  const needle = q.toLowerCase()
  const screens = SCREENS.filter((s) => {
    const nav = NAV.flatMap((group) => group.items).find((item) => item.to === s.to)
    return (!nav?.module || enabledModules?.has(nav.module) === true) && (!needle || s.label.toLowerCase().includes(needle))
  })
  const requests: PaletteItem[] = recent
    .filter((r) => needle && r.request_id.toLowerCase().includes(needle))
    .slice(0, 6)
    .map((r) => ({ id: `request:${r.request_id}`, group: 'Requests' as const, label: r.request_id, hint: `${r.outcome === 'deny' ? 'Denied' : 'Allowed'} · ${formatTime(r.started_at)}`, to: `/app/requests/${encodeURIComponent(r.request_id)}` }))
  const typed: PaletteItem[] = looksLikeRequestId(q) && !requests.some((r) => r.label === q)
    ? [{ id: `request:${q}`, group: 'Requests', label: `Open request ${q}`, hint: 'Find by request id', to: `/app/requests/${encodeURIComponent(q)}` }]
    : []
  // A screen that matches the text comes before the typed id, so typing "system" goes to System.
  return [...requests, ...screens, ...typed]
}

