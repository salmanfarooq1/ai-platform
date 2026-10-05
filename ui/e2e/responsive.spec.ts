import { expect, test } from '@playwright/test'
import { openApp } from './fixtures'

// At phone width the page must not scroll sideways. Wide tables scroll inside their own container instead.
test.use({ viewport: { width: 390, height: 844 } })

async function noSidewaysScroll(page: import('@playwright/test').Page, label: string) {
  const { scroll, inner } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }))
  expect(scroll, `${label}: scrollWidth ${scroll} must not exceed ${inner}`).toBeLessThanOrEqual(inner)
}

test('landing page fits a phone', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await noSidewaysScroll(page, 'landing')
  await expect(page.getByTestId('scroll-story')).toHaveAttribute('data-motion', 'static') // the plain list, not the pinned layout
})

test('how it works fits a phone', async ({ page }) => {
  await page.goto('/how-it-works')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await noSidewaysScroll(page, 'how it works')
})

for (const route of ['/app', '/app/walkthrough', '/app/requests', '/app/ask', '/app/decisions', '/app/library', '/app/policies', '/app/keys', '/app/usage', '/app/runs', '/app/system', '/app/history']) {
  test(`${route} fits a phone`, async ({ page }) => {
    await openApp(page, route)
    await page.waitForLoadState('networkidle')
    await noSidewaysScroll(page, route)
  })
}
