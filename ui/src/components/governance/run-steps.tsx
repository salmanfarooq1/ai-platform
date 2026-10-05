import { FileX, Gauge, Play, Prohibit, Stop, Terminal, WifiSlash, type Icon } from '@phosphor-icons/react'
import type { ReasonCode, RunTimelineItem, SandboxEvent } from '@/api/types'
import { SANDBOX_WORDS, isSandboxDeny, sandboxDetail } from '@/lib/sandbox'
import { stageLabel } from '@/lib/stages'
import { cn, formatTime } from '@/lib/utils'
import { VerdictBadge } from './verdict-badge'

const ICONS: Record<SandboxEvent['kind'], Icon> = {
  start: Play,
  exit: Stop,
  network_denied: WifiSlash,
  file_denied: FileX,
  limit_hit: Gauge,
  log: Terminal,
}

interface RunStepsProps {
  items: RunTimelineItem[]
  /** The reason catalogue. With it, a denied decision shows its plain sentence. */
  reasons?: Record<string, ReasonCode>
}

function toneOf(item: RunTimelineItem): 'deny' | 'warn' | 'plain' | 'allow' {
  if (item.source === 'decision') return item.decision?.outcome === 'deny' ? 'deny' : 'allow'
  const kind = item.sandbox?.kind
  if (kind && isSandboxDeny(kind)) return 'deny'
  return kind === 'limit_hit' ? 'warn' : 'plain'
}

function DecisionStep({ item, reasons }: { item: RunTimelineItem; reasons?: Record<string, ReasonCode> }) {
  const d = item.decision
  if (!d) return null
  const denied = d.outcome === 'deny'
  return (
    <>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-footnote text-fg-secondary">Gateway</span>
        <code className="mono text-footnote font-medium">{d.action}</code>
        {d.resource ? <code className="mono text-footnote text-fg-secondary">{d.resource}</code> : null}
        <VerdictBadge verdict={denied ? 'deny' : 'allow'} reason={d.reason} size="sm" />
      </div>
      <div className="mono mt-0.5 flex flex-wrap gap-x-3 text-footnote text-fg-secondary">
        <span>{formatTime(item.at)}</span>
        <span className={denied ? 'font-semibold text-deny' : undefined}>stage {d.stage}</span>
      </div>
      {denied ? (
        <p className="mt-1 text-footnote text-fg" data-testid="run-step-deny-sentence">
          <span className="font-semibold text-deny">{stageLabel(d.stage)}.</span> {reasons?.[d.reason]?.sentence ?? 'The gateway stopped this call.'}
        </p>
      ) : null}
    </>
  )
}

function SandboxStep({ item }: { item: RunTimelineItem }) {
  const e = item.sandbox
  if (!e) return null
  const Icon = ICONS[e.kind]
  const deny = isSandboxDeny(e.kind)
  return (
    <>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-footnote text-fg-secondary">Sandbox</span>
        <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-footnote font-medium', deny ? 'text-deny [background:linear-gradient(var(--deny-tint),var(--deny-tint)),var(--bg-surface)]' : e.kind === 'limit_hit' ? 'text-warning [background:linear-gradient(var(--warning-tint),var(--warning-tint)),var(--bg-surface)]' : 'text-fg')}>
          <Icon size={14} weight="bold" aria-hidden />
          <span data-testid="sandbox-kind-word">{SANDBOX_WORDS[e.kind]}</span>
        </span>
        {deny ? <span className="inline-flex items-center gap-1 text-footnote font-medium text-deny"><Prohibit size={14} weight="bold" aria-hidden /> Denied</span> : null}
      </div>
      <div className="mono mt-0.5 flex flex-wrap gap-x-3 text-footnote text-fg-secondary">
        <span>{formatTime(item.at)}</span>
        <code className="mono">{e.kind}</code>
      </div>
      <p className={cn('mt-1 text-footnote', deny ? 'text-fg' : 'text-fg-secondary')} data-testid="sandbox-detail">{sandboxDetail(e)}</p>
    </>
  )
}

/** The steps of one sandboxed run, oldest first: the gateway's decisions and the sandbox's own events in one rail.
 * A network or file denial from the sandbox has the same deny emphasis as a gateway deny: red bar, an icon, a word. */
export function RunSteps({ items, reasons }: RunStepsProps) {
  if (items.length === 0) return <p className="text-footnote text-fg-secondary">No steps were recorded for this run.</p>
  return (
    <ol aria-label="Run steps" className="relative m-0 list-none p-0">
      {items.map((item, i) => {
        const tone = toneOf(item)
        const key = item.source === 'decision' ? `d-${item.decision?.id}` : `s-${item.sandbox?.id}`
        return (
          <li key={key} data-source={item.source} data-tone={tone} data-kind={item.sandbox?.kind} className="relative flex gap-3 pb-4 last:pb-0">
            {i < items.length - 1 ? <span aria-hidden="true" className="absolute left-[7px] top-4 h-[calc(100%-8px)] w-px bg-fg-tertiary opacity-40" /> : null}
            <span
              aria-hidden="true"
              className={cn(
                'relative mt-1 h-[15px] w-[15px] shrink-0 border-2 bg-surface',
                item.source === 'sandbox' ? 'rounded-[3px]' : 'rounded-full',
                tone === 'deny' ? 'border-deny bg-deny' : tone === 'warn' ? 'border-warning' : tone === 'plain' ? 'border-fg-tertiary' : 'border-allow',
              )}
            />
            <div className={cn('min-w-0 flex-1 rounded-sm px-2 py-1', tone === 'deny' && 'border-l-2 border-l-deny [background:linear-gradient(var(--deny-tint),var(--deny-tint)),var(--bg-surface)]')}>
              {item.source === 'decision' ? <DecisionStep item={item} reasons={reasons} /> : <SandboxStep item={item} />}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
