import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { ask, openApp, readState, setTheme } from './fixtures'

// A9: axe on Ask, Decisions and the landing page, in both themes. 0 serious or critical violations.
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
