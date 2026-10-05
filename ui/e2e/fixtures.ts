import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, type Page } from '@playwright/test'

const HERE = path.dirname(fileURLToPath(import.meta.url))

export interface E2EState {
  api_key: string
  /** A key that may also write (kb:write), for the upload test. */
  writer_key: string
  principal_id: string
  tenant: string
  allowed_kb: string
  denied_kb: string
  preview: boolean
  base_url: string
  /** Two sandboxed runs made while seeding (a fake sandbox): one clean, one where the sandbox blocked a network call and a file read. */
  sandbox_runs: { completed: string; blocked: string }
}

/** serve.py writes the seeded key here. The directory is gitignored. */
export function readState(name = 'state.json'): E2EState {
  return JSON.parse(fs.readFileSync(path.resolve(HERE, '.state', name), 'utf8')) as E2EState
}

/** `first` is true for a browser that has never signed in: it lands on the walkthrough. Later sign-ins land on the Overview. */
export async function signIn(page: Page, key = readState().api_key, { first = true }: { first?: boolean } = {}): Promise<void> {
  await page.goto('/signin')
  await page.getByLabel('API key').fill(key)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  // A new browser opens the walkthrough first. After that, sign-in opens the Overview.
  await expect(page).toHaveURL(first ? /\/app\/walkthrough$/ : /\/app$/)
}

export async function setTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.addInitScript((t) => { try { localStorage.setItem('theme', t) } catch { /* storage blocked */ } }, theme)
}

export async function ask(page: Page, kb: string, question: string): Promise<void> {
  const field = page.getByRole('combobox', { name: 'Knowledge base' })
  // The page fills in the first allowed knowledge base when its config call returns. A person sees that before typing,
  // so wait for it. Without this, Playwright's focus, select and insert can straddle that re-render and double the text.
  await expect(field).not.toHaveValue('')
  await field.fill(kb)
  await page.getByRole('textbox', { name: 'Question' }).fill(question)
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
}

/** Open an app page with the session saved by auth.setup.ts. */
export async function openApp(page: Page, route = '/app/ask'): Promise<void> {
  await page.goto(route)
  await expect(page.getByTestId('tenant-crumb')).toBeVisible()
}
