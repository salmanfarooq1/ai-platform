import { ShieldCheck, ShieldX, ShieldQuestion } from 'lucide-react'
import styles from './VerificationBadge.module.css'

export default function VerificationBadge({ verified, notes }) {
  const state = verified === null || verified === undefined ? 'skipped' : verified ? 'verified' : 'failed'
  const Icon  = { verified: ShieldCheck, failed: ShieldX, skipped: ShieldQuestion }[state]
  const label = { verified: 'Verified', failed: 'Unverified', skipped: 'Verifier not run' }[state]
  return (
    <div className={`${styles.badge} ${styles[state]}`}>
      <span className={styles.icon}><Icon size={16} strokeWidth={1.75} /></span>
      <span>{label}</span>
      {notes && <span className={styles.notes}>{notes}</span>}
    </div>
  )
}
