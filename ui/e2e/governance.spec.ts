import { expect, test } from '@playwright/test'
import { ask, openApp, readState, signIn } from './fixtures'

const state = () => readState()
const ANON = { cookies: [], origins: [] }

test.describe('A6 governed ask, across the real API', () => {
  test.describe('signed out', () => {
    test.use({ storageState: ANON })

    test('allow: sign in, ask, open the call in Decisions, see Allowed and the policy version', async ({ page }) => {
      await signIn(page)
      await expect(page.getByTestId('tenant-crumb')).toHaveText(state().tenant)

      await ask(page, state().allowed_kb, 'How long must customer records be kept?')
      const answer = page.getByRole('region', { name: 'Answer' })
      await expect(answer).toContainText('seven years')
      await expect(answer.getByText('Allowed')).toBeVisible()
      await expect(answer.getByTestId('confidence')).toBeVisible()
      await expect(answer.getByRole('region', { name: 'Evidence' })).toContainText('retention.md')

      await answer.getByRole('link', { name: /Open receipt in Decisions/ }).click()
      await expect(page).toHaveURL(/\/app\/decisions\/[0-9a-f-]+\?.*request_id=/)

      const detail = page.getByRole('complementary', { name: 'Decision detail' })
      await expect(detail.getByText('Allowed').first()).toBeVisible()
      await expect(detail).toContainText('policy version 1')
      await expect(detail.getByRole('list', { name: 'Request trace' }).getByRole('listitem').first()).toBeVisible()
      await expect(detail.getByRole('region', { name: 'Receipt' })).toContainText('Input SHA-256')
      await expect(detail.getByRole('region', { name: 'Receipt' })).not.toContainText('customer records')
    })

    test('an unauthenticated visit to /app is sent to sign-in, and a bad key shows the error code', async ({ page }) => {
      await page.goto('/app/decisions')
      await expect(page).toHaveURL(/\/signin$/)
      await page.getByLabel('API key').fill('gap_bad_key')
      await page.getByRole('button', { name: 'Sign in', exact: true }).click()
      await expect(page.getByRole('alert')).toContainText('invalid_credentials')
    })

    test('sign out ends the session', async ({ page }) => {
      await signIn(page)
      await page.getByRole('button', { name: 'Sign out' }).click()
      await page.goto('/app/ask')
      await expect(page).toHaveURL(/\/signin$/)
    })
  })

  test('deny: a knowledge base the policy does not allow shows Denied and its reason code', async ({ page }) => {
    await openApp(page)
    await ask(page, state().denied_kb, 'What does the legal knowledge base say about retention?')

    const denied = page.getByRole('alert', { name: 'Denied' })
    await expect(denied.getByText('Denied', { exact: true })).toBeVisible()
    await expect(denied.getByText('kb_not_allowed').first()).toBeVisible()

    await denied.getByRole('link', { name: 'Open receipt in Decisions' }).click()
    const detail = page.getByRole('complementary', { name: 'Decision detail' })
    await expect(detail.locator('[data-verdict="deny"]').first()).toContainText('kb_not_allowed')
    await expect(detail.getByRole('region', { name: 'Receipt' })).toContainText('kb_not_allowed')
  })

  test('decisions filters narrow the table and the empty state explains itself', async ({ page }) => {
    await openApp(page, '/app/decisions')
    await expect(page.getByRole('table')).toBeVisible()
    await page.getByRole('radio', { name: 'Denied' }).click()
    // Retrying assertions: the table re-renders when the filter applies, so a one-time snapshot of rows can be stale.
    await expect(page.locator('tbody tr[data-outcome="deny"]').first()).toBeVisible()
    await expect(page.locator('tbody tr:not([data-outcome="deny"])')).toHaveCount(0)
    await page.getByLabel('Request id').fill('no-such-request')
    await expect(page.getByText('No decisions match these filters.')).toBeVisible()
  })
})

test.describe('A10 parity: Ask, Library and System work in the new UI', () => {
  test('Ask in agent mode returns an answer with a verdict and evidence', async ({ page }) => {
    await openApp(page)
    await page.getByRole('radio', { name: 'Agent' }).click()
    await ask(page, state().allowed_kb, 'How long must customer records be kept?')
    const answer = page.getByRole('region', { name: 'Answer' })
    await expect(answer.getByText('Allowed')).toBeVisible()
    await expect(answer.getByRole('region', { name: 'Evidence' })).toBeVisible()
  })

  test('Library lists the ingested document', async ({ page }) => {
    await openApp(page, '/app/library')
    await expect(page.getByRole('table')).toContainText('retention.md')
    await expect(page.getByRole('button', { name: 'Add documents' }).first()).toBeDisabled() // the key has no kb:write
  })

  test('System shows healthy services and the mode', async ({ page }) => {
    await openApp(page, '/app/system')
    await expect(page.getByText('Database')).toBeVisible()
    await expect(page.getByText('Healthy').first()).toBeVisible()
    await expect(page.getByText('local', { exact: true }).first()).toBeVisible()
  })

  test('History links an ask to its decision trace', async ({ page }) => {
    await openApp(page)
    await ask(page, state().allowed_kb, 'How long must customer records be kept?')
    await expect(page.getByRole('region', { name: 'Answer' })).toBeVisible()
    await page.goto('/app/history')
    await page.getByRole('link', { name: 'Open trace' }).first().click()
    await expect(page).toHaveURL(/\/app\/decisions\//)
  })

  test('Policies, Keys, Usage and Agent runs render real data', async ({ page }) => {
    await openApp(page, '/app/policies')
    await expect(page.getByRole('region', { name: /Policy version/ })).toContainText('allowed_kbs')
    await page.goto('/app/keys')
    await expect(page.getByRole('table')).toContainText('audit:read')
    await expect(page.locator('body')).not.toContainText(state().api_key)
    await page.goto('/app/usage')
    await expect(page.getByTestId('stat-requests')).toBeVisible()
    await page.goto('/app/runs')
    await expect(page.getByRole('heading', { name: 'Agent runs' })).toBeVisible()
  })
})
