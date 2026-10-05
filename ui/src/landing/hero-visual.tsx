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
    <div ref={box} className="relative aspect-[5/4] w-full overflow-hidden rounded-xl" data-testid="hero-visual" data-webgl={Scene && !reduced ? (ready ? 'ready' : 'loading') : 'off'}>
      <img src="/hero-poster.svg" width={800} height={640} alt="" decoding="async" className="absolute inset-0 h-full w-full object-cover" data-testid="hero-poster" />
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

function ReadyMark({ onReady }: { onReady: () => void }) {
  useEffect(() => { onReady() }, [onReady])
  return null
}
