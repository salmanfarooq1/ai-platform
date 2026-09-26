import { useState } from 'react'
import { ChevronRight, ChevronDown, Search, Brain } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import styles from './ReasoningChain.module.css'

// Deep research reasoning timeline — collapsed by default (BRANDING.md §8).
export default function ReasoningChain({ steps = [], toolCallCount }) {
  const [open, setOpen] = useState(false)
  const reduce = useReducedMotion()
  if (!steps.length) return null

  return (
    <div className={styles.chain}>
      <button className={styles.toggle} onClick={() => setOpen(o => !o)} aria-expanded={open}>
        <span className={styles.arrow}>{open ? <ChevronDown size={14} strokeWidth={1.75} /> : <ChevronRight size={14} strokeWidth={1.75} />}</span>
        Show reasoning ({steps.length} step{steps.length !== 1 ? 's' : ''})
        <span className={styles.count}>{toolCallCount} tool call{toolCallCount !== 1 ? 's' : ''}</span>
      </button>
      <motion.div
        className={styles.body}
        initial={false}
        animate={{ height: open ? 'auto' : 0, opacity: open ? 1 : 0 }}
        transition={reduce ? { duration: 0.15 } : { type: 'spring', bounce: 0, duration: 0.35 }}
      >
        <ol className={styles.steps}>
          {steps.map((step, i) => {
            const isCall   = step.startsWith('Called tool:')
            const isResult = step.startsWith('Tool result:')
            const Icon = isCall ? Search : isResult ? Brain : Brain
            return (
              <li key={i} className={`${styles.step} ${isCall ? styles.call : isResult ? styles.result : styles.note}`}>
                <span className={styles.stepIcon} aria-hidden="true"><Icon size={14} strokeWidth={1.75} /></span>
                <span className={styles.text}>{step}</span>
              </li>
            )
          })}
        </ol>
      </motion.div>
    </div>
  )
}
