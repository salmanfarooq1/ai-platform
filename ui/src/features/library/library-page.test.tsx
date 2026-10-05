import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import type { Job, PlatformConfig } from '@/api/types'
import { renderWithProviders } from '@/test/render'
import LibraryPage from './library-page'

vi.mock('@/app/session', () => ({ useSession: () => ({ can: () => true }) }))

const config = { namespaces: { legal: 'Legal' }, confidence_floor: 0.5, max_query_length: 1000, daily_token_budget: 1, rate_limit_rpm: 1, rate_limit_window_seconds: 60, reranker_enabled: false, agent_defaults: { max_iterations: 1, enable_verifier: false, max_verify_retries: 0 } } as PlatformConfig
const doc = (id: string) => ({ document_id: id, namespace: 'legal', source_filename: id, chunk_count: 4, content_hash: 'a'.repeat(64), last_ingested_at: '2026-09-14T09:30:00Z' })
const job = (over: Partial<Job>): Job => ({
  id: 'j', kind: 'ingest', status: 'queued', attempts: 0, max_attempts: 5, progress: { done: 0, total: 0 }, error_code: null,
  resource: 'legal/new.md', execution_id: null, created_at: '2026-09-14T09:30:00Z', updated_at: '2026-09-14T09:30:00Z', ...over,
})

afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); localStorage.clear() })

function setup(jobs: Job[], docs = [doc('old.md')]) {
  vi.spyOn(api, 'config').mockResolvedValue(config)
  const documents = vi.spyOn(api, 'documents').mockResolvedValue(docs)
  const list = vi.spyOn(api, 'jobs').mockResolvedValue({ items: jobs, next_cursor: null })
  renderWithProviders(<LibraryPage />)
  return { documents, list }
}

const statusOf = (name: string) => within(screen.getByText(name).closest('tr') as HTMLElement).getByTestId('doc-status')

describe('LibraryPage ingest status', () => {
  it('shows a queued document that is not in the registry yet, and a ready one', async () => {
    const { list } = setup([job({ status: 'queued' })])
    await screen.findByText('new.md')
    expect(list).toHaveBeenCalledWith({ kind: 'ingest' })
    expect(statusOf('new.md')).toHaveTextContent('Queued')
    expect(statusOf('old.md')).toHaveTextContent('Ready') // an older document has no job
  })

  it('shows how far a running job is', async () => {
    setup([job({ status: 'running', progress: { done: 3, total: 10 } })])
    await screen.findByText('new.md')
    expect(statusOf('new.md')).toHaveTextContent('Running')
    const bar = within(statusOf('new.md')).getByRole('progressbar', { name: 'Ingest progress' })
    expect(bar).toHaveAttribute('aria-valuenow', '3')
    expect(bar).toHaveAttribute('aria-valuemax', '10')
    expect(statusOf('new.md')).toHaveTextContent('3 of 10')
  })

  it('shows the error code and a plain sentence for a failed job and for a dead one', async () => {
    setup([
      job({ id: 'a', status: 'failed', error_code: 'unsupported_file', resource: 'legal/bad.md' }),
      job({ id: 'b', status: 'dead', error_code: 'internal_error', attempts: 5, resource: 'legal/dead.md' }),
    ])
    await screen.findByText('bad.md')
    expect(statusOf('bad.md')).toHaveTextContent('Failed')
    expect(statusOf('bad.md')).toHaveTextContent('The file could not be read as a document.')
    expect(statusOf('bad.md')).toHaveTextContent('unsupported_file')
    expect(statusOf('dead.md')).toHaveTextContent('It gave up after 5 attempts.')
  })

  it('a document whose latest job succeeded is Ready', async () => {
    setup([job({ status: 'succeeded', resource: 'legal/old.md' })])
    await screen.findByText('old.md')
    expect(statusOf('old.md')).toHaveTextContent('Ready')
  })

  it('polls every 2 seconds while a job is active and stops when none is', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config)
    vi.spyOn(api, 'documents').mockResolvedValueOnce([doc('old.md')]).mockResolvedValue([doc('old.md'), doc('new.md')]) // the registry has it once the job ends
    const list = vi.spyOn(api, 'jobs')
      .mockResolvedValueOnce({ items: [job({ status: 'running', progress: { done: 1, total: 4 } })], next_cursor: null })
      .mockResolvedValue({ items: [job({ status: 'succeeded' })], next_cursor: null })
    renderWithProviders(<LibraryPage />)
    await screen.findByText('new.md')
    expect(list).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2), { timeout: 4000 }) // the 2 s poll
    await waitFor(() => expect(statusOf('new.md')).toHaveTextContent('Ready'))
    await new Promise((r) => setTimeout(r, 2600))
    expect(list).toHaveBeenCalledTimes(2) // nothing is active: no more polling
  }, 15000)

  it('reads the registry again when the last job ends', async () => {
    const { documents } = setup([job({ status: 'running' })])
    await screen.findByText('new.md')
    const before = documents.mock.calls.length
    vi.mocked(api.jobs).mockResolvedValue({ items: [job({ status: 'succeeded' })], next_cursor: null })
    await waitFor(() => expect(documents.mock.calls.length).toBeGreaterThan(before), { timeout: 5000 })
  }, 15000)
})
