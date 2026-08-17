import { useState, useEffect } from 'react'
import { getHealth } from '../api/health'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import StatusDot from '../components/ui/StatusDot'
import styles from './Dashboard.module.css'

export default function Dashboard({ health }) {
  // health is already fetched in App.jsx and passed as prop.
  // We do NOT fetch it again here.
  const [localHealth, setLocal] = useState(health)
  useEffect(() => { setLocal(health) }, [health])

  const services = localHealth ? [
    { name: 'Database', status: localHealth.db    === 'ok' ? 'ok' : 'error', detail: localHealth.db },
    { name: 'Redis',    status: localHealth.redis  === 'ok' ? 'ok' : 'error', detail: localHealth.redis },
    { name: 'API',      status: 'ok', detail: `v${localHealth.version}` },
  ] : []

  function formatUptime(s) {
    if (!s) return '—'
    const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m = Math.floor((s%3600)/60)
    if (d > 0) return `${d}d ${h}h`
    if (h > 0) return `${h}h ${m}m`
    return `${m}m ${s%60}s`
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Dashboard</h1>
        <p>System health and platform overview</p>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sTitle}>System Health</h2>
        <div className={styles.healthGrid}>
          {services.length === 0
            ? Array.from({length:3}, (_,i) => <div key={i} className="skeleton" style={{height:100}} />)
            : services.map(s => (
              <Card key={s.name}>
                <div className={styles.svcHeader}>
                  <StatusDot status={s.status} />
                  <span className={styles.svcName}>{s.name}</span>
                </div>
                <span className={s.status === 'ok' ? styles.ok : styles.err}>
                  {s.status === 'ok' ? 'Operational' : s.detail}
                </span>
              </Card>
            ))
          }
        </div>
      </section>

      {localHealth && (
        <section className={styles.section}>
          <h2 className={styles.sTitle}>Platform Info</h2>
          <div className={styles.infoGrid}>
            <Card>
              <dt className={styles.infoLabel}>Mode</dt>
              <dd><Badge variant={localHealth.mode === 'prod' ? 'success' : localHealth.mode === 'demo' ? 'accent' : 'info'}>{localHealth.mode?.toUpperCase()}</Badge></dd>
            </Card>
            <Card>
              <dt className={styles.infoLabel}>Uptime</dt>
              <dd className={styles.infoVal}>{formatUptime(localHealth.uptime_seconds)}</dd>
            </Card>
            <Card>
              <dt className={styles.infoLabel}>Version</dt>
              <dd className={`${styles.infoVal} ${styles.mono}`}>{localHealth.version}</dd>
            </Card>
            <Card>
              <dt className={styles.infoLabel}>Overall</dt>
              <dd><Badge variant={localHealth.status === 'ok' ? 'success' : 'danger'}>{localHealth.status === 'ok' ? 'All systems operational' : 'Degraded'}</Badge></dd>
            </Card>
          </div>
        </section>
      )}

      <section className={styles.section}>
        <h2 className={styles.sTitle}>Retrieval Modes</h2>
        <div className={styles.modeTable}>
          {[
            { mode:'hybrid',      desc:'BM25 + vector via RRF k=60. Best quality. Default.', best:'All queries' },
            { mode:'vector_only', desc:'Semantic similarity (cosine on embeddings).',         best:'Conceptual paraphrases' },
            { mode:'bm25_only',   desc:'PostgreSQL full-text search (ts_rank).',              best:'"Article 33", exact IDs' },
          ].map(r => (
            <div key={r.mode} className={styles.modeRow}>
              <code className={styles.modeCode}>{r.mode}</code>
              <span className={styles.modeDesc}>{r.desc}</span>
              <span className={styles.modeBest}>Best for: {r.best}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
