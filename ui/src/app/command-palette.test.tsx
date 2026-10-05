import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import { api } from '@/api/endpoints'
import type { RequestSummary } from '@/api/types'
import { renderWithProviders } from '@/test/render'
import { CommandPalette } from './command-palette'
import { buildPaletteItems, looksLikeRequestId } from './palette-items'

const recent = (id: string, outcome: 'allow' | 'deny' = 'allow'): RequestSummary => ({
  request_id: id, started_at: '2026-09-14T09:30:12.000Z', principal: null, checks: 1, outcome, first_deny: null, policy_version: 1,
})

afterEach(() => vi.restoreAllMocks())

describe('buildPaletteItems', () => {
  it('lists every screen with no text, and filters by label', () => {
    const all = buildPaletteItems('')
    expect(all.map((i) => i.label)).toEqual(expect.arrayContaining(['Overview', 'Walkthrough', 'Requests', 'Ask', 'System']))
    expect(buildPaletteItems('req').map((i) => i.label)).toContain('Requests')
    expect(buildPaletteItems('walk').filter((i) => i.group === 'Go to').map((i) => i.label)).toEqual(['Walkthrough'])
  })

  it('offers to open a typed request id, and lists matching recent requests first', () => {
    const items = buildPaletteItems('abc123', [recent('abc123-0001'), recent('zzz')])
    expect(items[0]?.label).toBe('abc123-0001')
    expect(items[0]?.to).toBe('/app/requests/abc123-0001')
    expect(items.find((i) => i.label === 'Open request abc123')?.to).toBe('/app/requests/abc123')
    expect(items.some((i) => i.label === 'zzz')).toBe(false)
  })

  it('does not treat a short word or a sentence as a request id', () => {
    expect(looksLikeRequestId('ab')).toBe(false)
    expect(looksLikeRequestId('two words')).toBe(false)
    expect(looksLikeRequestId('9f2c4a7e-1b')).toBe(true)
  })
})

const HOSTILE = ['../x', '<script>alert(1)</script>', '%2F..%2F']

describe('hostile input', () => {
  it.each(HOSTILE)('%s is not a request id, and no item leaves /app/requests/ or a known screen', (text) => {
    expect(looksLikeRequestId(text)).toBe(false)
    const screens = new Set(buildPaletteItems('').map((i) => i.to))
    for (const item of buildPaletteItems(text, [recent('abc-0001')])) {
      if (screens.has(item.to)) continue
      expect(item.to.startsWith('/app/requests/')).toBe(true)
      const tail = item.to.slice('/app/requests/'.length)
      expect(tail).not.toMatch(/[/\\]|\.\.\//)
      expect(decodeURIComponent(tail)).not.toMatch(/[/\\<>]/)
    }
  })

  it('encodes a listed id that holds reserved characters, so it stays one path segment', () => {
    const item = buildPaletteItems('b#c', [recent('a?b#c/../d')]).find((i) => i.group === 'Requests')
    expect(item?.to).toBe('/app/requests/a%3Fb%23c%2F..%2Fd')
  })
})

describe('CommandPalette', () => {
  it.each(HOSTILE)('typing %s and pressing Enter never navigates outside /app/requests/', async (text) => {
    vi.spyOn(api, 'requests').mockResolvedValue({ items: [], next_cursor: null })
    renderWithProviders(<Harness />, { route: '/app' })
    await screen.findByRole('dialog')
    await userEvent.type(screen.getByRole('combobox'), text)
    await userEvent.keyboard('{Enter}')
    const where = screen.getByTestId('where').textContent ?? ''
    expect(where === '/app' || where.startsWith('/app/requests/')).toBe(true)
    expect(where).not.toContain('..')
    expect(where).not.toContain('<')
  })

  function Where() { const l = useLocation(); return <p data-testid="where">{l.pathname}</p> }
  function Harness() {
    const [open, setOpen] = useState(true)
    return <><CommandPalette open={open} onOpenChange={setOpen} /><Routes><Route path="*" element={<Where />} /></Routes></>
  }

  it('is a combobox over a listbox, named for what it does', async () => {
    vi.spyOn(api, 'requests').mockResolvedValue({ items: [], next_cursor: null })
    renderWithProviders(<Harness />)
    expect(await screen.findByRole('dialog', { name: 'Command palette' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /Go to a screen or find a request id/ })).toHaveFocus()
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(screen.getAllByRole('option').length).toBeGreaterThan(5)
  })

  it('goes to a screen with the arrow keys and Enter', async () => {
    vi.spyOn(api, 'requests').mockResolvedValue({ items: [], next_cursor: null })
    renderWithProviders(<Harness />)
    await screen.findByRole('dialog')
    await userEvent.type(screen.getByRole('combobox'), 'requests')
    await userEvent.keyboard('{Enter}')
    expect(screen.getByTestId('where')).toHaveTextContent('/app/requests')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('jumps to a request id', async () => {
    vi.spyOn(api, 'requests').mockResolvedValue({ items: [recent('3f9a-77c1-aa')], next_cursor: null })
    renderWithProviders(<Harness />)
    await screen.findByRole('dialog')
    await userEvent.type(screen.getByRole('combobox'), '3f9a-77c1-aa')
    expect(await screen.findByRole('option', { name: /3f9a-77c1-aa/ })).toBeInTheDocument()
    await userEvent.keyboard('{Enter}')
    expect(screen.getByTestId('where')).toHaveTextContent('/app/requests/3f9a-77c1-aa')
  })

  it('opens a typed id even when it is not in the recent list', async () => {
    vi.spyOn(api, 'requests').mockResolvedValue({ items: [], next_cursor: null })
    renderWithProviders(<Harness />)
    await screen.findByRole('dialog')
    await userEvent.type(screen.getByRole('combobox'), 'unknown-id-9')
    await userEvent.keyboard('{Enter}')
    expect(screen.getByTestId('where')).toHaveTextContent('/app/requests/unknown-id-9')
  })

  it('closes with Escape', async () => {
    vi.spyOn(api, 'requests').mockResolvedValue({ items: [], next_cursor: null })
    renderWithProviders(<Harness />)
    await screen.findByRole('dialog')
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
