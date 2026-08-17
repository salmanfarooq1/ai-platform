import { useState, useEffect } from 'react'
import { getAnalyticsSummary } from '../api/analytics'
import Card from '../components/ui/Card'
import styles from './Analytics.module.css'

const DAYS = [7, 14, 30, 90]

export default function Analytics() {
  const [days, setDays]         = useState(7)
  const [summary, setSummary]   = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)

  useEffect(() => {
    let gone = false
    setLoading(true); setError(null)
    getAnalyticsSummary(days)
      .then(d  => { if (!gone) setSummary(d) })
      .catch(e => { if (!gone) setError(e) })
      .finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }, [days])

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Analytics</h1>
        <div className={styles.dayPicker} role="group" aria-label="Time window">
          {DAYS.map(d => (
            <button key={d} className={`${styles.dayBtn} ${d === days ? styles.active : ''}`}
              onClick={() => setDays(d)} aria-pressed={d === days}>{d}d</button>
          ))}
        </div>
      </header>

      {loading && <p className={styles.info}>Loading analytics…</p>}
      {error && <p className={styles.err} role="alert">{error.message}</p>}

      {summary && (
        <>
          <div className={styles.summaryRow}>
            <Card><dt className={styles.dt}>Total cost</dt><dd className={styles.dd}>${summary.total_cost_usd.toFixed(4)}</dd></Card>
            <Card><dt className={styles.dt}>Total requests</dt><dd className={styles.dd}>{summary.total_requests.toLocaleString()}</dd></Card>
            <Card><dt className={styles.dt}>Avg cost / request</dt><dd className={styles.dd}>${summary.avg_cost_per_request.toFixed(6)}</dd></Card>
            <Card><dt className={styles.dt}>Total tokens</dt><dd className={styles.dd}>{summary.total_tokens.toLocaleString()}</dd></Card>
          </div>

          <div className={styles.breakdownGrid}>
            <Card title="By namespace">
              <ul className={styles.list}>
                {summary.by_namespace.map(r => (
                  <li key={r.namespace} className={styles.row}>
                    <span className={styles.key}>{r.namespace}</span>
                    <span className={styles.val}>${r.cost_usd.toFixed(4)} · {r.requests} req</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="By endpoint">
              <ul className={styles.list}>
                {summary.by_endpoint.map(r => (
                  <li key={r.endpoint} className={styles.row}>
                    <span className={styles.key}>{r.endpoint}</span>
                    <span className={styles.val}>${r.cost_usd.toFixed(4)} · {r.requests} req</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="By model">
              <ul className={styles.list}>
                {summary.by_model.map(r => (
                  <li key={r.model} className={styles.row}>
                    <span className={styles.key}>{r.model.split('/').pop()}</span>
                    <span className={styles.val}>${r.cost_usd.toFixed(4)} · {r.requests} req</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          {summary.by_day.length > 0 && (
            <Card title="Daily breakdown">
              <table className={styles.table}>
                <thead><tr><th>Date</th><th>Cost</th><th>Tokens</th><th>Requests</th></tr></thead>
                <tbody>
                  {summary.by_day.map(r => (
                    <tr key={r.date}>
                      <td>{r.date}</td>
                      <td>${r.cost_usd.toFixed(4)}</td>
                      <td>{r.tokens.toLocaleString()}</td>
                      <td>{r.requests}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
