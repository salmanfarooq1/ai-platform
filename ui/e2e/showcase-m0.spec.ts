import { execFileSync } from 'node:child_process'
import { expect, test } from '@playwright/test'
import { ask, readState, signIn } from './fixtures'

test('m0 journey', async ({ page }) => {
  const state = readState('showcase-m0/state.json')
  const policy = (action: string) => execFileSync(process.env.POETRY || 'poetry', ['run', 'python', '-m', 'scripts.showcase.m0_policy', action, 'ui/e2e/.state/showcase-m0'], { cwd: '..', encoding: 'utf8' })
  expect(policy('status')).toContain('baseline allowed')
  try {
  expect(policy('deny')).toContain('journey deny')
  await signIn(page, state.api_key)
  await page.goto('/app/ask')
  const searchResponse = page.waitForResponse((response) => response.url().endsWith('/v1/search') && response.request().method() === 'POST')
  await ask(page, state.allowed_kb, 'How long must customer records be kept?')
  const requestId = (await searchResponse).headers()['x-request-id']
  expect(requestId).toBeTruthy()
  if (!requestId) throw new Error('Search response omitted X-Request-ID')
  const denied = page.getByRole('alert', { name: 'Denied' })
  await expect(denied).toContainText('model_not_allowed')
  await page.goto(`/app/decisions?request_id=${encodeURIComponent(requestId)}&action=model.invoke&outcome=deny`)
  const row = page.locator('tbody tr[data-outcome="deny"]').filter({ hasText: 'model_not_allowed' })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('model.invoke')
  await row.getByRole('link').click()
  const detail = page.getByRole('complementary', { name: 'Decision detail' })
  await expect(detail.getByRole('region', { name: 'Receipt' })).toContainText('model_not_allowed')
  await detail.getByRole('link', { name: 'Verify receipt' }).click()
  await expect(page.getByTestId('receipt-result')).toHaveAttribute('data-valid', 'true')
  await expect(page.getByTestId('verified-fields')).toContainText('model_not_allowed')
  await page.goto('/app/modules')
  await expect(page.getByRole('region', { name: 'Agents' }).getByLabel('Agents: off')).toBeVisible()
  } finally {
    expect(policy('restore')).toContain('baseline restored as new version')
  }
})
