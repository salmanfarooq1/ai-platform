import { useState } from 'react'
import Badge from '../ui/Badge'
import styles from './AgentCitationCard.module.css'

export default function AgentCitationCard({ citation, index }) {
  const [expanded, setExpanded] = useState(false)
  const { document_id, source_filename, chunk_index, relevance_score, excerpt } = citation
  const pct  = Math.round(relevance_score * 100)
  const variant = relevance_score > 0.85 ? 'success' : relevance_score > 0.70 ? 'info' : relevance_score > 0.50 ? 'warning' : 'neutral'

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.index}>[{index+1}]</span>
        <div className={styles.meta}>
          <span className={styles.filename}>{source_filename || document_id}</span>
          <span className={styles.chunk}>chunk #{chunk_index}</span>
        </div>
        <Badge variant={variant} size="sm" title={`Relevance: ${relevance_score}`}>{pct}%</Badge>
      </div>
      <p className={styles.excerpt}>{expanded ? excerpt : excerpt?.slice(0,200)}{!expanded && excerpt?.length > 200 && '…'}</p>
      {excerpt?.length > 200 && (
        <button className={styles.expand} onClick={() => setExpanded(e => !e)}>
          {expanded ? 'Show less' : 'Show full excerpt'}
        </button>
      )}
    </div>
  )
}
