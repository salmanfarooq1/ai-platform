/** GSAP is loaded on demand, so a visitor with reduced motion never downloads it. All GSAP plugins are free (npm `gsap`). */
export async function loadGsap() {
  const [{ gsap }, { ScrollTrigger }, { SplitText }] = await Promise.all([import('gsap'), import('gsap/ScrollTrigger'), import('gsap/SplitText')])
  gsap.registerPlugin(ScrollTrigger, SplitText)
  return { gsap, ScrollTrigger, SplitText }
}
