import Badge from '../ui/Badge'
import styles from './MetaBar.module.css'

export default function MetaBar({ headers }) {
  if (!headers) return null
  const { cache, cacheType, costUsd, tokensIn, tokensOut, processTime, queryId, budgetRemaining, budgetLimit } = headers
  const isHit = cache === 'HIT'

  function formatCost(v) {
    const n = parseFloat(v)
    return isNaN(n) ? null : `$${n.toFixed(6)}`
  }
  function formatBudget(r, l) {
    if (!r || !l) return null
    return `${Math.round(parseInt(r)/1000)}K / ${Math.round(parseInt(l)/1000)}K tokens`
  }

  return (
    <div className={styles.metaBar} role="status" aria-label="Query metadata">
      {cache && (
        <Badge variant={isHit ? 'success' : 'neutral'} title={isHit ? 'Cache hit — no LLM call' : 'Cache miss — full RAG pipeline'}>
          {isHit ? `⚡ ${cacheType === 'semantic' ? 'Semantic' : 'Exact'} Hit` : '↻ Cache Miss'}
        </Badge>
      )}
      {costUsd && parseFloat(costUsd) >= 0 && (
        <span className={styles.chip} title="LLM cost">
          <span className={styles.label}>Cost</span>
          <span className={styles.value} style={{color:'var(--accent)'}}>{formatCost(costUsd) ?? '$0.000000'}</span>
        </span>
      )}
      {tokensIn && tokensOut && (
        <span className={styles.chip} title="Token usage">
          <span className={styles.label}>Tokens</span>
          <span className={styles.value} style={{color:'var(--data)'}}>{tokensIn} in / {tokensOut} out</span>
        </span>
      )}
      {processTime && (
        <span className={styles.chip} title="Response time">
          <span className={styles.label}>Time</span>
          <span className={styles.value}>{processTime}</span>
        </span>
      )}
      {budgetRemaining && budgetLimit && (
        <span className={styles.chip} title="Daily token budget remaining">
          <span className={styles.label}>Budget</span>
          <span className={styles.value}>{formatBudget(budgetRemaining, budgetLimit)}</span>
        </span>
      )}
      {queryId && (
        <span className={styles.chip} title={`Request ID: ${queryId}`}>
          <span className={styles.label}>ID</span>
          <span className={`${styles.value} ${styles.mono}`}>{queryId.slice(0,12)}…</span>
        </span>
      )}
    </div>
  )
}
