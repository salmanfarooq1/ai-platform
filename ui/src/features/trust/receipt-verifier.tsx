import { CheckCircle, XCircle } from '@phosphor-icons/react'
import { useMutation } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/endpoints'
import type { Receipt, VerifyResult } from '@/api/types'
import { CopyValue } from '@/components/governance/copy-value'
import { ErrorState } from '@/components/governance/states'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface Outcome {
  receipt: Receipt | null
  result: VerifyResult
}

/** The checks, in plain words. The server's detail sentence says what was found. */
const CHECK_TITLES: Record<string, string> = {
  alg: 'Algorithm',
  key: 'Signing key',
  canonical: 'Signed text',
  signature: 'Signature',
  row_hash: 'Chain hash',
}

function CheckRow({ name, ok, detail }: { name: string; ok: boolean; detail: string }) {
  const Icon = ok ? CheckCircle : XCircle
  return (
    <li className="grid grid-cols-[96px_minmax(0,1fr)] gap-x-3 gap-y-0.5 border-t border-hairline py-2 first:border-t-0 sm:grid-cols-[140px_96px_minmax(0,1fr)]">
      <span className="text-callout font-medium">{CHECK_TITLES[name] ?? name}</span>
      <span className={cn('inline-flex items-center gap-1 text-callout font-medium', ok ? 'text-allow' : 'text-deny')}>
        <Icon size={16} weight="bold" aria-hidden="true" />
        {ok ? 'Passed' : 'Failed'}
      </span>
      <span className="col-span-2 text-footnote text-fg-secondary sm:col-span-1">{detail}</span>
    </li>
  )
}

interface SignedText {
  decision?: Record<string, string | number | null>
  chain?: { position?: number; prev_hash?: string; row_hash?: string }
}

/** The fields the signature covers, read from the signed text itself, never from the loose `decision` object. */
function signedFields(canonical: string): SignedText | null {
  try {
    const value: unknown = JSON.parse(canonical)
    return typeof value === 'object' && value !== null ? (value as SignedText) : null
  } catch {
    return null
  }
}

const SIGNED_ROWS: Array<[string, string]> = [
  ['id', 'Decision id'], ['request_id', 'Request id'], ['action', 'Action'], ['resource', 'Resource'], ['outcome', 'Outcome'],
  ['stage', 'Stage'], ['reason', 'Reason'], ['policy_version', 'Policy version'], ['input_sha256', 'Input SHA-256'],
  ['created_at', 'Recorded'],
]

/** The outcome of one verification. Only a valid receipt has a "Verified" list, and it shows the signed text's own
 * values. Names, the tenant label and the trace are context: the signature does not cover them. */
export function VerificationResult({ outcome }: { outcome: Outcome }) {
  const { receipt, result } = outcome
  const Icon = result.valid ? CheckCircle : XCircle
  const signed = result.valid && receipt ? signedFields(receipt.canonical) : null
  return (
    <section aria-label="Verification result" data-testid="receipt-result" data-valid={result.valid ? 'true' : 'false'} className="flex flex-col gap-4">
      <div
        className={cn(
          'flex flex-wrap items-center gap-2 rounded-md px-3 py-2',
          result.valid
            ? 'text-allow [background:linear-gradient(var(--allow-tint),var(--allow-tint)),var(--bg-surface)]'
            : 'text-deny [background:linear-gradient(var(--deny-tint),var(--deny-tint)),var(--bg-surface)]',
        )}
      >
        <Icon size={20} weight="bold" aria-hidden="true" />
        <h3 className="m-0 text-headline font-semibold">{result.valid ? 'Valid' : 'Invalid'}</h3>
        <p className="m-0 text-callout">
          {result.valid ? 'The signature and the chain hash match. Only the fields under Verified are covered.' : 'Do not rely on this receipt. Fetch it again from the platform.'}
        </p>
      </div>
      <ul aria-label="Checks" className="m-0 list-none rounded-md border border-hairline bg-surface px-3 py-0">
        {result.checks.map((c) => <CheckRow key={c.name} name={c.name} ok={c.ok} detail={c.detail} />)}
      </ul>
      {signed ? (
        <section aria-label="Verified" data-testid="verified-fields">
          <h4 className="mb-2 text-callout font-semibold">Verified</h4>
          <dl className="grid grid-cols-[120px_minmax(0,1fr)] gap-x-3 gap-y-2 text-footnote">
            {SIGNED_ROWS.filter(([k]) => signed.decision && signed.decision[k] !== undefined && signed.decision[k] !== null).map(([k, label]) => (
              <div key={k} className="contents"><dt className="text-fg-secondary">{label}</dt><dd><CopyValue value={String(signed.decision?.[k])} label={label.toLowerCase()} /></dd></div>
            ))}
            <dt className="text-fg-secondary">Chain position</dt>
            <dd data-testid="chain-position" className="mono tabular">{signed.chain?.position}</dd>
            <dt className="text-fg-secondary">Row hash</dt>
            <dd>{signed.chain?.row_hash ? <CopyValue value={signed.chain.row_hash} label="row hash" /> : null}</dd>
            <dt className="text-fg-secondary">Previous hash</dt>
            <dd>{signed.chain?.prev_hash ? <CopyValue value={signed.chain.prev_hash} label="previous hash" /> : null}</dd>
            <dt className="text-fg-secondary">Key id</dt>
            <dd>{receipt ? <CopyValue value={receipt.key_id} label="key id" /> : null}</dd>
          </dl>
        </section>
      ) : null}
      {receipt ? (
        <section aria-label="Context, not signed" data-testid="context-fields">
          <h4 className="mb-2 text-callout font-semibold">Context, not signed</h4>
          <p className="mb-2 text-footnote text-fg-secondary">These come with the receipt but the signature does not cover them. They may differ from what the platform holds.</p>
          <dl className="grid grid-cols-[120px_minmax(0,1fr)] gap-x-3 gap-y-2 text-footnote">
            <dt className="text-fg-secondary">Principal name</dt><dd>{receipt.decision.principal?.name ?? 'none'}</dd>
            <dt className="text-fg-secondary">Tenant label</dt><dd>{receipt.decision.tenant.slug}</dd>
            <dt className="text-fg-secondary">Decision</dt>
            <dd className="flex flex-wrap items-center gap-2">
              <Link to={`/app/decisions/${encodeURIComponent(receipt.decision.id)}`} className="mono text-seal underline-offset-2 hover:underline">{receipt.decision.id}</Link>
              {result.valid ? null : <VerdictBadge verdict={receipt.decision.outcome === 'deny' ? 'deny' : 'allow'} reason={receipt.decision.reason} size="sm" />}
            </dd>
          </dl>
        </section>
      ) : null}
    </section>
  )
}

