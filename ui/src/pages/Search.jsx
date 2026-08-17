import { useState } from 'react'
import { search } from '../api/search'
import SearchForm from '../components/search/SearchForm'
import AnswerBlock from '../components/search/AnswerBlock'
import CitationCard from '../components/search/CitationCard'
import ConfidenceGauge from '../components/search/ConfidenceGauge'
import MetaBar from '../components/search/MetaBar'
import GuardrailBanner from '../components/search/GuardrailBanner'
import FeedbackButtons from '../components/feedback/FeedbackButtons'
import Card from '../components/ui/Card'
import styles from './Search.module.css'

export default function Search({ config }) {
  const [result, setResult]   = useState(null)
  const [headers, setHeaders] = useState(null)
  const [lastParams, setParams] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  async function handleSearch(params) {
    setLoading(true); setError(null); setResult(null); setHeaders(null); setParams(params)
    try {
      const { data, headers: h } = await search(params)
      setResult(data); setHeaders(h)
    } catch(e) { setError(e) }
    finally { setLoading(false) }
  }

  function errMsg(e) {
    if (!e) return null
    if (e.status === 400) return { type: 'blocked', reason: e.body?.detail?.reason }
    if (e.status === 404) return { type: 'generic', message: 'No documents found in this namespace. Upload a document first.' }
    if (e.status === 429) {
      const isbudget = e.body?.error === 'daily_token_budget_exceeded'
      return { type: 'generic', message: isbudget ? `Daily token budget exceeded. Resets at midnight UTC.` : 'Rate limit reached. Try again in a moment.' }
    }
    if (e.status === 502) return { type: 'generic', message: 'AI provider temporarily unavailable.' }
    return { type: 'generic', message: e.message || 'Unexpected error.' }
  }

  const err = errMsg(error)
  const floor = config?.confidence_floor ?? 0.45

  return (
    <div className={styles.page}>
      <header className={styles.header}><h1>Search</h1><p>Ask a question — the platform retrieves relevant chunks and generates a cited answer.</p></header>
      <SearchForm onSubmit={handleSearch} loading={loading} config={config} />
      {err && (
        <div className={styles.errorSection}>
          {err.type === 'blocked'
            ? <GuardrailBanner type="blocked" reason={err.reason} />
            : <div className={styles.genericError} role="alert">⊘ {err.message}</div>}
        </div>
      )}
      {result && (
        <div className={styles.results} role="region" aria-label="Search results" aria-live="polite">
          {result.needs_clarification && <GuardrailBanner type="clarification" />}
          {result.flagged && <GuardrailBanner type="flagged" reason={result.flag_reason} confidence={result.confidence} floor={floor} />}

          {/* rerank_applied mismatch warning */}
          {result.rerank_applied === false && lastParams?.rerank === true && (
            <p className={styles.rerankNote}>ℹ Reranking was requested but is unavailable in this deployment mode.</p>
          )}

          <Card title="Answer" accent>
            <AnswerBlock answer={result.answer} />
            <FeedbackButtons requestId={headers?.queryId} endpoint="/search" />
          </Card>

          <div className={styles.metricsRow}>
            <Card><ConfidenceGauge confidence={result.confidence} floor={floor} /></Card>
            <Card><MetaBar headers={headers} /></Card>
          </div>

          {result.results?.length > 0 && (
            <section aria-label="Source citations">
              <h2 className={styles.citationsTitle}>Sources <span className={styles.citCount}>{result.total_results}</span></h2>
              <div className={styles.citList}>{result.results.map((r,i) => <CitationCard key={`${r.document_id}-${i}`} result={r} index={i} />)}</div>
            </section>
          )}
        </div>
      )}
      {!result && !error && !loading && (
        <div className={styles.empty} aria-hidden="true">
          <span className={styles.emptyIcon}>⌕</span>
          <p>Enter a query above to search your documents.</p>
        </div>
      )}
      {loading && (
        <div className={styles.loading} aria-busy="true" aria-label="Searching…">
          <div className={styles.loadingBar} />
          <p>Searching and generating answer…</p>
        </div>
      )}
    </div>
  )
}
