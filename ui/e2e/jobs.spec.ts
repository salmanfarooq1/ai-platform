import { expect, test } from '@playwright/test'
import { ask, readState, signIn } from './fixtures'

const state = () => readState()
const ANON = { cookies: [], origins: [] }

// Sprint 007 A6. The upload returns at once ("Queued"), a worker ingests the file, the Library follows the job to
// "Ready", and then a question cites the new document. Real API, real Postgres and Redis, fake providers.
test.describe('A6 a document goes from upload to a cited answer', () => {
  test.use({ storageState: ANON })

  test('upload, watch the Library reach Ready, then ask a question that cites it', async ({ page }) => {
    await signIn(page, state().writer_key)
    await page.goto('/app/library')
    await expect(page.getByTestId('tenant-crumb')).toBeVisible()

    await page.getByRole('button', { name: 'Add documents' }).first().click()
    const dialog = page.getByRole('dialog', { name: 'Add documents' })
    await dialog.getByLabel('File').setInputFiles({
      name: 'incident-plan.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from('# Incident response\n\nThe incident response plan must be reviewed every ninety days by the security officer.\n'),
    })
    await dialog.getByRole('button', { name: 'Upload' }).click()
    await expect(dialog.getByRole('status')).toContainText('Queued') // it returned at once: the worker has not been waited for
    await dialog.getByText('Close', { exact: true }).click()

    const row = page.getByRole('row', { name: /incident-plan\.md/ })
    await expect(row).toBeVisible()
    await expect(row.getByTestId('doc-status')).toHaveText(/Ready/) // retrying assertion: it follows queued, running, ready
    await expect(row).toContainText(/\d/) // the passages are counted once it is in the registry

    await page.goto('/app/ask')
    await ask(page, state().allowed_kb, 'How often must the incident response plan be reviewed?')
    const answer = page.getByRole('region', { name: 'Answer' })
    await expect(answer).toContainText('ninety days')
    await expect(answer.getByRole('region', { name: 'Evidence' })).toContainText('incident-plan.md')
  })
})
