import { CheckCircle, Hand, Prohibit, WarningCircle } from '@phosphor-icons/react'
import type { Verdict } from '@/api/types'
import { cn } from '@/lib/utils'

const META: Record<Verdict, { word: string; icon: typeof CheckCircle; cls: string }> = {
  allow: { word: 'Allowed', icon: CheckCircle, cls: 'text-allow [background:linear-gradient(var(--allow-tint),var(--allow-tint)),var(--bg-surface)]' },
  deny: { word: 'Denied', icon: Prohibit, cls: 'text-deny [background:linear-gradient(var(--deny-tint),var(--deny-tint)),var(--bg-surface)]' },
  escalate: { word: 'Needs approval', icon: Hand, cls: 'text-escalate [background:linear-gradient(var(--escalate-tint),var(--escalate-tint)),var(--bg-surface)]' },
  unrecorded: { word: 'Not recorded', icon: WarningCircle, cls: 'text-warning [background:linear-gradient(var(--warning-tint),var(--warning-tint)),var(--bg-surface)]' },
}

interface VerdictBadgeProps {
  verdict: Verdict
  /** Reason code, shown in mono next to a denial. */
  reason?: string | null
  size?: 'sm' | 'md'
  className?: string
}

/** The tint is painted over the surface color, not over whatever is behind the badge, so the contrast holds in selected rows.
 * A verdict always shows an icon, a word and a color together. A denial adds its reason code. */
export function VerdictBadge({ verdict, reason, size = 'md', className }: VerdictBadgeProps) {
  const meta = META[verdict]
  const Icon = meta.icon
  return (
    <span
      data-verdict={verdict}
      className={cn('inline-flex items-center gap-1.5 rounded-full font-medium', size === 'sm' ? 'px-2 py-0.5 text-footnote' : 'px-2.5 py-1 text-callout', meta.cls, className)}
    >
      <Icon size={size === 'sm' ? 14 : 16} weight="bold" aria-hidden="true" />
      <span>{meta.word}</span>
      {verdict === 'deny' && reason ? <code className="mono font-normal">{reason}</code> : null}
    </span>
  )
}
