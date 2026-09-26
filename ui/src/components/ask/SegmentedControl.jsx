import { motion, useReducedMotion } from 'motion/react'
import styles from './SegmentedControl.module.css'

// Quick answer / Deep research switch. The selected pill slides between
// segments with a critically damped spring and re-targets mid-slide on
// rapid clicks (motion's shared layoutId handles interruption) — BRANDING.md §8.
export default function SegmentedControl({ options, value, onChange }) {
  const reduce = useReducedMotion()
  return (
    <div className={styles.track} role="radiogroup" aria-label="Ask mode">
      {options.map(opt => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={value === opt.value}
          className={[styles.segment, value === opt.value ? styles.active : ''].join(' ')}
          onClick={() => onChange(opt.value)}
        >
          {value === opt.value && (
            <motion.span
              layoutId="segmented-pill"
              className={styles.pill}
              style={{ left: 0, right: 0 }}
              transition={reduce ? { duration: 0.15 } : { type: 'spring', bounce: 0, duration: 0.3 }}
            />
          )}
          <span className={styles.segmentContent}>{opt.icon}{opt.label}</span>
        </button>
      ))}
    </div>
  )
}
