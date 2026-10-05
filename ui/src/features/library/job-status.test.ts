import { describe, expect, it } from 'vitest'
import type { Job } from '@/api/types'
import { anyActive, docState, failureSentence, latestByDocument } from './job-status'

const job = (over: Partial<Job> = {}): Job => ({
  id: 'j', kind: 'ingest', status: 'queued', attempts: 0, max_attempts: 5, progress: { done: 0, total: 0 }, error_code: null,
  resource: 'legal/a.md', execution_id: null, created_at: '2026-09-14T09:30:00Z', updated_at: '2026-09-14T09:30:00Z', ...over,
})

describe('job status', () => {
  it('maps a job to what the Library says', () => {
    expect(docState(undefined)).toBe('ready')
    expect(docState(job({ status: 'queued' }))).toBe('queued')
    expect(docState(job({ status: 'running' }))).toBe('running')
    expect(docState(job({ status: 'succeeded' }))).toBe('ready')
    expect(docState(job({ status: 'failed' }))).toBe('failed')
    expect(docState(job({ status: 'dead' }))).toBe('failed')
  })

  it('gives a plain sentence for a failure, and the attempts for a dead job', () => {
    expect(failureSentence(job({ status: 'failed', error_code: 'unsupported_file' }))).toBe('The file could not be read as a document.')
    expect(failureSentence(job({ status: 'dead', error_code: 'internal_error', attempts: 5 }))).toBe('Something went wrong while ingesting this file. It gave up after 5 attempts.')
    expect(failureSentence(job({ status: 'failed', error_code: 'new_code' }))).toBe('The job failed.')
  })

  it('polls only while a job is queued or running', () => {
    expect(anyActive(undefined)).toBe(false)
    expect(anyActive([job({ status: 'succeeded' }), job({ status: 'dead' })])).toBe(false)
    expect(anyActive([job({ status: 'succeeded' }), job({ status: 'running' })])).toBe(true)
    expect(anyActive([job({ status: 'queued' })])).toBe(true)
  })

  it('keeps the newest job per document of the chosen knowledge base', () => {
    const newest = job({ id: 'new', status: 'running', resource: 'legal/a.md' })
    const older = job({ id: 'old', status: 'failed', resource: 'legal/a.md' })
    const other = job({ id: 'other', resource: 'default/a.md' })
    const agent = job({ id: 'run', kind: 'agent_run', resource: 'legal' })
    const map = latestByDocument([newest, older, other, agent], 'legal')
    expect([...map.keys()]).toEqual(['a.md'])
    expect(map.get('a.md')?.id).toBe('new')
  })
})
