import { expect, test } from '@playwright/test'
import { ask, readState, signIn } from './fixtures'

const GATEWAY_UI = 'http://127.0.0.1:4175'
const ANON = { cookies: [], origins: [] }
const gatewayState = () => readState('gateway/state.json')

test.describe('Gateway edition module boundaries', () => {
  test.use({ baseURL: GATEWAY_UI, storageState: ANON })

  test('gateway edition hides agents and keeps search and trust', async ({ page }) => {
    await signIn(page, gatewayState().api_key)
    await expect(page.getByRole('link', { name: 'Agent runs' })).toHaveCount(0)

    await page.goto('/app/modules')
    const agents = page.getByRole('region', { name: 'Agents' })
    await expect(agents.getByRole('listitem')).toContainText('Agents')
    await expect(agents.getByLabel('Agents: off')).toBeVisible()
    const gateway = page.getByRole('region', { name: 'Gateway' })
    await expect(gateway.getByLabel('Gateway: on')).toBeVisible()

    await page.goto('/app/ask')
    await expect(page.getByRole('radio', { name: 'Agent' })).toHaveCount(0)
    await ask(page, gatewayState().allowed_kb, 'How long must customer records be kept?')
    const answer = page.getByRole('region', { name: 'Answer' })
    await expect(answer).toContainText('seven years')

    const decisions = await page.request.get('/v1/decisions?limit=1')
    expect(decisions.ok()).toBeTruthy()
    const id = ((await decisions.json()) as { items: Array<{ id: string }> }).items[0]?.id
    expect(id).toBeTruthy()
    await page.goto('/app/trust')
    await page.getByLabel('Decision id').fill(id!)
    await page.getByRole('button', { name: 'Verify receipt' }).click()
    await expect(page.getByTestId('receipt-result')).toHaveAttribute('data-valid', 'true')
  })

  test('direct agent runs url shows module unavailable', async ({ page }) => {
    await signIn(page, gatewayState().api_key)
    const runRequests: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/v1/agent/runs')) runRequests.push(request.url())
    })
    await page.goto('/app/runs')
    await expect(page.getByRole('heading', { name: 'Agent runs' })).toBeVisible()
    await expect(page.getByRole('status')).toContainText('Agent runs are unavailable in this edition.')
    await expect.poll(() => runRequests).toEqual([])
  })
})
