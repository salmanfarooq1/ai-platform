import { Suspense, lazy, useEffect, useRef, useState, type ComponentType } from 'react'
import { useReducedMotion } from './use-reduced-motion'

type SceneProps = { active: boolean }

const SCENE_DELAY_MS = 3500

function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') ?? c.getContext('webgl'))
  } catch {
    return false
  }
}

/**
 * The hero art. A static poster is always in the page. After first paint, and only when motion is allowed and the
 * hero is on screen, the WebGL scene is loaded as its own chunk and fades in over the poster.
 */
export function HeroVisual() {
  const reduced = useReducedMotion()
  const box = useRef<HTMLDivElement>(null)
  const [Scene, setScene] = useState<ComponentType<SceneProps> | null>(null)
  const [visible, setVisible] = useState(true)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (reduced) return
    let cancelled = false
    let timer: number | undefined
    const load = () => {
      if (cancelled || !webglAvailable()) return
      const Lazy = lazy(() => import('./hero-scene'))
      setScene(() => Lazy as unknown as ComponentType<SceneProps>)
    }
    // The poster is the hero until the scene is ready. The scene is about 900 kB of script, so it waits a few
    // seconds after load and then for an idle moment, to keep it off the critical path.
    const schedule = () => {
      timer = window.setTimeout(() => {
        if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(load, { timeout: 2000 })
        else load()
      }, SCENE_DELAY_MS)
    }
    // "After first paint": wait for the window load event, then for an idle moment.
    if (document.readyState === 'complete') schedule()
    else window.addEventListener('load', schedule, { once: true })
    return () => { cancelled = true; window.clearTimeout(timer); window.removeEventListener('load', schedule) }
  }, [reduced])

  useEffect(() => {
    const el = box.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(([entry]) => setVisible(entry?.isIntersecting ?? true))
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <div ref={box} aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden opacity-30 [mask-image:linear-gradient(to_bottom,black_55%,transparent)]" data-testid="hero-visual" data-webgl={Scene && !reduced ? (ready ? 'ready' : 'loading') : 'off'}>
      <Poster />
      {Scene && !reduced ? (
        <div className="absolute inset-0 transition-opacity duration-500" style={{ opacity: ready ? 1 : 0 }}>
          <Suspense fallback={null}>
            <Scene active={visible} />
            <ReadyMark onReady={() => setReady(true)} />
          </Suspense>
        </div>
      ) : null}
    </div>
  )
}

/** The static poster: a gateway ring with a few requests, drawn with the design tokens. It is always in the page. */
function Poster() {
  const dots: Array<[number, number, number]> = [[110, 410, 7], [190, 330, 6], [260, 452, 5], [330, 365, 7], [470, 300, 6], [560, 250, 7], [640, 330, 5], [710, 270, 6], [600, 415, 5]]
  const denied: Array<[number, number, number]> = [[395, 450, 7], [455, 520, 5], [520, 585, 4]]
  return (
    <svg viewBox="0 0 800 640" preserveAspectRatio="xMidYMid slice" focusable="false" className="absolute inset-0 h-full w-full" data-testid="hero-poster">
      <g transform="translate(400 320) rotate(-18)" fill="none" stroke="var(--seal)">
        <ellipse rx="150" ry="215" strokeWidth="7" />
        <ellipse rx="177" ry="254" strokeWidth="2" strokeOpacity="0.4" />
      </g>
      <g fill="var(--allow)">{dots.map(([x, y, r]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={r} />)}</g>
      <g fill="var(--deny)">{denied.map(([x, y, r]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={r} />)}</g>
    </svg>
  )
}

function ReadyMark({ onReady }: { onReady: () => void }) {
  useEffect(() => { onReady() }, [onReady])
  return null
}
