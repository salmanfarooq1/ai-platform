import styles from './ConfidenceGauge.module.css'

export default function ConfidenceGauge({ confidence, floor = 0.45 }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  const level = confidence >= 0.75 ? 'high' : confidence >= floor ? 'medium' : 'low'
  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span className={styles.label}>Confidence</span>
        <span className={`${styles.value} ${styles[level]}`}>{pct}%</span>
      </div>
      <div className={styles.track} role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`${styles.fill} ${styles[level]}`} style={{width:`${pct}%`}} />
        <div className={styles.threshold} style={{left:`${floor*100}%`}} title={`Guardrail floor: ${floor*100}%`} />
      </div>
      <span className={styles.floorLabel} style={{left:`${floor*100}%`}}>{floor*100}% floor</span>
    </div>
  )
}
