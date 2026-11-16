import { expect, test } from '@playwright/test'
import { ask, openApp, readState } from './fixtures'

test('model decision to verified receipt', async ({ page }) => {
  const state = readState()
  await openApp(page, '/app/ask')
  await ask(page, state.allowed_kb, 'How long must customer records be kept?')
  await expect(page.getByRole('region', { name: 'Answer' })).toBeVisible()

  await page.goto('/app/decisions')
  await page.getByLabel('Action').fill('model.invoke')
  const row = page.locator('tbody tr').first()
  await expect(row).toBeVisible()
  await row.getByRole('link').click()

  const detail = page.getByRole('complementary', { name: 'Decision detail' })
  const evidence = detail.getByRole('region', { name: 'Model evidence' })
  await expect(evidence.getByRole('heading', { name: 'Model' })).toBeVisible()
  await expect(evidence.getByText('Alias')).toBeVisible()
  await expect(evidence.getByText('Source')).toBeVisible()
  await expect(evidence.getByText('Region')).toBeVisible()
  await expect(evidence.getByText('Phase')).toBeVisible()
  const stages = evidence.getByRole('list', { name: 'Stages' })
  await expect(stages.getByRole('listitem').first()).toBeVisible()

  await detail.getByRole('link', { name: 'Verify receipt' }).click()
  const result = page.getByTestId('receipt-result')
  await expect(result).toHaveAttribute('data-valid', 'true')
  const verified = result.getByTestId('verified-fields')
  await expect(verified.getByText('Model', { exact: true })).toBeVisible()
  await expect(verified.getByText('Stages', { exact: true })).toBeVisible()
})
