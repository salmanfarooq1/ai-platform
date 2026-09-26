import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import Badge from '../ui/Badge'
import styles from './AgentCitationCard.module.css'

export default function AgentCitationCard({ citation, index, selected = false }) {
  const [expanded, setExpanded] = useState(false)
  const { document_id, source_filename, chunk_index, relevance_score, excerpt } = citation
  const pct  = Math.round(relevance_score * 100)
  const variant = relevance_score > 0.85 ? 'success' : relevance_score > 0.70 ? 'info' : relevance_score > 0.50 ? 'warning' : 'neutral'

  return (
    <div id={`citation-${index}`} className={[styles.card, selected ? styles.selected : ''].join(' ')}>
      <div className={styles.header}>
        <span className={styles.index}>[{index + 1}]</span>
        <div className={styles.meta}>
          <span className={styles.filename}>{source_filename || document_id}</span>
          <span className={styles.chunk}>chunk #{chunk_index}</span>
        </div>
        <Badge variant={variant} size="sm" title={`Relevance: ${relevance_score}`}>{pct}%</Badge>
      </div>
      <p className={styles.excerpt}>{expanded ? excerpt : excerpt?.slice(0, 200)}{!expanded && excerpt?.length > 200 && '…'}</p>
      {excerpt?.length > 200 && (
        <button className={styles.expand} onClick={() => setExpanded(e => !e)}>
          {expanded ? <ChevronUp size={14} strokeWidth={1.75} /> : <ChevronDown size={14} strokeWidth={1.75} />}
          {expanded ? 'Show less' : 'Show full excerpt'}
        </button>
      )}
    </div>
  )
}
