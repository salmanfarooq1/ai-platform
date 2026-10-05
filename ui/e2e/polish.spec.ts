import { expect, test, type Page } from '@playwright/test'
import { ask, openApp, readState, signIn } from './fixtures'

// Sprint 005b, A4 (a) to (e): the polish round, against the real API.
const state = () => readState()
const ANON = { cookies: [], origins: [] }
const ALLOWED_Q = 'How long must customer records be kept?'
const DENIED_Q = 'What does the legal knowledge base say about retention?'

/** Ask a question and return the request id the governance line points to. */
async function askAndGetRequestId(page: Page, kb: string, q: string): Promise<string> {
  await openApp(page)
  await ask(page, kb, q)
  const line = page.getByTestId('governance-line').first()
  await expect(line).toBeVisible()
  const href = (await line.getAttribute('href')) ?? ''
  const id = decodeURIComponent(href.split('/app/requests/')[1] ?? '')
  expect(id.length).toBeGreaterThan(8)
  return id
}

test.describe('A4 (a) the walkthrough', () => {
  test('shows an allowed and a blocked request side by side, the blocked one at the guardrails stage', async ({ page }) => {
    await openApp(page, '/app/walkthrough')
    await page.getByRole('button', { name: 'Run both' }).click()
    const allowed = page.getByTestId('walkthrough-allowed')
    const blocked = page.getByTestId('walkthrough-blocked')
    await expect(allowed).toBeVisible()
    await expect(blocked).toBeVisible()
    await expect(allowed.locator('[data-verdict="allow"]').first()).toContainText('Allowed')
    await expect(blocked.locator('[data-verdict="deny"]').first()).toContainText('Denied')
    // The blocked request is stopped by the input guardrails, which every tenant has.
    await expect(blocked.getByTestId('deny-stage')).toContainText('Denied at Input guardrails')
    await expect(blocked.getByText('guardrails', { exact: true })).toBeVisible()
    await expect(blocked.getByTestId('deny-sentence')).not.toBeEmpty()
    await expect(blocked.getByRole('list', { name: 'Request trace' })).toBeVisible()
    await expect(allowed.getByRole('list', { name: 'Request trace' })).toBeVisible()
    // Side by side: the same row, allowed on the left.
    const a = await allowed.boundingBox()
    const b = await blocked.boundingBox()
    expect(a && b).toBeTruthy()
    expect(a!.x).toBeLessThan(b!.x)
    expect(Math.abs(a!.y - b!.y)).toBeLessThan(4)
    // Each result links to its request.
    await blocked.getByRole('link', { name: /Open the request/ }).click()
    await expect(page).toHaveURL(/\/app\/requests\/[^/]+$/)
    await expect(page.getByRole('dialog', { name: 'Request' })).toBeVisible()
  })

})

test.describe('A4 (a) the first run', () => {
  test.use({ storageState: ANON })
  test('a new browser opens the walkthrough first, and the Overview after that', async ({ page }) => {
    await signIn(page)
    await expect(page).toHaveURL(/\/app\/walkthrough$/)
    await page.getByRole('button', { name: 'Session menu' }).click()
    await page.getByRole('menuitem', { name: 'Sign out' }).click()
    await expect(page).toHaveURL(/\/signin$/)
    // A fresh visit. (Signing straight back in on the redirected page returns to the page you left, which is the walkthrough.)
    await page.goto('/')
    await signIn(page, undefined, { first: false })
    await expect(page).toHaveURL(/\/app$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
  })
})

test.describe('A4 (b) the governance line in Ask', () => {
  test('shows "Checked by policy v1 ..." and the line opens the request drawer', async ({ page }) => {
    await openApp(page)
    await ask(page, state().allowed_kb, ALLOWED_Q)
    const answer = page.getByRole('region', { name: 'Answer' })
    await expect(answer).toContainText('seven years')
    const line = answer.getByTestId('governance-line')
    await expect(line).toHaveText(/Checked by policy v1 · \d+ checks? · allowed/)
    await line.click()
    await expect(page).toHaveURL(/\/app\/requests\/[^/]+$/)
    const drawer = page.getByRole('dialog', { name: 'Request' })
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole('list', { name: 'Request trace' })).toBeVisible()
    await expect(drawer.locator('[data-verdict="allow"]').first()).toContainText('Allowed')
    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
    await expect(page).toHaveURL(/\/app\/requests$/)
  })

  test('a denied ask shows the governance line too', async ({ page }) => {
    await openApp(page)
    await ask(page, state().denied_kb, DENIED_Q)
    const denied = page.getByRole('alert', { name: 'Denied' })
    await expect(denied.getByTestId('governance-line')).toHaveText(/Checked by policy v1 · \d+ checks? · denied/)
  })
})

