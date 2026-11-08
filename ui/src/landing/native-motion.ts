/** Browser animation primitives; every observer, listener and animation has an effect cleanup. */
export function revealHeadings(root: HTMLElement) {
  const cleanups: (() => void)[] = []
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      const heading = entry.target as HTMLElement
      observer.unobserve(heading)
      const original = [...heading.childNodes]
      const label = heading.getAttribute('aria-label')
      const text = heading.textContent ?? ''
      const words = [...text.matchAll(/\S+\s*/g)]
      // Measure the original text, then mask each visual line without changing its accessible name.
      const node = heading.firstChild
      if (!node || node.nodeType !== Node.TEXT_NODE || heading.childNodes.length !== 1) continue
      const lines: string[] = []
      let top: number | undefined
      for (const word of words) {
        const range = document.createRange()
        range.setStart(node, word.index)
        range.setEnd(node, word.index + word[0].length)
        const nextTop = Math.round(range.getBoundingClientRect().top)
        if (top !== nextTop) { lines.push(''); top = nextTop }
        lines[lines.length - 1] += word[0]
      }
      const animations: Animation[] = []
      const restore = () => {
        animations.forEach((animation) => animation.cancel())
        heading.replaceChildren(...original)
        if (label === null) heading.removeAttribute('aria-label')
        else heading.setAttribute('aria-label', label)
      }
      heading.setAttribute('aria-label', text.trim().replace(/\s+/g, ' '))
      heading.replaceChildren(...lines.map((line, index) => {
        const mask = document.createElement('span')
        mask.style.display = 'block'
        mask.style.overflow = 'hidden'
        mask.setAttribute('aria-hidden', 'true')
        const content = document.createElement('span')
        content.style.display = 'block'
        content.textContent = line
        mask.append(content)
        animations.push(content.animate([
          { transform: 'translateY(105%)', opacity: 0 },
          { transform: 'translateY(0)', opacity: 1 },
        ], { duration: 700, delay: index * 80, easing: 'cubic-bezier(0.165, 0.84, 0.44, 1)', fill: 'backwards' }))
        return mask
      }))
      // Restore flowing text after the reveal so font loads and resizes reflow naturally.
      void Promise.all(animations.map((animation) => animation.finished)).then(restore, () => undefined)
      cleanups.push(restore)
    }
  }, { rootMargin: '0px 0px -12% 0px' })
  root.querySelectorAll<HTMLElement>('[data-reveal]').forEach((heading) => observer.observe(heading))
  return () => { observer.disconnect(); cleanups.forEach((cleanup) => cleanup()) }
}

export function scrubStory(root: HTMLElement, pin: HTMLElement) {
  const panels = [...pin.querySelectorAll<HTMLElement>('[data-panel]')]
  const bars = [...pin.querySelectorAll<HTMLElement>('[data-bar]')]
  const elements = [root, pin, ...panels, ...bars]
  const styles = elements.map((element) => element.getAttribute('style'))
  const hadSpacer = root.classList.contains('pin-spacer')
  let frame = 0
  const render = () => {
    frame = 0
    const progress = Math.max(0, Math.min(panels.length - 1, -root.getBoundingClientRect().top / (innerHeight * 0.7)))
    const step = Math.floor(progress)
    const transition = Math.max(0, Math.min(1, (progress - step - 0.45) / 0.35))
    panels.forEach((panel, index) => {
      const opacity = index === step ? 1 - transition : index === step + 1 ? transition : 0
      panel.style.opacity = String(opacity)
      panel.style.visibility = opacity > 0 ? 'visible' : 'hidden'
      panel.style.transform = `translateY(${index <= step ? -transition * 24 : (1 - transition) * 24}px)`
      const bar = bars[index]
      if (bar) bar.style.opacity = String(opacity)
    })
  }
  const schedule = () => { if (!frame) frame = requestAnimationFrame(render) }
  const resize = () => { root.style.height = `${innerHeight * (1 + panels.length * 0.7)}px`; schedule() }
  root.classList.add('pin-spacer')
  pin.style.position = 'sticky'
  pin.style.top = '0'
  panels.forEach((panel) => { panel.style.transition = 'opacity 400ms linear, transform 400ms linear' })
  bars.forEach((bar) => { bar.style.transition = 'opacity 400ms linear' })
  window.addEventListener('scroll', schedule, { passive: true })
  window.addEventListener('resize', resize)
  resize()
  return () => {
    cancelAnimationFrame(frame)
    window.removeEventListener('scroll', schedule)
    window.removeEventListener('resize', resize)
    elements.forEach((element, index) => {
      const style = styles[index]
      if (style === null || style === undefined) element.removeAttribute('style')
      else element.setAttribute('style', style)
    })
    if (!hadSpacer) root.classList.remove('pin-spacer')
  }
}
