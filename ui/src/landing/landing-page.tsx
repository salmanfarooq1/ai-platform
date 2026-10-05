import { ArrowRight } from '@phosphor-icons/react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { DenyCalloutView } from '@/components/governance/deny-callout'
import { Receipt } from '@/components/governance/receipt'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { buttonVariants } from '@/components/ui/button-variants'
import { cn } from '@/lib/utils'
import { CAPABILITIES, HEADLINE, SUBLINE, USE_CASES, WHY_OUTSIDE } from './claims'
import { EXAMPLE_DENY_SENTENCE, exampleReceipt } from './example-data'
import { loadGsap } from './gsap-loader'
import { HeroVisual } from './hero-visual'
import { MarketingShell } from './marketing-shell'
import { ScrollStory } from './scroll-story'
import { useReducedMotion } from './use-reduced-motion'

export default function LandingPage() {
  const reduced = useReducedMotion()
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => { document.title = 'Governed Agent Platform' }, [])

  // Text reveals for section headings. With reduced motion nothing is animated and the text is shown as it is.
  useEffect(() => {
    if (reduced || !root.current) return
    let revert: (() => void) | undefined
    let cancelled = false
    const rootEl = root.current
    void loadGsap().then(({ gsap, SplitText }) => {
      if (cancelled) return
      const ctx = gsap.context(() => {
        gsap.utils.toArray<HTMLElement>('[data-reveal]', rootEl).forEach((el) => {
          const split = SplitText.create(el, { type: 'lines', mask: 'lines', autoSplit: true })
          gsap.from(split.lines, { yPercent: 105, opacity: 0, duration: 0.7, ease: 'power3.out', stagger: 0.08, scrollTrigger: { trigger: el, start: 'top 88%', once: true } })
        })
      }, rootEl)
      revert = () => ctx.revert()
    })
    return () => { cancelled = true; revert?.() }
  }, [reduced])

  return (
    <MarketingShell>
      <div ref={root}>
        <section className="relative isolate overflow-hidden" aria-labelledby="hero-title">
          <HeroVisual />
          <div className="relative mx-auto grid max-w-[1200px] items-center gap-10 px-4 pb-16 pt-14 md:grid-cols-[1.05fr_1fr] md:px-8 md:pb-24 md:pt-24">
            <div>
              <h1 id="hero-title" className="text-[length:var(--text-display)] font-semibold leading-[var(--leading-display)] tracking-[var(--tracking-display)]">
                {HEADLINE}
              </h1>
              <p className="mt-5 max-w-xl text-[1.0625rem] leading-relaxed text-fg-secondary">{SUBLINE}</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/app/walkthrough" className={cn(buttonVariants({ size: 'lg' }))}>Open the walkthrough <ArrowRight size={18} aria-hidden="true" /></Link>
                <Link to="/how-it-works" className={cn(buttonVariants({ size: 'lg', variant: 'secondary' }))}>How it works</Link>
              </div>
            </div>
            <div className="flex flex-col gap-3" data-testid="hero-examples">
              <p className="eyebrow">Example data, from the real console components</p>
              <div className="flex flex-col gap-3 rounded-xl border border-hairline bg-surface p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <VerdictBadge verdict="allow" />
                  <span className="text-callout text-fg-secondary">A decision record is written</span>
                </div>
                <Receipt decision={exampleReceipt} compact />
              </div>
              <DenyCalloutView
                className="rounded-xl"
                reason="kb_not_allowed"
                sentence={EXAMPLE_DENY_SENTENCE}
                policyField="allowed_kbs"
                stage="policy"
                policyVersion={3}
                action="kb.read"
                resource="payroll"
              />
            </div>
          </div>
        </section>

        <section id="use-cases" aria-labelledby="use-title" className="mx-auto max-w-[1200px] scroll-mt-20 px-4 py-16 md:px-8">
          <h2 id="use-title" className="eyebrow mb-4">Where it is used</h2>
          <ul className="m-0 flex list-none flex-col p-0">
            {USE_CASES.map((u) => (
              <li key={u.title} className="grid gap-1 border-t border-hairline py-5 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:gap-10">
                <h3 className="text-title-2">{u.title}</h3>
                <p className="max-w-prose text-body text-fg-secondary">{u.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="outside-title" className="mx-auto max-w-[1200px] px-4 pb-16 md:px-8">
          <div className="rounded-xl border border-hairline bg-surface p-8 md:p-12">
            <h2 id="outside-title" className="max-w-xl text-[clamp(1.5rem,2.6vw,2.1rem)] font-semibold leading-tight tracking-[-0.02em]">{WHY_OUTSIDE.title}</h2>
            <p className="mt-3 max-w-xl text-body text-fg-secondary">{WHY_OUTSIDE.body}</p>
            <Link to="/how-it-works" className="mt-5 inline-flex items-center gap-1 text-callout font-medium text-seal underline-offset-2 hover:underline">
              See how a call is checked <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
        </section>

        <ScrollStory />

        <section id="capabilities" aria-labelledby="cap-title" className="mx-auto max-w-[1200px] scroll-mt-20 px-4 py-20 md:px-8 md:py-28">
          <div className="grid gap-10 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <div className="md:sticky md:top-24 md:self-start">
              <h2 id="cap-title" data-reveal className="text-[clamp(1.6rem,3vw,2.4rem)] font-semibold leading-tight tracking-[-0.02em]">What the platform does</h2>
              <p className="mt-4 max-w-sm text-body text-fg-secondary">Each item is built and covered by tests today.</p>
            </div>
            <ul className="m-0 flex list-none flex-col p-0">
              {CAPABILITIES.map((c) => (
                <li key={c.title} className="border-b border-hairline py-5 first:pt-0 last:border-b-0">
                  <h3 className="text-title-2">{c.title}</h3>
                  <p className="mt-1.5 max-w-prose text-body text-fg-secondary">{c.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="cta-title" className="mx-auto max-w-[1200px] px-4 pb-24 md:px-8">
          <div className="rounded-xl border border-hairline bg-surface p-8 md:p-12">
            <h2 id="cta-title" className="max-w-xl text-[clamp(1.5rem,2.6vw,2.1rem)] font-semibold leading-tight tracking-[-0.02em]">Run one allowed and one blocked request</h2>
            <p className="mt-3 max-w-xl text-body text-fg-secondary">The walkthrough sends both through the real gateway and shows the two decisions side by side. Sign in with an API key, or use a read-only preview where the host has turned it on.</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/app/walkthrough" className={buttonVariants({ size: 'lg' })}>Open the walkthrough</Link>
              <Link to="/signin" className={buttonVariants({ size: 'lg', variant: 'secondary' })}>Sign in</Link>
            </div>
          </div>
        </section>
      </div>
    </MarketingShell>
  )
}
