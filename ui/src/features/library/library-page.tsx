import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MagnifyingGlass, UploadSimple } from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '@/api/endpoints'
import { useSession } from '@/app/session'
import { CopyValue } from '@/components/governance/copy-value'
import { EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/governance/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { formatNumber, formatTime } from '@/lib/utils'
import { UploadDialog } from './upload-dialog'
import { anyActive, DOC_STATE_WORD, docState, failureSentence, latestByDocument } from './job-status'
import type { DocumentRow, Job } from '@/api/types'

const POLL_MS = 2000

interface Row { doc: DocumentRow; job?: Job }

/** The ingest progress of one document: a word, and for a running job how far it is. */
function StatusCell({ job }: { job?: Job }) {
  const state = docState(job)
  const total = job?.progress.total ?? 0
  const done = job?.progress.done ?? 0
  return (
    <div data-testid="doc-status" data-state={state}>
      <span className={state === 'failed' ? 'text-deny' : state === 'ready' ? 'text-allow' : 'text-fg-secondary'}>{DOC_STATE_WORD[state]}</span>
      {state === 'running' && total > 0 ? (
        <div className="mt-1 flex items-center gap-2">
          <div role="progressbar" aria-label="Ingest progress" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} className="h-1 w-24 rounded-sm bg-muted">
            <div className="h-1 rounded-sm bg-seal" style={{ width: `${Math.round((done / total) * 100)}%` }} />
          </div>
          <span className="tabular text-footnote text-fg-secondary">{done} of {total}</span>
        </div>
      ) : null}
      {state === 'failed' && job ? <p className="mt-0.5 text-footnote text-fg-secondary">{failureSentence(job)} <span className="mono">{job.error_code}</span></p> : null}
    </div>
  )
}

const PAGE = 10

