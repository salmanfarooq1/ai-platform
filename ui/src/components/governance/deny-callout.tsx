import { Prohibit } from '@phosphor-icons/react'
import { useDenyReason } from '@/lib/reasons'
import { stageLabel } from '@/lib/stages'
import { cn } from '@/lib/utils'

interface DenyCalloutViewProps {
  reason: string
  /** The plain sentence for the reason. */
  sentence: string
  /** The policy document key behind the deny, or null. */
  policyField: string | null
  /** The stage on the decision row. It is the source of truth, not the catalogue. */
  stage: string
  policyVersion: number | null
  action?: string
  resource?: string | null
  className?: string
}

type DenyCalloutProps = Omit<DenyCalloutViewProps, 'sentence' | 'policyField'>

/**
 * Deny is the loudest state. It names the failing stage in red, says in a plain sentence why, and shows the policy
 * field and the policy version behind the stop. The verdict is never colour alone: icon, word and colour together.
 */
export function DenyCalloutView({ reason, sentence, policyField, stage, policyVersion, action, resource, className }: DenyCalloutViewProps) {
  return (
    <section
      aria-label="Why this was denied"
      data-testid="deny-callout"
      className={cn('flex flex-col gap-2 rounded-sm border border-hairline border-l-4 border-l-deny p-4 [background:linear-gradient(var(--deny-tint),var(--deny-tint)),var(--bg-surface)]', className)}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-deny">
        <Prohibit size={18} weight="bold" aria-hidden="true" />
        <p className="text-headline font-semibold" data-testid="deny-stage">
          Denied at {stageLabel(stage)}
        </p>
        <code className="mono text-footnote">{stage}</code>
      </div>
      <p className="text-body text-fg" data-testid="deny-sentence">{sentence}</p>
      {action ? (
        <p className="text-footnote text-fg-secondary">
          <code className="mono">{action}</code>{resource ? <> on <code className="mono">{resource}</code></> : null}
        </p>
      ) : null}
      <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-1 text-footnote">
        <dt className="text-fg-secondary">Reason code</dt>
        <dd><code className="mono">{reason}</code></dd>
        <dt className="text-fg-secondary">Policy field</dt>
        <dd data-testid="deny-policy-field">
          {policyField ? <code className="mono">{policyField}</code> : <span className="text-fg-secondary">none. No policy key is behind this stop.</span>}
        </dd>
        <dt className="text-fg-secondary">Policy version</dt>
        <dd data-testid="deny-policy-version">
          {policyVersion !== null ? <code className="mono">{policyVersion}</code> : <span className="text-fg-secondary">platform default</span>}
        </dd>
      </dl>
    </section>
  )
}

/** The same callout, with the sentence and policy field read from the reason catalogue. */
export function DenyCallout(props: DenyCalloutProps) {
  const view = useDenyReason(props.reason, props.policyVersion)
  return <DenyCalloutView {...props} sentence={view.sentence} policyField={view.policyField} />
}
