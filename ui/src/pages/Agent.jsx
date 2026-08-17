import { useState } from 'react'
import { agentQuery } from '../api/agent'
import AgentForm from '../components/agent/AgentForm'
import AgentCitationCard from '../components/agent/AgentCitationCard'
import AnswerBlock from '../components/search/AnswerBlock'
import ConfidenceGauge from '../components/search/ConfidenceGauge'
import GuardrailBanner from '../components/search/GuardrailBanner'
import MetaBar from '../components/search/MetaBar'
import VerificationBadge from '../components/agent/VerificationBadge'
import ReasoningChain from '../components/agent/ReasoningChain'
import FeedbackButtons from '../components/feedback/FeedbackButtons'
import Card from '../components/ui/Card'
import styles from './Agent.module.css'

export default function Agent({ config }) {
  const [result, setResult]   = useState(null)
  const [headers, setHeaders] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const floor = config?.confidence_floor ?? 0.45

  async function handleSubmit(params) {
    setLoading(true); setError(null); setResult(null); setHeaders(null)
    try {
      const { data, headers: h } = await agentQuery(params)
      setResult(data); setHeaders(h)
    } catch(e) { setError(e) }
    finally { setLoading(false) }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Agent</h1>
        <p>Multi-step reasoning with iterative retrieval and optional verification. Takes 8-15s for complex queries.</p>
      </header>
      <AgentForm onSubmit={handleSubmit} loading={loading} config={config} />
      {loading && (
        <div className={styles.loading} aria-busy="true">
          <div className={styles.loadingBar} />
          <p>Agent is researching… this may take several seconds.</p>
        </div>
      )}
      {error && <div className={styles.errorBanner} role="alert">⊘ {error.body?.detail || error.message}</div>}
      {result && (
        <div className={styles.results} role="region" aria-live="polite" aria-label="Agent response">
          <Card title="Answer" accent>
            <AnswerBlock answer={result.answer} />
            <FeedbackButtons requestId={headers?.queryId} endpoint="/agent/query" />
          </Card>
          <div className={styles.metricsRow}>
            <Card><ConfidenceGauge confidence={result.confidence} floor={floor} /></Card>
            <Card><VerificationBadge verified={result.verified} notes={result.verification_notes} /></Card>
            <Card>
              <MetaBar headers={headers} />
              <dl className={styles.agentStats}>
                <div><dt>Tool calls</dt><dd>{result.tool_calls_made}</dd></div>
                <div><dt>Time</dt><dd>{result.total_time_seconds.toFixed(2)}s</dd></div>
                <div><dt>Total cost</dt><dd>${result.total_cost_usd.toFixed(6)}</dd></div>
                <div><dt>Model</dt><dd className={styles.model}>{result.model_used?.split('/').pop()}</dd></div>
              </dl>
            </Card>
          </div>
          <ReasoningChain steps={result.reasoning_steps} toolCallCount={result.tool_calls_made} />
          {result.citations?.length > 0 && (
            <section>
              <h2 className={styles.citTitle}>Sources <span className={styles.citCount}>{result.citations.length}</span></h2>
              <div className={styles.citList}>{result.citations.map((c,i) => <AgentCitationCard key={`${c.document_id}-${i}`} citation={c} index={i} />)}</div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
