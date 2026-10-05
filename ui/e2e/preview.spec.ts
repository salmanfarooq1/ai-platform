import { expect, test } from '@playwright/test'

// The preview server runs with MODE=public-preview (second webServer in playwright.config.ts).
test.use({ baseURL: 'http://127.0.0.1:4174', storageState: { cookies: [], origins: [] } })

test('read-only preview: continue without a key, see the mode chip, cannot add documents', async ({ page }) => {
  await page.goto('/signin')
  await page.getByRole('button', { name: 'Continue in read-only preview' }).click()
  await expect(page).toHaveURL(/\/app\/walkthrough$/)
  await expect(page.getByTestId('mode-chip')).toContainText('Public preview')
  await expect(page.getByTestId('mode-chip')).toContainText('read-only')
  await page.goto('/app/library')
  await expect(page.getByRole('button', { name: 'Add documents' }).first()).toBeDisabled()
  await page.goto('/app/keys')
  await expect(page.getByRole('table')).toBeVisible()
})
