import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { DenyCalloutView } from '@/components/governance/deny-callout'
import { Receipt } from '@/components/governance/receipt'
import { TraceTimeline } from '@/components/governance/trace-timeline'
import { buttonVariants } from '@/components/ui/button-variants'
import { EXAMPLE_DENY_SENTENCE, EXAMPLE_POLICY, EXAMPLE_STAGES, exampleReceipt, exampleTrace } from './example-data'
import { MarketingShell } from './marketing-shell'

const RECORD_FIELDS = [
  ['Decision id', 'A unique id for this one check.'],
  ['Request id', 'Groups every check that belongs to one call.'],
  ['Policy version', 'The version of the tenant policy that applied. "default" means no tenant policy was set.'],
  ['Action and resource', 'What was asked, for example reading a knowledge base.'],
  ['Verdict and reason', 'Allow or deny, and the reason code. Each code has a plain sentence.'],
  ['Input SHA-256', 'A hash of the input. The input text itself is not stored.'],
]

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="border-t border-hairline py-12">
      <div className="grid gap-8 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
        <h2 id={id} className="text-title-1">{title}</h2>
        <div className="flex min-w-0 flex-col gap-4 text-body text-fg-secondary">{children}</div>
      </div>
    </section>
  )
}

/** The detail behind the landing page. A static page: no GSAP, no WebGL. */
export default function HowItWorksPage() {
  useEffect(() => { document.title = 'How it works - Governed Agent Platform' }, [])
  return (
    <MarketingShell>
      <div className="mx-auto max-w-[1200px] px-4 pb-16 pt-14 md:px-8 md:pt-20">
        <h1 className="max-w-2xl text-[clamp(1.9rem,3.6vw,2.8rem)] font-semibold leading-tight tracking-[-0.025em]">How a call is checked</h1>
        <p className="mt-4 max-w-2xl text-[1.0625rem] leading-relaxed text-fg-secondary">
          Every model, tool and knowledge base call goes through one gateway. This page shows what the gateway checks, what it writes down, and how to read it. The data on this page is example data.
        </p>

        <div className="mt-12">
          <Section id="stages" title="The checks, in order">
            <p>A call meets the same checks in the same order. The first check that fails stops the call, and that stage is recorded as the one that denied it.</p>
            <ol className="m-0 flex list-none flex-col p-0">
              {EXAMPLE_STAGES.map((s, i) => (
                <li key={s.code} className="grid grid-cols-[28px_minmax(0,1fr)] gap-x-3 border-t border-hairline py-3 first:border-t-0 first:pt-0">
                  <span className="mono tabular text-fg-tertiary">{i + 1}</span>
                  <div>
                    <p className="text-callout font-medium text-fg">{s.name} <code className="mono ml-1 text-footnote font-normal text-fg-secondary">{s.code}</code></p>
                    <p className="text-callout">{s.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Section>

          <Section id="outside" title="Why outside the agent">
            <p>Checks inside agent code can be skipped or changed by that code. A gateway sits outside it, so every call is checked.</p>
            <p>Agent code does not import the model client, and a test checks this. Agent clients that speak MCP use the same gateway.</p>
          </Section>

          <Section id="policy" title="The tenant policy">
            <p>A tenant policy can only narrow access. It lists the knowledge bases, tools and models a tenant may use, and sets limits for tool calls and tokens. It is versioned, and each request is checked against the active version.</p>
            <pre className="mono overflow-x-auto rounded-sm border border-hairline bg-surface p-4 text-footnote leading-relaxed text-fg">{JSON.stringify(EXAMPLE_POLICY, null, 2)}</pre>
            <p>With no tenant policy, scopes grant against the platform defaults.</p>
          </Section>

          <Section id="deny" title="When a call is denied">
            <p>A denied call names the stage that stopped it, gives one plain sentence, and shows the policy field and policy version behind the stop.</p>
            <DenyCalloutView reason="kb_not_allowed" sentence={EXAMPLE_DENY_SENTENCE} policyField="allowed_kbs" stage="policy" policyVersion={3} action="kb.read" resource="payroll" />
            <p>If a check cannot run, or the record cannot be written, the call is denied. With no tenant policy, the scopes on the key decide what is allowed, and a policy can only narrow that.</p>
          </Section>

          <Section id="record" title="The decision record">
            <p>Every call leaves a record, allowed or denied. The platform keeps a hash of the input, not the text.</p>
            <dl className="m-0 grid gap-x-6 gap-y-3 md:grid-cols-[180px_minmax(0,1fr)]">
              {RECORD_FIELDS.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-callout font-medium text-fg">{k}</dt>
                  <dd className="m-0 text-callout">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-hairline bg-surface p-5"><p className="eyebrow mb-2">Example receipt</p><Receipt decision={exampleReceipt} /></div>
              <div className="rounded-xl border border-hairline bg-surface p-5"><p className="eyebrow mb-3">Example request trace</p><TraceTimeline steps={exampleTrace} /></div>
            </div>
          </Section>

          <Section id="isolation" title="Tenants, limits and previews">
            <p>Postgres row-level security separates tenants, so one tenant cannot read another. Each tenant has rate limits and a daily token budget.</p>
            <p>A preview session is read-only. Its API key stays on the server, in a secure cookie session.</p>
          </Section>
        </div>

        <div className="mt-4 flex flex-wrap gap-3 border-t border-hairline pt-10">
          <Link to="/app/walkthrough" className={buttonVariants({ size: 'lg' })}>Open the walkthrough</Link>
          <Link to="/" className={buttonVariants({ size: 'lg', variant: 'secondary' })}>Back to the start</Link>
        </div>
      </div>
    </MarketingShell>
  )
}