function parseReceipt(text: string): { ok: true; value: unknown } | { ok: false } {
  try {
    const value: unknown = JSON.parse(text)
    return typeof value === 'object' && value !== null && !Array.isArray(value) ? { ok: true, value } : { ok: false }
  } catch {
    return { ok: false }
  }
}

/** Paste a decision id, fetch its signed receipt, and have the platform check it. Or paste a receipt you hold. */
export function ReceiptVerifier({ initialId }: { initialId?: string }) {
  const [id, setId] = useState(initialId ?? '')
  const [pasted, setPasted] = useState('')
  const [pasteError, setPasteError] = useState<string | null>(null)

  const byId = useMutation<Outcome, Error, string>({
    mutationFn: async (decisionId) => {
      const receipt = await api.receipt(decisionId)
      return { receipt, result: await api.verifyReceipt(receipt) }
    },
  })
  const byPaste = useMutation<Outcome, Error, unknown>({
    mutationFn: async (body) => {
      const result = await api.verifyReceipt(body)
      const receipt = body as Partial<Receipt>
      return { receipt: receipt.chain && receipt.decision ? (body as Receipt) : null, result }
    },
  })

  // A link from a decision opens this page with the id in the address. Run it once, as if the person pressed the button.
  const started = useRef(false)
  useEffect(() => {
    if (initialId && !started.current) {
      started.current = true
      byId.mutate(initialId)
    }
  }, [initialId, byId])

  function submitId(e: FormEvent) {
    e.preventDefault()
    const wanted = id.trim()
    if (wanted) { byPaste.reset(); byId.mutate(wanted) }
  }
  function submitPaste(e: FormEvent) {
    e.preventDefault()
    const parsed = parseReceipt(pasted)
    if (!parsed.ok) { setPasteError('That is not a receipt. Paste the JSON that GET /v1/receipts/{id} returns.'); return }
    setPasteError(null)
    byId.reset()
    byPaste.mutate(parsed.value)
  }

  const active = byPaste.isSuccess || byPaste.isPending || byPaste.isError ? byPaste : byId
  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={submitId} className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-[260px] flex-1 flex-col gap-1">
          <label htmlFor="receipt-decision-id" className="text-footnote font-medium">Decision id</label>
          <Input id="receipt-decision-id" className="mono" value={id} onChange={(e) => setId(e.target.value)} placeholder="Paste a decision id" autoComplete="off" spellCheck={false} />
        </div>
        <Button type="submit" disabled={!id.trim() || byId.isPending}>{byId.isPending ? 'Verifying' : 'Verify receipt'}</Button>
      </form>
      <details className="rounded-md border border-hairline bg-surface px-3 py-2">
        <summary className="cursor-pointer text-callout font-medium">Check a receipt you already hold</summary>
        <form onSubmit={submitPaste} className="mt-3 flex flex-col items-start gap-2">
          <label htmlFor="receipt-json" className="text-footnote font-medium">Receipt (JSON)</label>
          <Textarea id="receipt-json" className="mono min-h-[140px] text-footnote" value={pasted} onChange={(e) => setPasted(e.target.value)} spellCheck={false} aria-describedby={pasteError ? 'receipt-json-error' : undefined} aria-invalid={pasteError ? true : undefined} />
          {pasteError ? <p id="receipt-json-error" role="alert" className="text-footnote text-deny">{pasteError}</p> : null}
          <Button type="submit" variant="secondary" disabled={!pasted.trim() || byPaste.isPending}>Verify pasted receipt</Button>
        </form>
      </details>
      {active.isPending ? <p role="status" className="text-callout text-fg-secondary">Checking the receipt.</p> : null}
      {active.isError ? <ErrorState error={active.error} title="Could not verify this receipt." /> : null}
      {active.data ? <VerificationResult outcome={active.data} /> : null}
    </div>
  )
}
