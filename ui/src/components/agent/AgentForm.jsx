import { useState } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import Button from '../ui/Button'
import Toggle from '../ui/Toggle'
import { useCollection } from '../../context/CollectionContext'
import styles from './AgentForm.module.css'

// Deep research form. Namespace comes from the top-bar Collection picker
// (BRANDING.md §6) — no per-form namespace input.
export default function AgentForm({ onSubmit, loading, config, question, setQuestion }) {
  const { namespace } = useCollection()
  const reduce = useReducedMotion()
  const defaults = config?.agent_defaults ?? { max_iterations: 6, enable_verifier: true, max_verify_retries: 1 }

  const [maxIter, setMaxIter]   = useState(defaults.max_iterations)
  const [verifier, setVerifier] = useState(defaults.enable_verifier)
  const [retries, setRetries]   = useState(defaults.max_verify_retries)
  const [showOptions, setShowOptions] = useState(false)

  function handleSubmit(e) {
    e.preventDefault()
    if (!question.trim() || loading) return
    onSubmit({ question: question.trim(), namespace, maxIterations: maxIter, enableVerifier: verifier, maxVerifyRetries: retries })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Deep research form">
      <textarea className={styles.textarea} value={question} onChange={e => setQuestion(e.target.value)}
        placeholder="Ask a complex question — the agent researches iteratively across your documents…"
        rows={2} maxLength={config?.max_query_length ?? 1000} disabled={loading} aria-label="Question" />

      <div className={styles.bottomRow}>
        <button type="button" className={styles.disclosureBtn} onClick={() => setShowOptions(o => !o)} aria-expanded={showOptions}>
          {showOptions ? <ChevronDown size={14} strokeWidth={1.75} /> : <ChevronRight size={14} strokeWidth={1.75} />}
          Options
        </button>
        <span className={styles.hint}>Takes 8–15s for complex queries</span>
        <Button type="submit" loading={loading} disabled={!question.trim()} size="md">
          {loading ? 'Researching…' : 'Ask'}
        </Button>
      </div>

      <motion.div
        className={styles.options}
        initial={false}
        animate={{ height: showOptions ? 'auto' : 0, opacity: showOptions ? 1 : 0 }}
        transition={reduce ? { duration: 0.15 } : { type: 'spring', bounce: 0, duration: 0.35 }}
      >
        <div className={styles.optionsInner}>
          <label className={styles.group}>
            <span className={styles.cLabel}>Max iterations: {maxIter}</span>
            <input type="range" min={1} max={10} value={maxIter} onChange={e => setMaxIter(Number(e.target.value))} className={styles.slider} />
          </label>
          <div className={styles.group}>
            <Toggle label="Enable verifier" checked={verifier} onChange={setVerifier} id="verifier-toggle" />
          </div>
          {verifier && (
            <label className={styles.group}>
              <span className={styles.cLabel}>Verify retries: {retries}</span>
              <input type="range" min={0} max={3} value={retries} onChange={e => setRetries(Number(e.target.value))} className={styles.slider} />
            </label>
          )}
        </div>
      </motion.div>
    </form>
  )
}
