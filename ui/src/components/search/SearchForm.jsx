import { useState } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import Button from '../ui/Button'
import Toggle from '../ui/Toggle'
import { useCollection } from '../../context/CollectionContext'
import styles from './SearchForm.module.css'

const MODES = [
  { value: 'hybrid',      label: 'Hybrid', tooltip: 'BM25 + vector via RRF — best quality' },
  { value: 'vector_only', label: 'Vector', tooltip: 'Semantic similarity only' },
  { value: 'bm25_only',   label: 'BM25',   tooltip: 'Exact keyword matching' },
]

// Quick answer form. Namespace comes from the top-bar Collection picker
// (BRANDING.md §6) — this form no longer has its own namespace input.
export default function SearchForm({ onSubmit, loading, config, query, setQuery }) {
  const { namespace } = useCollection()
  const reduce = useReducedMotion()
  const rerankerEnabled = config?.reranker_enabled ?? true
  const maxQueryLength = config?.max_query_length ?? 1000

  const [topK, setTopK]     = useState(5)
  const [mode, setMode]     = useState('hybrid')
  const [rerank, setRerank] = useState(true)
  const [showOptions, setShowOptions] = useState(false)

  function handleKeyDown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); handleSubmit(e) }
  }
  function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim() || loading) return
    onSubmit({ query: query.trim(), namespace, topK, retrievalMode: mode, rerank: rerank && rerankerEnabled })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Quick answer form">
      <textarea className={styles.textarea} value={query} onChange={e => setQuery(e.target.value)}
        onKeyDown={handleKeyDown} placeholder="Ask a question about your documents…"
        rows={2} maxLength={maxQueryLength} aria-label="Question"
        aria-describedby="q-hint" disabled={loading} />

      <div className={styles.bottomRow}>
        <button type="button" className={styles.disclosureBtn} onClick={() => setShowOptions(o => !o)} aria-expanded={showOptions}>
          {showOptions ? <ChevronDown size={14} strokeWidth={1.75} /> : <ChevronRight size={14} strokeWidth={1.75} />}
          Options
        </button>
        <span id="q-hint" className={styles.hint}>Ctrl+Enter</span>
        <Button type="submit" loading={loading} disabled={!query.trim()} size="md">
          {loading ? 'Asking…' : 'Ask'}
        </Button>
      </div>

      <motion.div
        className={styles.options}
        initial={false}
        animate={{ height: showOptions ? 'auto' : 0, opacity: showOptions ? 1 : 0 }}
        transition={reduce ? { duration: 0.15 } : { type: 'spring', bounce: 0, duration: 0.35 }}
      >
        <div className={styles.optionsInner}>
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
      </motion.div>
    </form>
  )
}
