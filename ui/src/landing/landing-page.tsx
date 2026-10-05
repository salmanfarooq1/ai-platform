import { ArrowRight, Moon, Sun } from '@phosphor-icons/react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useTheme } from '@/app/theme'
import { Logo } from '@/components/governance/logo'
import { buttonVariants } from '@/components/ui/button-variants'
import { cn } from '@/lib/utils'
import { loadGsap } from './gsap-loader'
import { HeroVisual } from './hero-visual'
import { ScrollStory } from './scroll-story'
import { useReducedMotion } from './use-reduced-motion'

const CAPABILITIES = [
  { title: 'One entry point', body: 'Models, tools and knowledge bases are reached only through the gateway. Agent code cannot import the model client, and a test checks it.' },
  { title: 'Policy per tenant', body: 'A tenant narrows what it may do: knowledge bases, tools, models, tool calls and tokens. Policies are versioned, and each request is checked against the current version.' },
  { title: 'Receipts you can read', body: 'The Decisions explorer filters every call by verdict, action, principal and policy version, and shows the stage trace for a request.' },
  { title: 'Isolation in the database', body: 'Postgres row-level security separates tenants. The app refuses to start as a superuser, so a bug in a query cannot read another tenant.' },
  { title: 'Read-only previews', body: 'A preview session drops the write and admin scopes. Visitors can ask questions, and they cannot add documents or change settings.' },
  { title: 'Limits that fail closed', body: 'Rate limit and daily token budget are gateway stages. If a decision cannot be written down, an allow becomes a deny.' },
]

export default function LandingPage() {
  const reduced = useReducedMotion()
  const root = useRef<HTMLDivElement>(null)
  const { isDark, toggle } = useTheme()

  useEffect(() => { document.title = 'Governed Agent Platform' }, [])

  // Text reveals for headings. With reduced motion nothing is animated and the text is shown as it is.
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
    <div ref={root} className="min-h-screen bg-canvas">
      <a href="#content" className="skip-link">Skip to content</a>
      <header className="sticky top-0 z-30 border-b border-hairline bg-[var(--material-thin)] backdrop-blur-[var(--material-blur)]">
        <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-4 px-4 md:px-8">
          <Logo />
          <nav aria-label="Page" className="ml-6 hidden items-center gap-5 text-callout text-fg-secondary md:flex">
            <a className="rounded-sm hover:text-fg" href="#how-it-works">How it works</a>
            <a className="rounded-sm hover:text-fg" href="#capabilities">Capabilities</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button type="button" onClick={toggle} aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'} className="rounded-sm p-2 text-fg-secondary hover:bg-muted hover:text-fg">
              {isDark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <Link to="/app/ask" className={buttonVariants({ size: 'sm' })}>Open the workspace</Link>
          </div>
        </div>
      </header>

      <main id="content">
        <section className="mx-auto grid max-w-[1200px] items-center gap-10 px-4 pb-16 pt-14 md:grid-cols-[1.05fr_1fr] md:px-8 md:pb-24 md:pt-24" aria-labelledby="hero-title">
          <div>
            <p className="eyebrow mb-4">Governance for agents</p>
            <h1 id="hero-title" className="text-[clamp(2.1rem,4.6vw,3.6rem)] font-semibold leading-[1.05] tracking-[-0.03em]">
              Let agents work on your data. Keep the rules in your hands.
            </h1>
            <p className="mt-5 max-w-xl text-[1.0625rem] leading-relaxed text-fg-secondary">
              Every model, tool and knowledge base call passes one gateway. Policy decides, and each decision is written down in a receipt you can open and read.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/app/ask" className={cn(buttonVariants({ size: 'lg' }))}>Open the workspace <ArrowRight size={18} aria-hidden="true" /></Link>
              <a href="#how-it-works" className={cn(buttonVariants({ size: 'lg', variant: 'secondary' }))}>See one request</a>
            </div>
          </div>
          <HeroVisual />
        </section>

        <ScrollStory />

        <section id="capabilities" aria-labelledby="cap-title" className="mx-auto max-w-[1200px] px-4 py-20 md:px-8 md:py-28">
          <div className="grid gap-10 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <div className="md:sticky md:top-24 md:self-start">
              <h2 id="cap-title" data-reveal className="text-[clamp(1.6rem,3vw,2.4rem)] font-semibold leading-tight tracking-[-0.02em]">What the platform does for you</h2>
              <p className="mt-4 max-w-sm text-body text-fg-secondary">Each item below is built and covered by tests today.</p>
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
            <h2 id="cta-title" className="max-w-xl text-[clamp(1.5rem,2.6vw,2.1rem)] font-semibold leading-tight tracking-[-0.02em]">Ask a question, then open its receipt</h2>
            <p className="mt-3 max-w-xl text-body text-fg-secondary">Sign in with an API key, or look around in a read-only preview where the host has turned it on.</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/app/ask" className={buttonVariants({ size: 'lg' })}>Open the workspace</Link>
              <Link to="/signin" className={buttonVariants({ size: 'lg', variant: 'secondary' })}>Sign in</Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-hairline">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-4 py-6 text-footnote text-fg-secondary md:px-8">
          <span>Governed Agent Platform</span>
          <nav aria-label="Footer" className="flex gap-4">
            <Link className="rounded-sm hover:text-fg" to="/signin">Sign in</Link>
            <a className="rounded-sm hover:text-fg" href="#capabilities">Capabilities</a>
          </nav>
        </div>
      </footer>
    </div>
  )
}
