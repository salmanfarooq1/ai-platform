// The pinned scroll story follows the GSAP ScrollTrigger pinning pattern. 21st.dev has similar scroll sections
// (https://21st.dev). It is not reachable from the build container, so this is built from the pattern, with no code copied.
import { useEffect, useRef } from 'react'
import { loadGsap } from './gsap-loader'
import { STORY_STEPS } from './story-data'
import { StoryPanel } from './story-panels'
import { useMediaQuery, useReducedMotion } from './use-reduced-motion'

/** The governed-request scroll story. With reduced motion it is a plain list showing every end state. */
export function ScrollStory() {
  const prefersReduced = useReducedMotion()
  const narrow = useMediaQuery('(max-width: 767px)')
  // On a narrow screen the pinned layout does not fit, so it shows the same plain list as reduced motion.
  const reduced = prefersReduced || narrow
  const root = useRef<HTMLElement>(null)
  const pin = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (reduced || !root.current || !pin.current) return
    let revert: (() => void) | undefined
    let cancelled = false
    const rootEl = root.current
    const pinEl = pin.current
    void loadGsap().then(({ gsap }) => {
      if (cancelled) return
      const ctx = gsap.context(() => {
        const panels = gsap.utils.toArray<HTMLElement>('[data-panel]', pinEl)
        // The active step is marked by a bar. Text stays at full contrast, so every step passes AA.
        const items = gsap.utils.toArray<HTMLElement>('[data-bar]', pinEl)
        gsap.set(panels, { autoAlpha: 0, y: 24 })
        gsap.set(items, { opacity: 0 })
        // The first step is showing when the story pins.
        if (panels[0]) gsap.set(panels[0], { autoAlpha: 1, y: 0 })
        if (items[0]) gsap.set(items[0], { opacity: 1 })
        const tl = gsap.timeline({
          defaults: { ease: 'none' },
          scrollTrigger: { trigger: pinEl, start: 'top top', end: `+=${STORY_STEPS.length * 70}%`, pin: true, scrub: 0.4, anticipatePin: 1 },
        })
        panels.forEach((p, i) => {
          const prev = panels[i - 1]
          const prevItem = items[i - 1]
          const item = items[i]
          if (prev) tl.to(prev, { autoAlpha: 0, y: -24, duration: 0.35 }, i)
          if (prevItem) tl.to(prevItem, { opacity: 0, duration: 0.35 }, i)
          if (i === 0) return
          tl.to(p, { autoAlpha: 1, y: 0, duration: 0.35 }, i + 0.2)
          if (item) tl.to(item, { opacity: 1, duration: 0.35 }, i + 0.2)
        })
        tl.to({}, { duration: 0.5 })
      }, rootEl)
      rootEl.dataset['motion'] = 'scrub'
      revert = () => ctx.revert()
    })
    return () => { cancelled = true; revert?.(); delete rootEl.dataset['motion'] }
  }, [reduced])

  return (
    <section ref={root} id="how-it-works" aria-labelledby="story-title" data-testid="scroll-story" data-motion={reduced ? 'static' : 'pending'}>
      <div ref={pin} className={reduced ? 'py-16' : 'flex min-h-screen flex-col justify-center py-10'}>
        <div className="mx-auto w-full max-w-[1200px] px-4 md:px-8">
          <h2 id="story-title" data-reveal className="mb-8 max-w-2xl text-[clamp(1.6rem,3vw,2.4rem)] font-semibold leading-tight tracking-[-0.02em]">
            One governed request, from the first question to the receipt
          </h2>
          {reduced ? (
            <ol className="m-0 flex list-none flex-col gap-10 p-0">
              {STORY_STEPS.map((s) => (
                <li key={s.id} className="grid gap-4 md:grid-cols-[1fr_1.2fr]">
                  <div><h3 className="text-title-2">{s.title}</h3><p className="mt-1 text-body text-fg-secondary">{s.body}</p></div>
                  <StoryPanel id={s.id} />
                </li>
              ))}
            </ol>
          ) : (
            <div className="grid gap-8 md:grid-cols-[1fr_1.2fr]">
              <ol className="m-0 flex list-none flex-col gap-5 p-0">
                {STORY_STEPS.map((s, i) => (
                  <li key={s.id} data-step className="relative max-w-md pl-4">
                    <span data-bar aria-hidden="true" className="absolute inset-y-0 left-0 w-0.5 rounded-full bg-brand" style={{ opacity: i === 0 ? 1 : 0 }} />
                    <h3 className="text-title-2">{s.title}</h3>
                    <p className="mt-1 text-callout text-fg-secondary">{s.body}</p>
                  </li>
                ))}
              </ol>
              <div className="relative min-h-[470px]" aria-live="off">
                {STORY_STEPS.map((s, i) => (
                  <div key={s.id} data-panel className="absolute inset-0" style={i === 0 ? undefined : { opacity: 0, visibility: 'hidden' }}>
                    <StoryPanel id={s.id} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
