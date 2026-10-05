import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { openApp, setTheme } from './fixtures'

// Sprint 008 A7. Open Trust, verify a receipt (valid), then a tampered one (invalid). Axe is clean on the page, in both
// themes. Real API, real Postgres and Redis, a real signing key (a throwaway one made at startup), fake providers.
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

async function aDecisionId(page: Page): Promise<string> {
  const res = await page.request.get('/v1/decisions?limit=1')
  expect(res.ok()).toBeTruthy()
  return ((await res.json()) as { items: Array<{ id: string }> }).items[0]?.id ?? ''
}

async function scan(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  const blocking = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  console.log(`axe ${label}: violations=${results.violations.length} serious_or_critical=${blocking.length} passes=${results.passes.length}`)
  for (const v of results.violations) console.log(`  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} nodes)`)
  expect(blocking, `serious or critical violations on ${label}`).toEqual([])
}

test.describe('A7 the Trust page', () => {
  test('a receipt verifies as valid, and a tampered one as invalid', async ({ page }) => {
    await openApp(page, '/app/trust')
    await expect(page.getByRole('heading', { level: 1, name: 'Trust' })).toBeVisible()
    const id = await aDecisionId(page)

    await page.getByLabel('Decision id').fill(id)
    await page.getByRole('button', { name: 'Verify receipt' }).click()
    const valid = page.getByTestId('receipt-result')
    await expect(valid).toHaveAttribute('data-valid', 'true')
    await expect(valid.getByRole('heading', { name: 'Valid' })).toBeVisible()
    await expect(valid.getByTestId('chain-position')).toHaveText(/^\d+$/)
    await expect(valid.getByRole('list', { name: 'Checks' }).getByText('Failed')).toHaveCount(0)

    // Tamper with what the platform signed: the receipt says the call was denied. The signature and the chain hash no longer match.
    const receipt = (await (await page.request.get(`/v1/receipts/${id}`)).json()) as { decision: { outcome: string } }
    receipt.decision.outcome = receipt.decision.outcome === 'allow' ? 'deny' : 'allow'
    await page.getByText('Check a receipt you already hold').click()
    await page.getByLabel('Receipt (JSON)').fill(JSON.stringify(receipt))
    await page.getByRole('button', { name: 'Verify pasted receipt' }).click()
    const invalid = page.getByTestId('receipt-result')
    await expect(invalid).toHaveAttribute('data-valid', 'false')
    await expect(invalid.getByRole('heading', { name: 'Invalid' })).toBeVisible()
    await expect(invalid.getByRole('list', { name: 'Checks' }).getByText('Failed').first()).toBeVisible()
  })

  test('the decision drawer links to the check, which runs on arrival', async ({ page }) => {
    await openApp(page, '/app/trust')
    const id = await aDecisionId(page)
    await page.goto(`/app/decisions/${id}`)
    await page.getByRole('link', { name: 'Verify receipt' }).first().click()
    await expect(page).toHaveURL(/\/app\/trust\?decision=/)
    await expect(page.getByTestId('receipt-result')).toHaveAttribute('data-valid', 'true')
  })

  test('retention and the recorded eval gate run show', async ({ page }) => {
    await openApp(page, '/app/trust')
    await expect(page.getByTestId('retention-days')).toContainText('90 days')
    await expect(page.getByTestId('last-purge')).toHaveText('never')
    await expect(page.getByTestId('eval-latest')).toContainText('Passed')
    await expect(page.getByRole('table', { name: 'Latest eval scores' })).toContainText('Retrieval hit')
  })

  for (const theme of ['light', 'dark'] as const) {
    test(`axe is clean, ${theme} theme, after a verification`, async ({ page }) => {
      await setTheme(page, theme)
      await openApp(page, '/app/trust')
      const id = await aDecisionId(page)
      await page.getByLabel('Decision id').fill(id)
      await page.getByRole('button', { name: 'Verify receipt' }).click()
      await expect(page.getByTestId('receipt-result')).toBeVisible()
      await scan(page, `trust (${theme})`)
    })
  }
})
