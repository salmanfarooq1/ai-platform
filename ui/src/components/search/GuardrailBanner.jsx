import { ShieldAlert, ShieldQuestion } from 'lucide-react'
import styles from './GuardrailBanner.module.css'

export default function GuardrailBanner({ type, reason, confidence, floor = 0.45 }) {
  if (type === 'blocked') return (
    <div className={`${styles.banner} ${styles.error}`} role="alert">
      <ShieldAlert size={18} strokeWidth={1.75} className={styles.icon} aria-hidden="true" />
      <div><strong>Query blocked</strong><p>{reason || 'This query matches a restricted pattern.'}</p></div>
    </div>
  )
  if (type === 'flagged') return (
    <div className={`${styles.banner} ${styles.warning}`} role="status">
      <ShieldAlert size={18} strokeWidth={1.75} className={styles.icon} aria-hidden="true" />
      <div>
        <strong>Low confidence answer</strong>
        <p>{reason || `Confidence ${confidence != null ? Math.round(confidence * 100) + '%' : ''} is below the ${floor * 100}% threshold. Check the sources before relying on this.`}</p>
      </div>
    </div>
  )
  if (type === 'clarification') return (
    <div className={`${styles.banner} ${styles.info}`} role="status">
      <ShieldQuestion size={18} strokeWidth={1.75} className={styles.icon} aria-hidden="true" />
      <div><strong>Clarification suggested</strong><p>This query is ambiguous — try rephrasing for a more precise answer.</p></div>
    </div>
  )
  return null
}
