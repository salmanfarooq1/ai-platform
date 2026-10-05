import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test as setup } from '@playwright/test'
import { signIn } from './fixtures'

const AUTH_FILE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '.state/auth.json')

setup('sign in once and keep the session cookie', async ({ page }) => {
  await signIn(page)
  await expect(page.getByTestId('tenant-crumb')).toBeVisible()
  await page.context().storageState({ path: AUTH_FILE })
})
