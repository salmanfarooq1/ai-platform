import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, type Page } from '@playwright/test'

const HERE = path.dirname(fileURLToPath(import.meta.url))

export interface E2EState {
  api_key: string
  principal_id: string
  tenant: string
  allowed_kb: string
  denied_kb: string
  preview: boolean
  base_url: string
}

/** serve.py writes the seeded key here. The directory is gitignored. */
export function readState(name = 'state.json'): E2EState {
  return JSON.parse(fs.readFileSync(path.resolve(HERE, '.state', name), 'utf8')) as E2EState
}

export async function signIn(page: Page, key = readState().api_key): Promise<void> {
  await page.goto('/signin')
  await page.getByLabel('API key').fill(key)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/ask$/)
}

export async function setTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.addInitScript((t) => { try { localStorage.setItem('theme', t) } catch { /* storage blocked */ } }, theme)
}

export async function ask(page: Page, kb: string, question: string): Promise<void> {
  await page.getByRole('combobox', { name: 'Knowledge base' }).fill(kb)
  await page.getByRole('textbox', { name: 'Question' }).fill(question)
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
}

/** Open an app page with the session saved by auth.setup.ts. */
export async function openApp(page: Page, route = '/app/ask'): Promise<void> {
  await page.goto(route)
  await expect(page.getByTestId('tenant-crumb')).toBeVisible()
}
