import { useState } from 'react'
import styles from './ReasoningChain.module.css'

export default function ReasoningChain({ steps = [], toolCallCount }) {
  const [open, setOpen] = useState(false)
  if (!steps.length) return null
  return (
    <div className={styles.chain}>
      <button className={styles.toggle} onClick={() => setOpen(o => !o)} aria-expanded={open}>
        <span className={styles.arrow}>{open ? '▾' : '▸'}</span>
        Reasoning chain
        <span className={styles.count}>{toolCallCount} tool call{toolCallCount !== 1 ? 's' : ''}</span>
      </button>
      {open && (
        <ol className={styles.steps}>
          {steps.map((step, i) => {
            const isCall   = step.startsWith('Called tool:')
            const isResult = step.startsWith('Tool result:')
            return (
              <li key={i} className={`${styles.step} ${isCall ? styles.call : isResult ? styles.result : styles.note}`}>
                <span className={styles.stepIcon} aria-hidden="true">{isCall ? '⚙' : isResult ? '↩' : '◦'}</span>
                <span className={styles.text}>{step}</span>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
