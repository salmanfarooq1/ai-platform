import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import { REASONS_KEY } from '@/lib/reasons'
import { CATALOGUE, decision, detail } from '@/test/fixtures'
import { renderWithProviders, testClient } from '@/test/render'
import { runDuration, runStatusWord } from './run-status'
import RunsPage from './runs-page'

const FINISHED = '3f1c2d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'
const RUNNING = '9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d'

const runs = [
  decision({ id: 'run-1', request_id: 'req-1', action: 'agent.run', resource: null, execution_id: FINISHED, run_status: 'succeeded' }),
  decision({ id: 'run-2', request_id: 'req-2', action: 'agent.run', resource: null, execution_id: RUNNING, run_status: 'running' }),
  decision({ id: 'run-3', request_id: 'req-3', action: 'agent.run', resource: null, execution_id: 'c0ffee00-1111-4222-8333-444455556666', run_status: null }),
  decision({ id: 'run-4', request_id: 'req-4', action: 'agent.run', resource: null, outcome: 'deny', stage: 'guardrails', reason: 'query_blocked', execution_id: null }),
]

afterEach(() => vi.restoreAllMocks())

const NO_RUNS = { items: [], next_cursor: null }
const run = (over: Record<string, unknown>) => ({
  job_id: 'job-1', status: 'succeeded', error_code: null, created_at: '2026-09-14T09:30:00Z', started_at: '2026-09-14T09:30:01Z',
  finished_at: '2026-09-14T09:30:04.200Z', result: null, decisions_url: '/v1/decisions', ...over,
}) as never

function page(route = '/app/runs') {
  if (!vi.isMockFunction(api.agentRuns)) vi.spyOn(api, 'agentRuns').mockResolvedValue(NO_RUNS)
  const client = testClient()
  client.setQueryData(REASONS_KEY, CATALOGUE)
  return renderWithProviders(<RunsPage />, { client, route })
}

describe('RunsPage', () => {
  it('says what each run status means in words', () => {
    expect(runStatusWord('queued')).toBe('Queued')
    expect(runStatusWord('running')).toBe('Running')
    expect(runStatusWord('succeeded')).toBe('Finished')
    expect(runStatusWord('failed')).toBe('Failed')
    expect(runStatusWord('stopped')).toBe('Stopped')
    expect(runStatusWord(null)).toBe('Not tracked')
    expect(runStatusWord(undefined)).toBe('Not tracked')
    expect(runStatusWord('something-new')).toBe('Not tracked')
  })

  it('lists each run with its execution id and the status the runtime reports', async () => {
    const decisions = vi.spyOn(api, 'decisions').mockResolvedValue({ items: runs, next_cursor: null })
    page()
    const rows = await screen.findAllByRole('row')
    expect(decisions).toHaveBeenCalledWith({ action: 'agent.run' }, undefined)
    const header = within(rows[0]!).getAllByRole('columnheader').map((h) => h.textContent)
    expect(header).toEqual(['Started', 'Verdict', 'Status', 'Duration', 'Execution id', 'Principal', 'Request id'])

    const cells = (row: HTMLElement) => ({
      status: within(row).getByTestId('run-row-status').textContent,
      id: within(row).getByTestId('run-row-execution-id').textContent,
    })
    expect(cells(rows[1]!)).toEqual({ status: 'Finished', id: FINISHED.slice(0, 8) })
    expect(cells(rows[2]!)).toEqual({ status: 'Running', id: RUNNING.slice(0, 8) })
    expect(cells(rows[3]!)).toEqual({ status: 'Not tracked', id: 'c0ffee00' })
    expect(cells(rows[4]!)).toEqual({ status: 'Not tracked', id: 'None' }) // refused before it got an id to show
    expect(within(rows[1]!).getByTestId('run-row-execution-id')).toHaveAttribute('title', FINISHED)
  })

  it('shows the full execution id and the status of the selected run next to its steps', async () => {
    vi.spyOn(api, 'decisions').mockResolvedValue({ items: runs, next_cursor: null })
    const one = vi.spyOn(api, 'decision').mockResolvedValue(detail({ id: 'run-2', execution_id: RUNNING, run_status: 'running', action: 'agent.run' }))
    page('/app/runs?run=run-2')
    const panel = await screen.findByRole('complementary', { name: 'Run timeline' })
    expect(await within(panel).findByTestId('run-status')).toHaveTextContent('Running')
    expect(within(panel).getByText(RUNNING)).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Copy execution id' })).toBeInTheDocument()
    expect(one).toHaveBeenCalledWith('run-2')
  })

  it('a run with no execution id or status still renders honestly', async () => {
    vi.spyOn(api, 'decisions').mockResolvedValue({ items: runs, next_cursor: null })
    vi.spyOn(api, 'decision').mockResolvedValue(detail({ id: 'run-4', execution_id: null, run_status: null }))
    page('/app/runs?run=run-4')
    const panel = await screen.findByRole('complementary', { name: 'Run timeline' })
    expect(await within(panel).findByTestId('run-status')).toHaveTextContent('Not tracked')
    expect(within(panel).queryByRole('button', { name: 'Copy execution id' })).not.toBeInTheDocument()
  })

  it('opens a run when its time is clicked', async () => {
    vi.spyOn(api, 'decisions').mockResolvedValue({ items: runs, next_cursor: null })
    vi.spyOn(api, 'decision').mockResolvedValue(detail({ id: 'run-1', execution_id: FINISHED, run_status: 'succeeded' }))
    page()
    const rows = await screen.findAllByRole('row')
    await userEvent.click(within(rows[1]!).getByRole('button', { name: /Open run from/ }))
    expect(await screen.findByTestId('run-status')).toHaveTextContent('Finished')
  })

  it('reads each run status and duration from the runs endpoint, and polls it only while a run is active', async () => {
    vi.spyOn(api, 'decisions').mockResolvedValue({ items: runs, next_cursor: null })
    const endpoint = vi.spyOn(api, 'agentRuns').mockResolvedValue({
      items: [
        run({ execution_id: FINISHED, status: 'succeeded' }),
        run({ execution_id: RUNNING, status: 'queued', started_at: null, finished_at: null }),
        run({ execution_id: 'c0ffee00-1111-4222-8333-444455556666', status: 'failed', error_code: 'agent_run_failed' }),
      ],
      next_cursor: null,
    })
    page()
    await screen.findAllByRole('row')
    const rows = screen.getAllByRole('row')
    const cell = (i: number, id: string) => within(rows[i]!).getByTestId(id).textContent
    expect([cell(1, 'run-row-status'), cell(1, 'run-row-duration')]).toEqual(['Finished', '3.2 s'])
    expect([cell(2, 'run-row-status'), cell(2, 'run-row-duration')]).toEqual(['Queued', 'None'])
    expect(cell(3, 'run-row-status')).toBe('Failed')  // the decision said nothing: the runs endpoint knows
    expect(cell(4, 'run-row-duration')).toBe('None')   // refused before it started: no run, no time
    expect(endpoint).toHaveBeenCalledTimes(1)
  })

  it('writes a duration in plain units', () => {
    expect(runDuration('2026-09-14T09:30:00Z', '2026-09-14T09:30:03.200Z')).toBe('3.2 s')
    expect(runDuration('2026-09-14T09:30:00Z', '2026-09-14T09:30:42Z')).toBe('42 s')
    expect(runDuration('2026-09-14T09:30:00Z', '2026-09-14T09:35:00Z')).toBe('5 min')
    expect(runDuration('2026-09-14T09:30:00Z', null)).toBe('Running')
    expect(runDuration(null, null)).toBe('None')
  })
})
