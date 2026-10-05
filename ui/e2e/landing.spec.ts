import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

const DIST = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../dist')

test.describe('A7 landing page: build output', () => {
  test('the WebGL code is its own chunk and no /app chunk contains it', () => {
    const assets = fs.readdirSync(path.join(DIST, 'assets')).filter((f) => f.endsWith('.js'))
    const html = fs.readFileSync(path.join(DIST, 'index.html'), 'utf8')
    const webglMarkers = /WebGLRenderer|getContext\(["']webgl/
    const withWebgl = assets.filter((f) => webglMarkers.test(fs.readFileSync(path.join(DIST, 'assets', f), 'utf8')))
    console.log('chunks:', assets.join(', '))
    console.log('chunks containing WebGL code:', withWebgl.join(', '))
    // three.js lives in webgl-*.js. hero-scene and landing-page may mention a context probe, but no app chunk may.
    expect(withWebgl.length).toBeGreaterThan(0)
    for (const f of withWebgl) expect(f).toMatch(/^(webgl|hero-scene|landing-page)-/)
    const appChunks = assets.filter((f) => !/^(webgl|hero-scene|landing-page|gsap)-/.test(f))
    console.log('app chunks checked:', appChunks.join(', '))
    for (const f of appChunks) {
      const text = fs.readFileSync(path.join(DIST, 'assets', f), 'utf8')
      expect(text, `${f} must not contain three.js`).not.toMatch(/WebGLRenderer|@react-three|THREE\./)
      expect(text, `${f} must not name the webgl chunk`).not.toMatch(/webgl-[\w-]+\.js/)
      expect(text, `${f} must not name the gsap chunk`).not.toMatch(/gsap-[\w-]+\.js/)
    }
    // The entry HTML preloads neither the WebGL chunk nor GSAP.
    expect(html).not.toMatch(/webgl|gsap|hero-scene/)
  })
})

test.describe('A7 landing page: motion on', () => {
  test('the WebGL chunk loads after first paint, and the scroll story pins', async ({ page }) => {
    const requests: Array<{ url: string; at: number }> = []
    const t0 = Date.now()
    page.on('request', (r) => requests.push({ url: r.url(), at: Date.now() - t0 }))
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

    const hero = page.getByTestId('hero-visual')
    await expect(hero).toHaveAttribute('data-webgl', 'ready', { timeout: 30_000 })
    await expect(page.getByTestId('hero-poster')).toBeAttached()

    const timing = await page.evaluate(() => {
      const fcp = performance.getEntriesByType('paint').find((p) => p.name === 'first-contentful-paint')?.startTime ?? -1
      const res = performance.getEntriesByType('resource').filter((r) => /\/assets\/(webgl|hero-scene)-/.test(r.name))
      return { fcp, webgl: res.map((r) => ({ name: r.name.split('/').pop(), start: r.startTime })) }
    })
    console.log('first-contentful-paint ms:', Math.round(timing.fcp), 'webgl requests:', JSON.stringify(timing.webgl))
    expect(timing.fcp).toBeGreaterThan(0)
    expect(timing.webgl.length).toBeGreaterThan(0)
    for (const r of timing.webgl) expect(r.start).toBeGreaterThan(timing.fcp)
    expect(requests.filter((r) => /assets\/webgl-/.test(r.url)).length).toBe(1)

    const story = page.getByTestId('scroll-story')
    await expect(story).toHaveAttribute('data-motion', 'scrub')
    expect(await page.locator('.pin-spacer').count()).toBeGreaterThan(0)
  })

  test('scrolling moves the story from the first panel to the last', async ({ page }) => {
    await page.goto('/')
    const story = page.getByTestId('scroll-story')
    await expect(story).toHaveAttribute('data-motion', 'scrub')
    const panels = story.locator('[data-panel]')
    await story.scrollIntoViewIfNeeded()
    await page.evaluate(() => document.getElementById('how-it-works')?.scrollIntoView())
    await expect.poll(async () => Number(await panels.nth(0).evaluate((el) => getComputedStyle(el).opacity))).toBeGreaterThan(0.9)
    await page.evaluate(() => window.scrollBy(0, window.innerHeight * 3.4))
    await expect.poll(async () => Number(await panels.nth(4).evaluate((el) => getComputedStyle(el).opacity))).toBeGreaterThan(0.9)
    await expect.poll(async () => Number(await panels.nth(0).evaluate((el) => getComputedStyle(el).opacity))).toBeLessThan(0.1)
  })
})

test.describe('A7 landing page: reduced motion', () => {
  test.use({ contextOptions: { reducedMotion: 'reduce' } })

  test('no GSAP, no WebGL, the poster is shown and every story step is visible', async ({ page }) => {
    const urls: string[] = []
    page.on('request', (r) => urls.push(r.url()))
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500) // longer than the idle delay that would start the WebGL load

    expect(urls.filter((u) => /\/assets\/(webgl|gsap|hero-scene)-/.test(u))).toEqual([])
    await expect(page.getByTestId('hero-visual')).toHaveAttribute('data-webgl', 'off')
    await expect(page.getByTestId('hero-poster')).toBeVisible()
    await expect(page.locator('canvas')).toHaveCount(0)
    await expect(page.getByTestId('scroll-story')).toHaveAttribute('data-motion', 'static')
    expect(await page.locator('.pin-spacer').count()).toBe(0)
    for (const title of ['Agent asks', 'Gateway', 'Policy', 'Allow or deny', 'Record']) {
      await expect(page.getByTestId('scroll-story').getByRole('heading', { level: 3, name: title, exact: true }).first()).toBeVisible()
    }
    // The text is shown in full, not held back by a reveal.
    const opacity = await page.locator('#story-title').evaluate((el) => getComputedStyle(el).opacity)
    expect(opacity).toBe('1')
  })
})

test.describe('005b landing page: copy and sections', () => {
  test('the headline and subline are exact, and the hero is built from real components labelled as examples', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your agents can only ever do less.')
    await expect(page.getByText('Control what your agents can do. See everything they did.', { exact: true })).toBeVisible()
    const examples = page.getByTestId('hero-examples')
    await expect(examples).toContainText('Example data')
    await expect(examples.getByRole('region', { name: 'Receipt' })).toBeVisible()
    await expect(examples.getByTestId('deny-callout')).toContainText('Denied at Tenant policy')
  })

  test('has the use cases, the one reason the gateway sits outside the agent, and no problem section', async ({ page }) => {
    await page.goto('/')
    const cases = page.locator('#use-cases')
    for (const text of ['An internal knowledge assistant over company documents', 'An agent with tool access', 'A team that must see what its agents did']) {
      await expect(cases).toContainText(text)
    }
    await expect(cases).toContainText('The policy lists which knowledge bases can be read.')
    await expect(cases).not.toContainText('and nothing else')
    await expect(page.getByRole('heading', { level: 2, name: 'Why the gateway sits outside the agent' })).toBeVisible()
    await expect(page.getByText('Checks inside agent code can be skipped or changed by that code.').first()).toBeVisible()
    await expect(page.getByRole('heading', { name: /problem/i })).toHaveCount(0)
  })

  test('How it works is a public page without GSAP or WebGL', async ({ page }) => {
    const urls: string[] = []
    page.on('request', (r) => urls.push(r.url()))
    await page.goto('/how-it-works')
    await expect(page.getByRole('heading', { level: 1, name: 'How a call is checked' })).toBeVisible()
    await page.waitForLoadState('networkidle')
    expect(urls.filter((u) => /\/assets\/(webgl|gsap|hero-scene)-/.test(u))).toEqual([])
    await expect(page.locator('canvas')).toHaveCount(0)
    await expect(page.getByRole('region', { name: 'Receipt' })).toBeVisible()
    await expect(page.getByText('With no tenant policy, the scopes on the key decide what is allowed, and a policy can only narrow that.')).toBeVisible()
    await expect(page.getByText('Nothing is allowed by default')).toHaveCount(0)
  })
})