test.describe('A4 (c) Overview', () => {
  test('the blocked number opens the request list filtered to deny', async ({ page }) => {
    await openApp(page)
    await ask(page, state().denied_kb, DENIED_Q) // make sure at least one request was blocked
    await expect(page.getByRole('alert', { name: 'Denied' })).toBeVisible()
    await page.goto('/app')
    const blocked = page.getByTestId('tile-blocked')
    await expect(blocked).toBeVisible()
    await expect(page.getByTestId('tile-checked')).toBeVisible()
    const tileNumber = Number((await blocked.getByText(/^[\d,.\s]+$/).innerText()).replace(/\D/g, ''))
    expect(tileNumber).toBeGreaterThan(0)
    await blocked.click()
    await expect(page).toHaveURL(/\/app\/requests\?outcome=deny/)
    await expect(page.getByRole('radio', { name: 'Denied' })).toBeChecked()
    await expect(page.locator('tbody tr[data-outcome="deny"]').first()).toBeVisible()
    // Load every page of the filtered list, then the tile and the list must agree.
    const more = page.getByRole('button', { name: 'Load more' })
    while (await more.isVisible()) {
      const before = await page.locator('tbody tr').count()
      await more.click()
      await expect.poll(() => page.locator('tbody tr').count()).toBeGreaterThan(before)
    }
    await expect(page.locator('tbody tr:not([data-outcome="deny"])')).toHaveCount(0)
    await expect(page.locator('tbody tr[data-outcome="deny"]')).toHaveCount(tileNumber)
  })

  test('shows the numbers and the top deny reasons with plain titles', async ({ page }) => {
    await openApp(page)
    await ask(page, state().denied_kb, DENIED_Q)
    await expect(page.getByRole('alert', { name: 'Denied' })).toBeVisible()
    await page.goto('/app')
    for (const id of ['tile-checked', 'tile-blocked', 'tile-deny-rate', 'tile-budget']) await expect(page.getByTestId(id)).toBeVisible()
    await expect(page.getByRole('list', { name: 'Top deny reasons' })).toContainText('Knowledge base not allowed')
  })
})

test.describe('A4 (d) the command palette', () => {
  test('Cmd or Ctrl plus K jumps to a request id', async ({ page }) => {
    const id = await askAndGetRequestId(page, state().allowed_kb, ALLOWED_Q)
    await page.goto('/app/library')
    await expect(page.getByTestId('tenant-crumb')).toBeVisible()
    await page.keyboard.press('ControlOrMeta+k')
    const palette = page.getByRole('dialog', { name: 'Command palette' })
    await expect(palette).toBeVisible()
    await page.getByRole('combobox', { name: /Go to a screen or find a request id/ }).fill(id)
    await expect(palette.getByRole('option').first()).toContainText(id)
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(new RegExp(`/app/requests/${id}$`))
    await expect(page.getByRole('dialog', { name: 'Request' })).toContainText(id)
  })

  test('goes to a screen by name, and Escape closes it', async ({ page }) => {
    await openApp(page, '/app/library')
    await page.getByRole('button', { name: 'Open command palette' }).click()
    await page.getByRole('combobox').fill('system')
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/\/app\/system$/)
    await page.keyboard.press('ControlOrMeta+k')
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeHidden()
  })
})

