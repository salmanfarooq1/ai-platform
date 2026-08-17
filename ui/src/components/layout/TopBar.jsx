import StatusDot from '../ui/StatusDot'
import Toggle from '../ui/Toggle'
import { useTheme } from '../../hooks/useTheme'
import styles from './TopBar.module.css'

export default function TopBar({ health }) {
  const isHealthy = health?.status === 'ok'
  const mode = health?.mode ?? '—'
  const { isDark, toggleDark } = useTheme()

  function formatUptime(s) {
    if (!s) return '—'
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  }

  return (
    <header className={styles.topBar} role="banner">
      <div className={styles.left}>
        <StatusDot
          status={health === null ? 'unknown' : isHealthy ? 'ok' : 'error'}
          aria-label={`System: ${health === null ? 'checking' : isHealthy ? 'healthy' : 'degraded'}`}
        />
        <span className={styles.platformName}>AI Platform</span>
      </div>
      <div className={styles.right}>
        {health && (
          <>
            <span className={`${styles.modeBadge} ${styles[`mode_${mode}`]}`}>
              {mode.toUpperCase()}
            </span>
            <span className={styles.uptime} title="Uptime">↑ {formatUptime(health.uptime_seconds)}</span>
          </>
        )}
        <span className={styles.version}>{health?.version ?? ''}</span>
        <div className={styles.themeSep} aria-hidden="true" />
        <Toggle
          id="theme-toggle"
          label={isDark ? '🌙' : '☀️'}
          checked={isDark}
          onChange={toggleDark}
        />
      </div>
    </header>
  )
}
