import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { indexReasons } from '@/lib/reasons'
import { SANDBOX_WORDS, isSandboxDeny, sandboxDetail, sandboxSummary } from '@/lib/sandbox'
import { CATALOGUE, decisionStep, sandboxEvent, sandboxStep, sandboxedRun } from '@/test/fixtures'
import { renderWithProviders } from '@/test/render'
import { RunSteps } from './run-steps'

const KINDS = ['start', 'exit', 'network_denied', 'file_denied', 'limit_hit', 'log'] as const

describe('RunSteps', () => {
  it('lists the gateway decisions and the sandbox events of a run in one rail, in the order given', () => {
    renderWithProviders(<RunSteps items={sandboxedRun('run-1').timeline} reasons={indexReasons(CATALOGUE)} />)
    const list = screen.getByRole('list', { name: 'Run steps' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows.map((r) => r.getAttribute('data-source'))).toEqual(['decision', 'sandbox', 'decision', 'sandbox', 'sandbox', 'decision', 'sandbox'])
    expect(rows.map((r) => r.getAttribute('data-kind'))).toEqual([null, 'start', null, 'network_denied', 'file_denied', null, 'exit'])
  })

  it('gives every sandbox kind its own word and its own icon, and the word is text, not color', () => {
    renderWithProviders(<RunSteps items={KINDS.map((kind) => sandboxStep({ id: kind, kind }))} />)
    const words = screen.getAllByTestId('sandbox-kind-word').map((w) => w.textContent)
    expect(words).toEqual(KINDS.map((k) => SANDBOX_WORDS[k]))
    expect(new Set(words).size).toBe(KINDS.length)
    const icons = screen.getAllByTestId('sandbox-kind-word').map((w) => w.previousElementSibling?.innerHTML)
    expect(new Set(icons).size).toBe(KINDS.length) // six different glyphs
    expect(icons.every((i) => i && i.length > 0)).toBe(true)
  })

  it('shows a blocked network call and a blocked file read as a deny state with a word, an icon and the detail', () => {
    renderWithProviders(<RunSteps items={[
      sandboxStep({ id: 'n', kind: 'network_denied', detail: { host: 'api.openai.com', port: 443 } }),
      sandboxStep({ id: 'f', kind: 'file_denied', detail: { path: '/var/lib/dpkg/status' } }),
      sandboxStep({ id: 'l', kind: 'log', detail: { message: 'ready' } }),
    ]} />)
    const rows = screen.getAllByRole('listitem')
    expect(rows.map((r) => r.getAttribute('data-tone'))).toEqual(['deny', 'deny', 'plain'])
    for (const row of rows.slice(0, 2)) {
      expect(within(row).getByText('Denied')).toBeInTheDocument()
      expect(row.querySelector('div.border-l-deny')).not.toBeNull() // the red bar of the deny anchor
    }
    expect(within(rows[0]!).getByTestId('sandbox-detail')).toHaveTextContent('Tried to reach api.openai.com:443. The sandbox may only reach the gateway.')
    expect(within(rows[1]!).getByTestId('sandbox-detail')).toHaveTextContent('Tried to read /var/lib/dpkg/status. The sandbox may only use its work directory.')
    expect(within(rows[2]!).queryByText('Denied')).not.toBeInTheDocument()
  })

  it('shows a gateway deny next to the sandbox events with the failing stage and the catalogue sentence', () => {
    renderWithProviders(<RunSteps items={sandboxedRun('run-1').timeline} reasons={indexReasons(CATALOGUE)} />)
    const sentence = screen.getByTestId('run-step-deny-sentence')
    expect(sentence).toHaveTextContent('Tenant policy.')
    expect(sentence).toHaveTextContent('The policy does not list this knowledge base.')
    expect(screen.getAllByText('Denied')).toHaveLength(3) // one gateway deny and two sandbox denies
  })

  it('marks a limit as a warning, not a deny', () => {
    renderWithProviders(<RunSteps items={[sandboxStep({ kind: 'limit_hit', detail: { limit: 'wall_seconds', value: 300 } })]} />)
    expect(screen.getByRole('listitem')).toHaveAttribute('data-tone', 'warn')
    expect(screen.getByTestId('sandbox-detail')).toHaveTextContent('Hit the wall seconds limit.')
  })

  it('says so when a run has no steps', () => {
    renderWithProviders(<RunSteps items={[]} />)
    expect(screen.getByText('No steps were recorded for this run.')).toBeInTheDocument()
  })

  it('shows a plain fallback sentence for a deny the catalogue does not know', () => {
    renderWithProviders(<RunSteps items={[decisionStep({ id: 'x', outcome: 'deny', stage: 'policy', reason: 'a_new_reason' })]} reasons={indexReasons(CATALOGUE)} />)
    expect(screen.getByTestId('run-step-deny-sentence')).toHaveTextContent('The gateway stopped this call.')
  })
})

describe('sandbox words', () => {
  it('knows which kinds are denials', () => {
    expect(KINDS.filter(isSandboxDeny)).toEqual(['network_denied', 'file_denied'])
  })

  it('writes a plain line for each kind, and copes with a detail that has nothing in it', () => {
    for (const kind of KINDS) expect(sandboxDetail(sandboxEvent({ kind, detail: {} })).length).toBeGreaterThan(5)
    expect(sandboxDetail(sandboxEvent({ kind: 'exit', detail: { code: 0 } }))).toBe('The agent finished (exit code 0).')
    expect(sandboxDetail(sandboxEvent({ kind: 'exit', detail: { code: 3 } }))).toBe('The agent stopped (exit code 3).')
    expect(sandboxDetail(sandboxEvent({ kind: 'exit', detail: { reason: 'wall_time_exceeded' } }))).toBe('The run ended: wall time exceeded.')
    expect(sandboxDetail(sandboxEvent({ kind: 'log', detail: { message: 'ready' } }))).toBe('ready')
  })

  it('does not print a field the event does not carry, or a nested value', () => {
    const line = sandboxDetail(sandboxEvent({ kind: 'network_denied', detail: { host: 'a.test', environment: { RUN_TOKEN: 'secret' } } }))
    expect(line).toBe('Tried to reach a.test. The sandbox may only reach the gateway.')
    expect(line).not.toContain('secret')
  })

  it('summarises what the sandbox stopped, and says nothing when it stopped nothing', () => {
    expect(sandboxSummary(sandboxedRun('r').sandbox_events)).toBe('1 network call blocked, 1 file access blocked')
    expect(sandboxSummary([sandboxEvent({ kind: 'network_denied' }), sandboxEvent({ kind: 'network_denied' }), sandboxEvent({ kind: 'file_denied' }), sandboxEvent({ kind: 'file_denied' })])).toBe('2 network calls blocked, 2 file accesses blocked')
    expect(sandboxSummary([sandboxEvent({ kind: 'start' }), sandboxEvent({ kind: 'exit' })])).toBeNull()
  })
})