export default function LibraryPage() {
  const { can } = useSession()
  const qc = useQueryClient()
  const config = useQuery({ queryKey: ['config'], queryFn: api.config, retry: false, staleTime: 300_000 })
  const kbs = Object.keys(config.data?.namespaces ?? {})
  const [kb, setKb] = useState(() => { try { return localStorage.getItem('collection') ?? '' } catch { return '' } })
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)

  useEffect(() => { if (kbs.length > 0 && !kbs.includes(kb)) setKb(kbs[0] ?? '') }, [kbs, kb])
  useEffect(() => { setPage(1) }, [filter, kb])

  const docs = useQuery({ queryKey: ['documents', kb], queryFn: () => api.documents(kb), enabled: !!kb, retry: false })
  // Ingestion is a job: poll the jobs every 2 s while any is queued or running, and stop when none is.
  const jobs = useQuery({
    queryKey: ['jobs', 'ingest'],
    queryFn: () => api.jobs({ kind: 'ingest' }),
    enabled: !!kb,
    retry: false,
    refetchInterval: (q) => (anyActive(q.state.data?.items) ? POLL_MS : false),
  })
  const active = anyActive(jobs.data?.items)
  const wasActive = useRef(false)
  useEffect(() => {
    // When the last job ends, the registry has a new document: read it.
    if (wasActive.current && !active) void qc.invalidateQueries({ queryKey: ['documents', kb] })
    wasActive.current = active
  }, [active, kb, qc])

  const rows = useMemo<Row[]>(() => {
    const f = filter.trim().toLowerCase()
    const latest = latestByDocument(jobs.data?.items ?? [], kb)
    const registry = docs.data ?? []
    const known = new Set(registry.map((d) => d.document_id))
    // Documents still being ingested are not in the registry yet: show them from their job.
    const pending: DocumentRow[] = [...latest.entries()]
      .filter(([id, j]) => !known.has(id) && j.status !== 'succeeded')
      .map(([id]) => ({ document_id: id, namespace: kb, source_filename: id, chunk_count: 0 }))
    const all = [...pending, ...registry].map((doc) => ({ doc, job: latest.get(doc.document_id) }))
    return f ? all.filter(({ doc }) => (doc.source_filename ?? doc.document_id).toLowerCase().includes(f)) : all
  }, [docs.data, jobs.data, filter, kb])
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const visible = rows.slice((page - 1) * PAGE, page * PAGE)
  const canWrite = can('kb:write')

  return (
    <div>
      <PageHeader
        title="Library"
        actions={
          <Button onClick={() => setOpen(true)} disabled={!canWrite || !kb} title={canWrite ? undefined : 'This session cannot add documents'}>
            <UploadSimple size={16} aria-hidden="true" /> Add documents
          </Button>
        }
      >
        Documents ingested into a knowledge base.{!canWrite ? ' This session is read-only.' : ''}
      </PageHeader>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-footnote text-fg-secondary">
          Knowledge base
          <Select aria-label="Knowledge base" value={kb} onChange={(e) => { setKb(e.target.value); try { localStorage.setItem('collection', e.target.value) } catch { /* optional */ } }} disabled={kbs.length === 0}>
            {kbs.map((k) => <option key={k} value={k}>{k}</option>)}
          </Select>
        </label>
        <div className="relative">
          <MagnifyingGlass size={16} aria-hidden="true" className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-secondary" />
          <Input aria-label="Search documents" type="search" placeholder="Search documents" className="w-64 pl-8" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
      </div>

      {config.error ? <ErrorState error={config.error} onRetry={() => void config.refetch()} title="Could not load knowledge bases." /> : null}
      {docs.isLoading || config.isLoading ? <TableSkeleton rows={5} cols={4} /> : null}
      {docs.error ? <ErrorState error={docs.error} onRetry={() => void docs.refetch()} title="Could not load documents." /> : null}
      {docs.data && rows.length === 0 && !filter.trim() ? (
        <EmptyState title="No documents in this knowledge base." action={canWrite ? <Button size="sm" onClick={() => setOpen(true)}>Add documents</Button> : undefined}>
          Add a file and it is split into passages that Ask can cite.
        </EmptyState>
      ) : null}
      {docs.data && rows.length === 0 && filter.trim() ? <EmptyState title="No documents match.">Clear the search box to see all documents.</EmptyState> : null}

      {visible.length > 0 ? (
        <>
          <div className="overflow-x-auto rounded-md border border-hairline bg-surface">
            <table className="w-full border-collapse text-callout">
              <caption className="sr-only">Documents in {kb}</caption>
              <thead>
                <tr className="bg-muted text-left text-footnote text-fg-secondary">
                  <th scope="col" className="px-3 py-2 font-medium">Document</th>
                  <th scope="col" className="px-3 py-2 font-medium">Status</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Chunks</th>
                  <th scope="col" className="px-3 py-2 font-medium">SHA-256</th>
                  <th scope="col" className="px-3 py-2 font-medium">Last ingested</th>
                </tr>
              </thead>
              <tbody>
                {visible.map(({ doc: d, job }) => (
                  <tr key={`${d.namespace}-${d.document_id}`} className="min-h-10 border-t border-hairline align-top">
                    <td className="px-3 py-2">{d.source_filename ?? d.document_id}</td>
                    <td className="px-3 py-2"><StatusCell job={job} /></td>
                    <td className="mono tabular px-3 text-right">{formatNumber(d.chunk_count)}</td>
                    <td className="px-3">{d.content_hash ? <CopyValue value={d.content_hash.slice(0, 12)} label="content hash" /> : <span className="text-fg-tertiary">none</span>}</td>
                    <td className="mono px-3 text-footnote text-fg-secondary">{d.last_ingested_at ? formatTime(d.last_ingested_at) : 'none'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-end gap-2 text-footnote text-fg-secondary">
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <span className="tabular">Page {page} of {pages}</span>
            <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </>
      ) : null}

      <UploadDialog open={open} onOpenChange={setOpen} kb={kb} onDone={() => { void qc.invalidateQueries({ queryKey: ['jobs', 'ingest'] }); void qc.invalidateQueries({ queryKey: ['documents', kb] }) }} />
    </div>
  )
}
