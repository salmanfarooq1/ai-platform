import styles from './GuardrailBanner.module.css'
export default function GuardrailBanner({ type, reason, confidence, floor = 0.45 }) {
  if (type === 'blocked') return (
    <div className={`${styles.banner} ${styles.error}`} role="alert">
      <span className={styles.icon}>⊘</span>
      <div><strong>Query blocked</strong><p>{reason || 'This query matches a restricted pattern.'}</p></div>
    </div>
  )
  if (type === 'flagged') return (
    <div className={`${styles.banner} ${styles.warning}`} role="status">
      <span className={styles.icon}>⚠</span>
      <div>
        <strong>Low confidence answer</strong>
        <p>{reason || `Confidence ${confidence != null ? Math.round(confidence*100)+'%' : ''} is below the ${floor*100}% threshold. Verify against primary sources.`}</p>
      </div>
    </div>
  )
  if (type === 'clarification') return (
    <div className={`${styles.banner} ${styles.info}`} role="status">
      <span className={styles.icon}>◎</span>
      <div><strong>Clarification suggested</strong><p>Query is ambiguous — try rephrasing for a more precise answer.</p></div>
    </div>
  )
  return null
}
