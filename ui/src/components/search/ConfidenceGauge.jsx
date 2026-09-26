import { motion, useReducedMotion } from 'motion/react'
import { confidenceLevel, CONFIDENCE_LABEL } from '../../brand'
import styles from './ConfidenceGauge.module.css'

const SIZE = 96
const STROKE = 6
const RADIUS = (SIZE - STROKE) / 2
const CIRC = 2 * Math.PI * RADIUS

// Confidence ring — draws once with a critically damped spring on first
// reveal; reduced motion shows the final value immediately (BRANDING.md §8, §12).
export default function ConfidenceGauge({ confidence, floor = 0.45 }) {
  const reduce = useReducedMotion()
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  const level = confidenceLevel(confidence, floor)
  const offset = CIRC * (1 - confidence)

  return (
    <div className={styles.wrapper}>
      <div className={styles.ringWrap}>
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
          <circle className={styles.track} cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} strokeWidth={STROKE} fill="none" />
          <motion.circle
            className={[styles.fill, styles[level]].join(' ')}
            cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} strokeWidth={STROKE} fill="none"
            strokeDasharray={CIRC}
            initial={{ strokeDashoffset: reduce ? offset : CIRC }}
            animate={{ strokeDashoffset: offset }}
            transition={reduce ? { duration: 0.15 } : { type: 'spring', bounce: 0, duration: 0.6 }}
          />
        </svg>
        <div className={styles.center}>
          <span className={[styles.value, styles[level]].join(' ')}>{pct}%</span>
          <span className={styles.label}>{CONFIDENCE_LABEL[level]}</span>
        </div>
      </div>
    </div>
  )
}
