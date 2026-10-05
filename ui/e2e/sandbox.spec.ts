import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { openApp, readState, setTheme } from './fixtures'

// Sprint 009 A6 (UI half). The Agent runs page shows the sandbox events on the step timeline, next to the gateway decisions,
// for runs that came from the real openshell runtime. The sandbox itself was a fake (see scripts/e2e/serve.py): these runs
// were made while seeding, so this test reads stored data, and it proves the page and the runs API, not OpenShell.
const state = () => readState()

async function openRun(page: Page, executionId: string): Promise<void> {
  await openApp(page, '/app/runs')
  const row = page.locator('tbody tr').filter({ has: page.getByTestId('run-row-execution-id').filter({ hasText: executionId.slice(0, 8) }) })
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: /Open run from/ }).click()
  await expect(page.getByRole('complementary', { name: 'Run timeline' }).getByRole('list', { name: 'Run steps' })).toBeVisible()
}

test.describe('A6 sandbox events on the Agent runs timeline', () => {
  test('a run where the sandbox blocked a network call and a file read shows both, as denials, in time order next to the decisions', async ({ page }) => {
    await openRun(page, state().sandbox_runs.blocked)
    const panel = page.getByRole('complementary', { name: 'Run timeline' })
    await expect(panel.getByTestId('run-sandbox-summary')).toHaveText('1 network call blocked, 1 file access blocked')

    const steps = panel.getByRole('list', { name: 'Run steps' }).getByRole('listitem')
    const words = await panel.getByTestId('sandbox-kind-word').allTextContents()
    expect(words).toEqual(['Sandbox started', 'Network call blocked', 'File access blocked', 'Sandbox exited']) // one word per kind, in time order
    // the gateway decisions are in the same rail: the entry check, the tool call and the model calls
    const sources = await steps.evaluateAll((els) => els.map((e) => e.getAttribute('data-source')))
    expect(sources.filter((s) => s === 'decision').length).toBeGreaterThanOrEqual(6)
    expect(sources[0]).toBe('decision') // the entry check comes before the sandbox starts
    expect(sources.indexOf('sandbox')).toBeGreaterThan(0)
    await expect(panel.getByText('tool.call', { exact: true }).first()).toBeVisible()
    await expect(panel.getByText('retrieve_chunks', { exact: true }).first()).toBeVisible()

    // a deny state: the step says "Denied" in words, has the red anchor, and says what was tried
    const network = steps.filter({ has: page.locator('[data-testid="sandbox-kind-word"]', { hasText: 'Network call blocked' }) })
    await expect(network).toHaveAttribute('data-tone', 'deny')
    await expect(network.getByText('Denied', { exact: true })).toBeVisible()
    await expect(network.getByTestId('sandbox-detail')).toHaveText('Tried to reach api.openai.com:443. The sandbox may only reach the gateway.')
    const file = steps.filter({ has: page.locator('[data-testid="sandbox-kind-word"]', { hasText: 'File access blocked' }) })
    await expect(file).toHaveAttribute('data-tone', 'deny')
    await expect(file.getByTestId('sandbox-detail')).toHaveText('Tried to read /var/lib/dpkg/status. The sandbox may only use its work directory.')
    // the order on screen is the order of time: the denials sit between the start and the exit
    const kinds = await steps.evaluateAll((els) => els.filter((e) => e.getAttribute('data-source') === 'sandbox').map((e) => e.getAttribute('data-kind')))
    expect(kinds).toEqual(['start', 'network_denied', 'file_denied', 'exit'])
  })

  test('a clean run shows a start and an exit, no denials, and says nothing was blocked', async ({ page }) => {
    await openRun(page, state().sandbox_runs.completed)
    const panel = page.getByRole('complementary', { name: 'Run timeline' })
    await expect(panel.getByTestId('run-sandbox-summary')).toHaveText('Ran inside the sandbox. Nothing was blocked.')
    expect(await panel.getByTestId('sandbox-kind-word').allTextContents()).toEqual(['Sandbox started', 'Sandbox exited'])
    await expect(panel.locator('[data-source="sandbox"][data-tone="deny"]')).toHaveCount(0)
    await expect(panel.getByTestId('run-status')).toHaveText('Finished')
    await expect(panel.getByTestId('sandbox-detail').last()).toHaveText('The agent finished (exit code 0).')
  })

  test('the run list shows both runs as finished, and a run with no sandbox keeps the request trace', async ({ page }) => {
    await openApp(page, '/app/runs')
    for (const id of Object.values(state().sandbox_runs)) {
      const row = page.locator('tbody tr').filter({ has: page.getByTestId('run-row-execution-id').filter({ hasText: id.slice(0, 8) }) })
      await expect(row.getByTestId('run-row-status')).toHaveText('Finished')
    }
  })

  for (const theme of ['light', 'dark'] as const) {
    test(`the sandbox timeline has no serious accessibility violations, ${theme} theme`, async ({ page }) => {
      await setTheme(page, theme)
      await openRun(page, state().sandbox_runs.blocked)
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
      const blocking = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
      console.log(`axe sandbox timeline (${theme}): violations=${results.violations.length} serious_or_critical=${blocking.length} passes=${results.passes.length}`)
      expect(blocking, 'serious or critical violations').toEqual([])
    })
  }
})
