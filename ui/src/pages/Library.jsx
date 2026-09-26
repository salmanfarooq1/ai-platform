import { useState, useEffect, useMemo, useRef } from 'react'
import { Search, FileText, Copy, ChevronLeft, ChevronRight, Inbox, CircleAlert } from 'lucide-react'
import { listDocuments } from '../api/documents'
import { useCollection } from '../context/CollectionContext'
import { useToast } from '../context/ToastContext'
import Button from '../components/ui/Button'
import UploadModal from '../components/library/UploadModal'
import { usePageTitle } from '../hooks/usePageTitle'
import styles from './Library.module.css'

const PAGE_SIZES = [10, 25, 50]

// Library merges Documents + Ingest: a searchable, paginated table, and an
// "Add documents" modal (BRANDING.md §6, §8).
export default function Library({ config }) {
  usePageTitle('Library')
  const { namespace } = useCollection()
  const toast = useToast()

  const [docs, setDocs]       = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  const [query, setQuery]       = useState('')
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage]         = useState(1)

  const [modalOpen, setModalOpen] = useState(false)
  const addBtnRef = useRef(null)

  function load() {
    if (!namespace) return
    let gone = false
    setLoading(true); setError(null)
    listDocuments(namespace)
      .then(d => { if (!gone) setDocs(d.documents) })
      .catch(e => { if (!gone) setError(e) })
      .finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }

  useEffect(load, [namespace]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setPage(1) }, [query, pageSize, namespace])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return docs
    return docs.filter(d => (d.source_filename ?? d.document_id).toLowerCase().includes(q))
  }, [docs, query])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const pageDocs = filtered.slice((page - 1) * pageSize, page * pageSize)

  function copyId(id) {
    navigator.clipboard?.writeText(id).then(
      () => toast.info('Document ID copied to clipboard.'),
      () => toast.error('Could not copy to clipboard.')
    )
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerText}>
          <h1>Library</h1>
          <p>Documents ingested into the {namespace || '…'} collection.</p>
        </div>
        <Button ref={addBtnRef} onClick={() => setModalOpen(true)}>Add documents</Button>
      </header>

      <div className={styles.toolbar}>
        <div className={styles.searchBox}>
          <Search size={16} strokeWidth={1.75} className={styles.searchIcon} aria-hidden="true" />
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search documents…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            aria-label="Search documents"
          />
        </div>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Document</th>
              <th>Chunks</th>
              <th>SHA-256</th>
              <th>Last ingested</th>
              <th className={styles.actionsCol}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={5}>
                <div className={styles.stateRow}><div className="skeleton" style={{ width: '100%', height: 32 }} /></div>
              </td></tr>
            )}
            {!loading && error && (
              <tr><td colSpan={5}>
                <div className={styles.stateRow}>
                  <CircleAlert size={28} strokeWidth={1.75} className={styles.stateIcon} />
                  <span className={styles.errMsg}>{error.message || 'Could not load documents.'}</span>
                </div>
              </td></tr>
            )}
            {!loading && !error && docs.length === 0 && (
              <tr><td colSpan={5}>
                <div className={styles.stateRow}>
                  <Inbox size={28} strokeWidth={1.75} className={styles.stateIcon} />
                  <span>No documents yet. Add documents to start asking questions.</span>
                  <Button size="sm" onClick={() => setModalOpen(true)}>Add documents</Button>
                </div>
              </td></tr>
            )}
            {!loading && !error && docs.length > 0 && filtered.length === 0 && (
              <tr><td colSpan={5}>
                <div className={styles.stateRow}>
                  <Search size={28} strokeWidth={1.75} className={styles.stateIcon} />
                  <span>No documents match "{query}".</span>
                </div>
              </td></tr>
            )}
            {!loading && !error && pageDocs.map(doc => (
              <tr key={`${doc.document_id}-${doc.namespace}`}>
                <td>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <FileText size={14} strokeWidth={1.75} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }} />
                    {doc.source_filename ?? doc.document_id}
                  </span>
                </td>
                <td className={styles.num}>{doc.chunk_count.toLocaleString()}</td>
                <td className={styles.hash} title={doc.content_hash}>{doc.content_hash?.slice(0, 10)}…</td>
                <td>{doc.last_ingested_at ? new Date(doc.last_ingested_at).toLocaleString() : '—'}</td>
                <td className={styles.actionsCol}>
                  <button className={styles.iconBtn} onClick={() => copyId(doc.document_id)} title="Copy document ID" aria-label="Copy document ID">
                    <Copy size={14} strokeWidth={1.75} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.pagination}>
        <div className={styles.pageSize}>
          Rows per page
          <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))} aria-label="Rows per page">
            {PAGE_SIZES.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div className={styles.pageNav}>
          <button className={styles.iconBtn} onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Previous page">
            <ChevronLeft size={16} strokeWidth={1.75} />
          </button>
          Page {page} of {totalPages}
          <button className={styles.iconBtn} onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} aria-label="Next page">
            <ChevronRight size={16} strokeWidth={1.75} />
          </button>
        </div>
      </div>

      <UploadModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        triggerRef={addBtnRef}
        config={config}
        onIngested={load}
      />
    </div>
  )
}
