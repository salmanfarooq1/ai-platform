import Card from '../components/ui/Card'
import StatusDot from '../components/ui/StatusDot'
import ModeBadge from '../components/layout/ModeBadge'
import { usePageTitle } from '../hooks/usePageTitle'
import styles from './System.module.css'

function formatUptime(s) {
  if (!s) return '—'
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${s % 60}s`
}

// System: service health, uptime, mode, version (BRANDING.md §6).
export default function System({ health, config }) {
  usePageTitle('System')

  const services = health ? [
    { name: 'Database', status: health.db === 'ok' ? 'ok' : 'error', detail: health.db },
    { name: 'Redis',    status: health.redis === 'ok' ? 'ok' : 'error', detail: health.redis },
    { name: 'Reranker', status: config?.reranker_enabled ? 'ok' : 'unknown', detail: config?.reranker_enabled ? 'enabled' : 'disabled in this mode' },
    { name: 'API',      status: 'ok', detail: `v${health.version}` },
  ] : []

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>System</h1>
        <p>Service health, uptime and platform version.</p>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sTitle}>Service health</h2>
        <div className={styles.grid}>
          {services.length === 0
            ? Array.from({ length: 4 }, (_, i) => <div key={i} className="skeleton" style={{ height: 88 }} />)
            : services.map(s => (
              <Card key={s.name}>
                <div className={styles.svcHeader}>
                  <StatusDot status={s.status} />
                  <span className={styles.svcName}>{s.name}</span>
                </div>
                <span className={[styles.svcStatus, styles[s.status]].join(' ')}>
                  {s.status === 'ok' ? 'Healthy' : s.status === 'unknown' ? 'Disabled' : `Down (${s.detail})`}
                </span>
              </Card>
            ))
          }
        </div>
      </section>

      {health && (
        <section className={styles.section}>
          <h2 className={styles.sTitle}>Platform</h2>
          <div className={styles.grid}>
            <Card>
              <div className={styles.tileLabel}>Mode</div>
              <div className={styles.tileValue} style={{ fontSize: 'var(--text-headline)' }}><ModeBadge mode={health.mode} /></div>
            </Card>
            <Card>
              <div className={styles.tileLabel}>Uptime</div>
              <div className={styles.tileValue}>{formatUptime(health.uptime_seconds)}</div>
            </Card>
            <Card>
              <div className={styles.tileLabel}>Version</div>
              <div className={styles.tileValue} style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-headline)' }}>{health.version}</div>
            </Card>
            <Card>
              <div className={styles.tileLabel}>Overall</div>
              <div className={[styles.svcStatus, health.status === 'ok' ? styles.ok : styles.error].join(' ')} style={{ fontSize: 'var(--text-headline)' }}>
                {health.status === 'ok' ? 'All systems operational' : 'Degraded'}
              </div>
            </Card>
          </div>
        </section>
      )}
    </div>
  )
}
