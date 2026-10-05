import type { Job } from '@/api/types'

/** What a document's latest ingest job says, in the words the Library shows. */
export type DocState = 'queued' | 'running' | 'ready' | 'failed'

export function docState(job: Job | undefined): DocState {
  if (!job) return 'ready' // an older document has no job: it was ingested before jobs existed
  if (job.status === 'queued') return 'queued'
  if (job.status === 'running') return 'running'
  if (job.status === 'succeeded') return 'ready'
  return 'failed'
}

export const DOC_STATE_WORD: Record<DocState, string> = { queued: 'Queued', running: 'Running', ready: 'Ready', failed: 'Failed' }

const SENTENCES: Record<string, string> = {
  unsupported_file: 'The file could not be read as a document.',
  object_missing: 'The stored file was not found. Upload it again.',
  stopped: 'The job was stopped.',
  lease_expired: 'The worker stopped before it finished, and no attempts were left.',
  internal_error: 'Something went wrong while ingesting this file.',
}

/** A plain sentence for a failed or dead job. A dead job also says how many attempts were made. */
export function failureSentence(job: Job): string {
  const base = (job.error_code && SENTENCES[job.error_code]) || 'The job failed.'
  return job.status === 'dead' ? `${base} It gave up after ${job.attempts} attempts.` : base
}

/** True while any job still has work to do. The Library polls only then. */
export function anyActive(jobs: readonly Job[] | undefined): boolean {
  return !!jobs?.some((j) => j.status === 'queued' || j.status === 'running')
}

/** The newest job per document of one knowledge base. `jobs` is newest first, as the API returns it. */
export function latestByDocument(jobs: readonly Job[], kb: string): Map<string, Job> {
  const out = new Map<string, Job>()
  for (const j of jobs) {
    if (j.kind !== 'ingest' || !j.resource?.startsWith(`${kb}/`)) continue
    const doc = j.resource.slice(kb.length + 1)
    if (!out.has(doc)) out.set(doc, j)
  }
  return out
}
