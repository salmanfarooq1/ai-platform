import { useState } from 'react'
import Badge from '../ui/Badge'
import styles from './CitationCard.module.css'

export default function CitationCard({ result, index }) {
  const [expanded, setExpanded] = useState(false)
  const { document_id, namespace, content, score, metadata } = result
  const chunkIndex = metadata?.chunk_index

  function scoreVariant(s) {
    if (s > 0.85) return 'success'
    if (s > 0.70) return 'info'
    if (s > 0.50) return 'warning'
    return 'neutral'
  }
  // RRF scores are <0.1; vector scores are 0.1-1.0
  function formatScore(s) {
    return s < 0.1 ? s.toFixed(4) : `${Math.round(s*100)}%`
  }
  const preview = content.slice(0, 180)

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.source}>
          <span className={styles.index} aria-label={`Citation ${index+1}`}>[{index+1}]</span>
          <span className={styles.docId} title={document_id}>{document_id}</span>
          {chunkIndex != null && <span className={styles.chunk}>chunk #{chunkIndex}</span>}
        </div>
        <div className={styles.meta}>
          <Badge variant="neutral" size="sm">{namespace}</Badge>
          <Badge variant={scoreVariant(score)} size="sm" title={`Score: ${score}`}>{formatScore(score)}</Badge>
        </div>
      </div>
      <div className={styles.content}>
        <p className={styles.text}>{expanded ? content : preview}{!expanded && content.length > 180 && '…'}</p>
        {content.length > 180 && (
          <button className={styles.expandBtn} onClick={() => setExpanded(e => !e)} aria-expanded={expanded}>
            {expanded ? 'Show less' : 'Show full excerpt'}
          </button>
        )}
      </div>
    </div>
  )
}
