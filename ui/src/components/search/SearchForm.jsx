import { useState } from 'react'
import Button from '../ui/Button'
import Toggle from '../ui/Toggle'
import styles from './SearchForm.module.css'

const MODES = [
  { value: 'hybrid',      label: 'Hybrid', tooltip: 'BM25 + vector via RRF — best quality' },
  { value: 'vector_only', label: 'Vector', tooltip: 'Semantic similarity only' },
  { value: 'bm25_only',   label: 'BM25',   tooltip: 'Exact keyword matching' },
]

export default function SearchForm({ onSubmit, loading, config }) {
  const namespaces = config?.namespaces ? Object.keys(config.namespaces) : ['default']
  const rerankerEnabled = config?.reranker_enabled ?? true
  const maxQueryLength = config?.max_query_length ?? 1000

  const [query, setQuery]       = useState('')
  const [namespace, setNs]      = useState(namespaces[0])
  const [topK, setTopK]         = useState(5)
  const [mode, setMode]         = useState('hybrid')
  const [rerank, setRerank]     = useState(true)

  function handleKeyDown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); handleSubmit(e) }
  }
  function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim() || loading) return
    onSubmit({ query: query.trim(), namespace, topK, retrievalMode: mode, rerank: rerank && rerankerEnabled })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Search form">
      <div className={styles.inputRow}>
        <textarea className={styles.textarea} value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown} placeholder="Ask a question about your documents…"
          rows={3} maxLength={maxQueryLength} aria-label="Search query"
          aria-describedby="q-hint" disabled={loading} />
        <Button type="submit" loading={loading} disabled={!query.trim()} size="lg">Search</Button>
      </div>
      <span id="q-hint" className={styles.hint}>Ctrl+Enter · Max {maxQueryLength} chars</span>
      <div className={styles.controls}>
        <label className={styles.group}>
          <span className={styles.cLabel}>Namespace</span>
          <select className={styles.select} value={namespace} onChange={e => setNs(e.target.value)} disabled={!config}>
            {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
          </select>
        </label>
        <label className={styles.group}>
          <span className={styles.cLabel}>Retrieval</span>
          <div className={styles.modeGroup} role="radiogroup" aria-label="Retrieval mode">
            {MODES.map(m => (
              <button key={m.value} type="button" title={m.tooltip} aria-pressed={mode === m.value}
                className={`${styles.modeBtn} ${mode === m.value ? styles.active : ''}`}
                onClick={() => setMode(m.value)}>{m.label}</button>
            ))}
          </div>
        </label>
        <label className={styles.group}>
          <span className={styles.cLabel}>Sources: {topK}</span>
          <input type="range" min={1} max={20} value={topK} onChange={e => setTopK(Number(e.target.value))} className={styles.slider} aria-label={`Top ${topK} sources`} />
        </label>
        <div className={styles.group}>
          <Toggle label="Rerank" checked={rerank && rerankerEnabled} onChange={setRerank} disabled={!rerankerEnabled} id="rerank-toggle" />
          {!rerankerEnabled && <span className={styles.disabledHint}>Unavailable in this mode</span>}
        </div>
      </div>
    </form>
  )
}
