import { useState, useEffect } from 'react'
import { listDocuments } from '../api/documents'
import Card from '../components/ui/Card'
import styles from './Documents.module.css'

export default function Documents({ config }) {
  const namespaces   = config?.namespaces ? Object.keys(config.namespaces) : []
  const [ns, setNs]           = useState('')
  const [docs, setDocs]       = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    let gone = false
    setLoading(true); setError(null)
    listDocuments(ns || undefined)
      .then(d  => { if (!gone) setDocs(d.documents) })
      .catch(e => { if (!gone) setError(e) })
      .finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }, [ns])

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Documents</h1>
        <select className={styles.select} value={ns} onChange={e => setNs(e.target.value)} aria-label="Filter by namespace">
          <option value="">All namespaces</option>
          {namespaces.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </header>

      {loading && <p className={styles.info}>Loading documents…</p>}
      {error && <p className={styles.err} role="alert">{error.message}</p>}

      {!loading && !error && (
        <Card>
          <table className={styles.table}>
            <thead>
              <tr><th>Document</th><th>Namespace</th><th>Chunks</th><th>SHA-256</th><th>Last ingested</th></tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <tr key={`${doc.document_id}-${doc.namespace}`}>
                  <td>{doc.source_filename ?? doc.document_id}</td>
                  <td>{doc.namespace}</td>
                  <td>{doc.chunk_count.toLocaleString()}</td>
                  <td className={styles.hash} title={doc.content_hash}>{doc.content_hash?.slice(0,10)}…</td>
                  <td>{doc.last_ingested_at ? new Date(doc.last_ingested_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {docs.length === 0 && (
            <p className={styles.empty}>No documents ingested{ns ? ` in "${ns}"` : ''}.</p>
          )}
        </Card>
      )}
    </div>
  )
}
