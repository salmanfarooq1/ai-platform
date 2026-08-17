import { useState } from 'react'
import { ingestFile } from '../api/ingest'
import DropZone from '../components/ingest/DropZone'
import IngestResult from '../components/ingest/IngestResult'
import styles from './Ingest.module.css'

export default function Ingest({ config }) {
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  async function handleUpload(params) {
    setLoading(true); setError(null); setResult(null)
    try { setResult(await ingestFile(params)) }
    catch(e) { setError(e) }
    finally { setLoading(false) }
  }

  function errMsg(e) {
    if (!e) return null
    if (e.status === 415) return 'Unsupported file type. Upload .txt, .md, or .pdf.'
    if (e.status === 429) return 'Rate limit reached. Wait before uploading again.'
    return e.message || 'Upload failed. Try again.'
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Ingest Documents</h1>
        <p>Upload documents to a namespace. The platform chunks, embeds, and indexes automatically. SHA-256 deduplication prevents re-processing identical files.</p>
      </header>
      <DropZone onUpload={handleUpload} loading={loading} config={config} />
      {error && <div className={styles.error} role="alert">⊘ {errMsg(error)}</div>}
      {result && <IngestResult result={result} />}
    </div>
  )
}
