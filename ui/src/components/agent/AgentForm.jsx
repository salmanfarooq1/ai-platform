import { useState } from 'react'
import Button from '../ui/Button'
import Toggle from '../ui/Toggle'
import styles from './AgentForm.module.css'

export default function AgentForm({ onSubmit, loading, config }) {
  const namespaces = config?.namespaces ? Object.keys(config.namespaces) : ['default']
  const defaults   = config?.agent_defaults ?? { max_iterations: 6, enable_verifier: true, max_verify_retries: 1 }

  const [question, setQ]        = useState('')
  const [namespace, setNs]      = useState(namespaces[0])
  const [maxIter, setMaxIter]   = useState(defaults.max_iterations)
  const [verifier, setVerifier] = useState(defaults.enable_verifier)
  const [retries, setRetries]   = useState(defaults.max_verify_retries)

  function handleSubmit(e) {
    e.preventDefault()
    if (!question.trim() || loading) return
    onSubmit({ question: question.trim(), namespace, maxIterations: maxIter, enableVerifier: verifier, maxVerifyRetries: retries })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Agent query">
      <textarea className={styles.textarea} value={question} onChange={e => setQ(e.target.value)}
        placeholder="Ask a complex compliance question… The agent researches iteratively."
        rows={3} maxLength={config?.max_query_length ?? 1000} disabled={loading} aria-label="Agent question" />
      <div className={styles.controls}>
        <label className={styles.group}>
          <span className={styles.label}>Namespace</span>
          <select className={styles.select} value={namespace} onChange={e => setNs(e.target.value)} disabled={!config}>
            {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
          </select>
        </label>
        <label className={styles.group}>
          <span className={styles.label}>Max iterations: {maxIter}</span>
          <input type="range" min={1} max={10} value={maxIter} onChange={e => setMaxIter(Number(e.target.value))} className={styles.slider} />
        </label>
        <div className={styles.group}>
          <Toggle label="Enable verifier" checked={verifier} onChange={setVerifier} id="verifier-toggle" />
        </div>
        {verifier && (
          <label className={styles.group}>
            <span className={styles.label}>Verify retries: {retries}</span>
            <input type="range" min={0} max={3} value={retries} onChange={e => setRetries(Number(e.target.value))} className={styles.slider} />
          </label>
        )}
      </div>
      <Button type="submit" loading={loading} disabled={!question.trim()} size="lg">Run Agent</Button>
    </form>
  )
}
