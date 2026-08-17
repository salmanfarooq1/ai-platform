import { useState, useRef } from 'react'
import Button from '../ui/Button'
import styles from './DropZone.module.css'

const ACCEPTED = ['.txt', '.md', '.pdf']

export default function DropZone({ onUpload, loading, config }) {
  const namespaces = config?.namespaces ? Object.keys(config.namespaces) : ['default']
  const [dragging, setDragging] = useState(false)
  const [file, setFile]         = useState(null)
  const [namespace, setNs]      = useState(namespaces[0])
  const [docId, setDocId]       = useState('')
  const inputRef = useRef(null)

  function handleDrop(e) { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) setFile(f) }
  function fileSize(b) { return b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB` }

  return (
    <form onSubmit={e => { e.preventDefault(); if (file && !loading) onUpload({ file, namespace, documentId: docId || undefined }) }} aria-label="Document upload">
      <div className={[styles.zone, dragging ? styles.dragging : '', file ? styles.hasFile : ''].join(' ')}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => !file && inputRef.current?.click()}
        role="button" tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
        aria-label="Drop file here or click to browse">
        <input ref={inputRef} type="file" accept={ACCEPTED.join(',')} className={styles.hidden} onChange={e => { const f = e.target.files[0]; if (f) setFile(f) }} aria-hidden="true" />
        {file ? (
          <div className={styles.fileInfo}>
            <span className={styles.fileName}>{file.name}</span>
            <span className={styles.fileSize}>{fileSize(file.size)}</span>
            <button type="button" className={styles.clearBtn} onClick={e => { e.stopPropagation(); setFile(null) }} aria-label="Remove file">✕</button>
          </div>
        ) : (
          <div className={styles.prompt}>
            <span className={styles.icon} aria-hidden="true">⇑</span>
            <span>Drop a file here, or click to browse</span>
            <span className={styles.hint}>Accepts: {ACCEPTED.join(', ')}</span>
          </div>
        )}
      </div>
      <div className={styles.options}>
        <label className={styles.optGroup}>
          <span className={styles.optLabel}>Namespace</span>
          <select className={styles.select} value={namespace} onChange={e => setNs(e.target.value)} disabled={!config}>
            {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
          </select>
        </label>
        <label className={styles.optGroup}>
          <span className={styles.optLabel}>Document ID (optional)</span>
          <input type="text" className={styles.input} value={docId} onChange={e => setDocId(e.target.value)} placeholder={file?.name || 'defaults to filename'} />
        </label>
      </div>
      <Button type="submit" disabled={!file} loading={loading} size="lg">Ingest Document</Button>
    </form>
  )
}
