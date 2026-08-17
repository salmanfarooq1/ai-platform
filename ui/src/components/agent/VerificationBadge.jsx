import styles from './VerificationBadge.module.css'
export default function VerificationBadge({ verified, notes }) {
  const state = verified === null || verified === undefined ? 'skipped' : verified ? 'verified' : 'failed'
  const icon  = { verified: '✓', failed: '✗', skipped: '◎' }[state]
  const label = { verified: 'Verified', failed: 'Unverified', skipped: 'Verifier not run' }[state]
  return (
    <div className={`${styles.badge} ${styles[state]}`}>
      <span className={styles.icon}>{icon}</span>
      <span>{label}</span>
      {notes && <span className={styles.notes}>{notes}</span>}
    </div>
  )
}
