import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { ask, openApp, readState, setTheme } from './fixtures'

// A9 and 005b A5: axe on the landing page, How it works, Overview, Requests with the drawer open, the walkthrough, Ask and
// Decisions, in both themes. 0 serious or critical violations.
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

async function scan(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  const blocking = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  const byImpact = (i: string) => results.violations.filter((v) => v.impact === i).length
  console.log(`axe ${label}: violations=${results.violations.length} critical=${byImpact('critical')} serious=${byImpact('serious')} moderate=${byImpact('moderate')} minor=${byImpact('minor')} passes=${results.passes.length}`)
  for (const v of results.violations) console.log(`  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} nodes) ${v.nodes[0]?.target.join(' ') ?? ''}`)
  expect(blocking, `serious or critical violations on ${label}`).toEqual([])
}

for (const theme of ['light', 'dark'] as const) {
  test.describe(`axe, ${theme} theme`, () => {
    test.beforeEach(async ({ page }) => { await setTheme(page, theme) })

    test('landing page', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByTestId('hero-visual')).toHaveAttribute('data-webgl', 'ready', { timeout: 30_000 })
      await scan(page, `landing (${theme})`)
    })

    test('How it works', async ({ page }) => {
      await page.goto('/how-it-works')
      await expect(page.getByRole('heading', { level: 1, name: 'How a call is checked' })).toBeVisible()
      await scan(page, `how it works (${theme})`)
    })
    test('Overview', async ({ page }) => {
      await openApp(page)
      await ask(page, readState().denied_kb, 'What does the legal knowledge base say about retention?')
      await expect(page.getByRole('alert', { name: 'Denied' })).toBeVisible()
      await page.goto('/app')
      await expect(page.getByTestId('tile-blocked')).toBeVisible()
      await expect(page.getByRole('list', { name: 'Top deny reasons' })).toBeVisible()
      await scan(page, `overview (${theme})`)
    })
    test('Requests, with the drawer open on a denied request', async ({ page }) => {
      await openApp(page)
      await ask(page, readState().denied_kb, 'What does the legal knowledge base say about retention?')
      await page.getByRole('alert', { name: 'Denied' }).getByTestId('governance-line').click()
      const drawer = page.getByRole('dialog', { name: 'Request' })
      await expect(drawer.getByTestId('deny-callout')).toBeVisible()
      await scan(page, `requests drawer (${theme})`)
    })
    test('Requests, the list', async ({ page }) => {
      await openApp(page, '/app/requests')
      await expect(page.getByRole('table')).toBeVisible()
      await scan(page, `requests list (${theme})`)
    })
    test('the walkthrough, after both requests ran', async ({ page }) => {
      await openApp(page, '/app/walkthrough')
      await page.getByRole('button', { name: 'Run both' }).click()
      await expect(page.getByTestId('walkthrough-blocked').getByTestId('deny-callout')).toBeVisible()
      await expect(page.getByTestId('walkthrough-allowed').getByRole('list', { name: 'Request trace' })).toBeVisible()
      await scan(page, `walkthrough (${theme})`)
    })
    test('the command palette, open', async ({ page }) => {
      await openApp(page)
      await page.keyboard.press('ControlOrMeta+k')
      await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeVisible()
      await scan(page, `command palette (${theme})`)
    })
    test('the session menu, open', async ({ page }) => {
      await openApp(page)
      await page.getByRole('button', { name: 'Session menu' }).click()
      await expect(page.getByTestId('session-identity')).toBeVisible()
      await scan(page, `session menu (${theme})`)
    })
    test('Ask, with an answer', async ({ page }) => {
      await openApp(page)
      await ask(page, readState().allowed_kb, 'How long must customer records be kept?')
      await expect(page.getByRole('region', { name: 'Answer' })).toContainText('seven years')
      await scan(page, `ask (${theme})`)
    })

    test('Ask, with a denial', async ({ page }) => {
      await openApp(page)
      await ask(page, readState().denied_kb, 'What does the legal knowledge base say about retention?')
      await expect(page.getByRole('alert', { name: 'Denied' })).toBeVisible()
      await scan(page, `ask denied (${theme})`)
    })

    test('Decisions, with a denied decision open', async ({ page }) => {
      await openApp(page)
      await ask(page, readState().denied_kb, 'What does the legal knowledge base say about retention?')
      await page.getByRole('link', { name: 'Open receipt in Decisions' }).click()
      await expect(page.getByRole('complementary', { name: 'Decision detail' }).locator('[data-verdict="deny"]').first()).toBeVisible()
      await scan(page, `decisions denied (${theme})`)
    })

    test('Decisions, with a decision open', async ({ page }) => {
      await openApp(page)
      await ask(page, readState().allowed_kb, 'How long must customer records be kept?')
      await page.getByRole('link', { name: /Open receipt in Decisions/ }).click()
      await expect(page.getByRole('complementary', { name: 'Decision detail' }).getByRole('region', { name: 'Receipt' })).toBeVisible()
      await scan(page, `decisions (${theme})`)
    })
  })
}
