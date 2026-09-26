import { useState, useRef } from 'react'
import { UploadCloud, X, CircleAlert } from 'lucide-react'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import IngestResult from '../ingest/IngestResult'
import { ingestFile } from '../../api/ingest'
import { useCollection } from '../../context/CollectionContext'
import { useToast } from '../../context/ToastContext'
import styles from './UploadModal.module.css'

const ACCEPTED = ['.txt', '.md', '.pdf']

function fileSize(b) {
  return b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`
}

// "Add documents" modal — three numbered steps (BRANDING.md §8).
export default function UploadModal({ open, onClose, triggerRef, config, onIngested }) {
  const { namespace: activeNamespace, namespaces } = useCollection()
  const toast = useToast()
  const [namespace, setNamespace] = useState(activeNamespace)
  const [dragging, setDragging]   = useState(false)
  const [file, setFile]           = useState(null)
  const [docId, setDocId]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState(null)
  const inputRef = useRef(null)

  function handleDrop(e) { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) setFile(f) }

  function errMsg(e) {
    if (e.status === 415) return 'Unsupported file type. Upload .txt, .md, or .pdf.'
    if (e.status === 429) return 'Rate limit reached. Wait before uploading again.'
    if (e.status === 413) return 'Upload failed. The file is over the size limit. Try a smaller file.'
    return e.message || 'Upload failed. Try again.'
  }

  async function handleUpload(e) {
    e.preventDefault()
    if (!file || loading) return
    setLoading(true); setError(null); setResult(null)
    try {
      const r = await ingestFile({ file, namespace, documentId: docId || undefined })
      setResult(r)
      toast.success(`${file.name} ingested — ${r.total_chunks.toLocaleString()} chunks.`, 'Upload complete')
      onIngested?.()
    } catch (e2) {
      setError(e2)
      toast.error(errMsg(e2), 'Upload failed')
    } finally { setLoading(false) }
  }

  function handleClose() {
    if (loading) return // Esc/close is a no-op mid-upload
    onClose()
    // Reset once the close animation has had a beat.
    setTimeout(() => { setFile(null); setDocId(''); setResult(null); setError(null) }, 200)
  }

  return (
    <Modal open={open} onClose={handleClose} title="Add documents" triggerRef={triggerRef} closeOnEsc={!loading}>
      <form onSubmit={handleUpload}>
        <div className={styles.step}>
          <div className={styles.stepHeader}>
            <span className={styles.stepNum}>1</span>
            <span className={styles.stepTitle}>Choose collection</span>
          </div>
          <select className={styles.select} value={namespace} onChange={e => setNamespace(e.target.value)} aria-label="Collection">
            {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
          </select>
        </div>

        <div className={styles.step}>
          <div className={styles.stepHeader}>
            <span className={styles.stepNum}>2</span>
            <span className={styles.stepTitle}>Drop files</span>
          </div>
          <div
            className={[styles.zone, dragging ? styles.dragging : '', file ? styles.hasFile : ''].join(' ')}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => !file && inputRef.current?.click()}
            role="button" tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
            aria-label="Drop a file here or click to browse"
          >
            <input ref={inputRef} type="file" accept={ACCEPTED.join(',')} className={styles.hidden}
              onChange={e => { const f = e.target.files[0]; if (f) setFile(f) }} aria-hidden="true" />
            {file ? (
              <div className={styles.fileInfo}>
                <span className={styles.fileName}>{file.name}</span>
                <span className={styles.fileSize}>{fileSize(file.size)}</span>
                <button type="button" className={styles.clearBtn} onClick={e => { e.stopPropagation(); setFile(null); setResult(null) }} aria-label="Remove file">
                  <X size={16} strokeWidth={1.75} />
                </button>
              </div>
            ) : (
              <div className={styles.prompt}>
                <UploadCloud size={28} strokeWidth={1.75} className={styles.icon} aria-hidden="true" />
                <span>Drop a file here, or click to browse</span>
                <span className={styles.hint}>Accepts {ACCEPTED.join(', ')}</span>
              </div>
            )}
          </div>
        </div>

        <div className={styles.step}>
          <div className={styles.stepHeader}>
            <span className={styles.stepNum}>3</span>
            <span className={styles.stepTitle}>Review and upload</span>
          </div>
          <input type="text" className={styles.input} value={docId} onChange={e => setDocId(e.target.value)}
            placeholder={file?.name ? `Document ID (defaults to "${file.name}")` : 'Document ID (optional)'} />

          {error && (
            <div className={styles.error} role="alert">
              <CircleAlert size={16} strokeWidth={1.75} />
              {errMsg(error)}
            </div>
          )}
          {result && <IngestResult result={result} compact />}
        </div>

        <div className={styles.actions}>
          <Button type="button" variant="ghost" onClick={handleClose} disabled={loading}>Cancel</Button>
          <Button type="submit" disabled={!file} loading={loading}>{loading ? 'Uploading…' : 'Upload'}</Button>
        </div>
      </form>
    </Modal>
  )
}