test.describe('A4 (e) a deny shows its plain sentence and the policy field', () => {
  test('in Ask, in the request drawer and in the decision detail', async ({ page }) => {
    await openApp(page)
    await ask(page, state().denied_kb, DENIED_Q)
    const denied = page.getByRole('alert', { name: 'Denied' })
    const callout = denied.getByTestId('deny-callout')
    await expect(callout.getByTestId('deny-stage')).toContainText('Denied at Tenant policy')
    await expect(callout.getByTestId('deny-sentence')).toHaveText('The policy does not list this knowledge base.')
    await expect(callout.getByTestId('deny-policy-field')).toHaveText('allowed_kbs')
    await expect(callout.getByTestId('deny-policy-version')).toHaveText('1')

    await denied.getByTestId('governance-line').click()
    const drawer = page.getByRole('dialog', { name: 'Request' })
    await expect(drawer.getByTestId('deny-sentence')).toHaveText('The policy does not list this knowledge base.')
    await expect(drawer.getByTestId('deny-policy-field')).toHaveText('allowed_kbs')
    await expect(drawer.getByTestId('trace-deny-sentence')).toContainText('The policy does not list this knowledge base.')

    await drawer.getByRole('link', { name: /Open receipt/ }).last().click()
    const detail = page.getByRole('complementary', { name: 'Decision detail' })
    await expect(detail.getByTestId('deny-sentence')).toHaveText('The policy does not list this knowledge base.')
    await expect(detail.getByTestId('deny-policy-field')).toHaveText('allowed_kbs')
  })
})

test.describe('Requests page and the session menu', () => {
  test('console reads are left out unless "Include console views" is on', async ({ page }) => {
    await openApp(page)
    await page.goto('/app') // the Overview is a console view: it reads the log and leaves an audit.read request
    await expect(page.getByTestId('tile-checked')).toBeVisible()
    await page.goto('/app/requests?action=audit.read')
    await expect(page.getByText('No requests match these filters.')).toBeVisible()
    const toggle = page.getByLabel('Include console views')
    await expect(toggle).not.toBeChecked()
    await toggle.click()
    await expect(toggle).toBeChecked()
    await expect(page).toHaveURL(/console=1/)
    await expect(page.getByRole('table')).toBeVisible()
    await expect(page.locator('tbody tr').first()).toBeVisible()
  })

  test('the session menu shows who you are, the tenant and the scopes, and switches the theme', async ({ page }) => {
    await openApp(page)
    await page.getByRole('button', { name: 'Session menu' }).click()
    const identity = page.getByTestId('session-identity')
    await expect(identity).toContainText('e2e-user')
    await expect(identity).toContainText(state().tenant)
    await expect(identity).toContainText('audit:read')
    await page.getByRole('menuitemradio', { name: 'Dark' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.getByRole('button', { name: 'Session menu' }).click()
    await page.getByRole('menuitemradio', { name: 'Light' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  })

  test('an unknown request id says so in the drawer', async ({ browser }) => {
    const context = await browser.newContext({ storageState: 'e2e/.state/auth.json' })
    const page = await context.newPage()
    await page.goto('/app/requests/not-a-real-request-id')
    await expect(page.getByRole('dialog', { name: 'Request' })).toContainText('No request with this id was found for your tenant.')
    await context.close()
  })
})

test.describe('signed out', () => {
  test.use({ storageState: ANON })
  test('/how-it-works is public and /app/requests asks for sign-in', async ({ page }) => {
    await page.goto('/how-it-works')
    await expect(page.getByRole('heading', { level: 1, name: 'How a call is checked' })).toBeVisible()
    await page.goto('/app/requests')
    await expect(page).toHaveURL(/\/signin$/)
  })
})
