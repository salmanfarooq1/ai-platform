import {
  Books, ChatCircleText, ClockCounterClockwise, Gauge, Gear, Key, ListChecks, Path, Play, Scroll, ShieldCheck, SquaresFour, Stack,
  type Icon,
} from '@phosphor-icons/react'

export interface NavItem { to: string; label: string; icon: Icon; end?: boolean; module?: string }
export interface NavGroup { group: string; items: NavItem[] }

export const NAV: NavGroup[] = [
  { group: 'Start', items: [
    { to: '/app', label: 'Overview', icon: SquaresFour, end: true },
    { to: '/app/walkthrough', label: 'Walkthrough', icon: Play },
  ] },
  { group: 'Workspace', items: [
    { to: '/app/ask', label: 'Ask', icon: ChatCircleText },
    { to: '/app/library', label: 'Library', icon: Books },
    { to: '/app/history', label: 'History', icon: ClockCounterClockwise },
  ] },
  { group: 'Governance', items: [
    { to: '/app/requests', label: 'Requests', icon: Stack },
    { to: '/app/decisions', label: 'Decisions', icon: Scroll },
    { to: '/app/policies', label: 'Policies', icon: ShieldCheck },
    { to: '/app/keys', label: 'Keys', icon: Key },
    { to: '/app/usage', label: 'Usage', icon: Gauge },
    { to: '/app/runs', label: 'Agent runs', icon: Path, module: 'agents' },
  ] },
  { group: 'Platform', items: [
    { to: '/app/modules', label: 'Modules', icon: Stack },
    { to: '/app/trust', label: 'Trust', icon: ListChecks },
    { to: '/app/system', label: 'System', icon: Gear },
  ] },
]

export function visibleNav(enabled: ReadonlySet<string> | undefined): NavGroup[] {
  return NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.module || enabled?.has(item.module) === true),
  })).filter((group) => group.items.length > 0)
}

export function pageName(pathname: string): string {
  let best: NavItem | undefined
  for (const g of NAV) {
    for (const i of g.items) {
      const hit = i.end ? pathname === i.to : pathname === i.to || pathname.startsWith(`${i.to}/`)
      if (hit && (!best || i.to.length > best.to.length)) best = i
    }
  }
  return best?.label ?? 'App'
}
