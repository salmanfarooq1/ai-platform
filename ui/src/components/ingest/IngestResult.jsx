import Badge from '../ui/Badge'
import Card from '../ui/Card'
import styles from './IngestResult.module.css'

const STATUS = {
  new:       { label: 'New Document', variant: 'success', desc: 'Ingested and indexed for the first time.' },
  updated:   { label: 'Updated',      variant: 'info',    desc: 'Existing document replaced with new content.' },
  unchanged: { label: 'Unchanged',    variant: 'neutral', desc: 'Identical to stored version — no re-ingestion needed.' },
}

export default function IngestResult({ result, compact = false }) {
  if (!result) return null
  const { document_id, namespace, total_chunks, total_time_seconds,
          throughput_chunks_per_second, status, content_hash, chunks_deleted } = result
  const cfg = STATUS[status] ?? STATUS.new

  const body = (
    <>
      <div className={styles.statusRow}>
        <Badge variant={cfg.variant}>{cfg.label}</Badge>
        <span className={styles.desc}>{cfg.desc}</span>
      </div>
      <dl className={styles.metrics}>
        <div className={styles.metric}><dt>Document</dt><dd>{document_id}</dd></div>
        <div className={styles.metric}><dt>Namespace</dt><dd>{namespace}</dd></div>
        <div className={styles.metric}><dt>Chunks created</dt><dd className={styles.highlight}>{total_chunks.toLocaleString()}</dd></div>
        {chunks_deleted > 0 && <div className={styles.metric}><dt>Old chunks removed</dt><dd>{chunks_deleted.toLocaleString()}</dd></div>}
        <div className={styles.metric}><dt>Processing time</dt><dd>{total_time_seconds.toFixed(2)}s</dd></div>
        <div className={styles.metric}><dt>Throughput</dt><dd>{throughput_chunks_per_second.toFixed(1)} chunks/sec</dd></div>
        {content_hash && (
          <div className={`${styles.metric} ${styles.hashRow}`}>
            <dt>SHA-256</dt>
            <dd className={styles.hash} title={content_hash}>{content_hash.slice(0, 16)}…</dd>
          </div>
        )}
      </dl>
    </>
  )

  return compact ? body : <Card title="Ingestion complete">{body}</Card>
}
