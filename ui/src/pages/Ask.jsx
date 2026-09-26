import { useState } from 'react'
import { MessageSquareText, Brain } from 'lucide-react'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { search } from '../api/search'
import { agentQuery } from '../api/agent'
import SegmentedControl from '../components/ask/SegmentedControl'
import SearchForm from '../components/search/SearchForm'
import AgentForm from '../components/agent/AgentForm'
import AnswerBlock from '../components/search/AnswerBlock'
import CitationCard from '../components/search/CitationCard'
import AgentCitationCard from '../components/agent/AgentCitationCard'
import ConfidenceGauge from '../components/search/ConfidenceGauge'
import MetaBar from '../components/search/MetaBar'
import GuardrailBanner from '../components/search/GuardrailBanner'
import VerificationBadge from '../components/agent/VerificationBadge'
import ReasoningChain from '../components/agent/ReasoningChain'
import FeedbackButtons from '../components/feedback/FeedbackButtons'
import { usePageTitle } from '../hooks/usePageTitle'
import styles from './Ask.module.css'

const SUGGESTIONS = [
  'What are the KYC requirements?',
  'Summarize the latest filing',
  'Which documents mention Article 33?',
]

const MODES = [
  { value: 'quick', label: 'Quick answer',  icon: <MessageSquareText size={14} strokeWidth={1.75} /> },
  { value: 'deep',  label: 'Deep research', icon: <Brain size={14} strokeWidth={1.75} /> },
]

// Ask merges Search + Agent behind one mode switch (BRANDING.md §6, §7).
export default function Ask({ config }) {
  usePageTitle('Ask')
  const reduce = useReducedMotion()
  const [mode, setMode] = useState('quick')

  const [query, setQuery]       = useState('')
  const [question, setQuestion] = useState('')

  const [quick, setQuick] = useState({ result: null, headers: null, params: null, loading: false, error: null })
  const [deep, setDeep]   = useState({ result: null, headers: null, loading: false, error: null })

  const hasAnswered = quick.result != null || deep.result != null
  const floor = config?.confidence_floor ?? 0.45

  async function handleQuickSubmit(params) {
    setQuick(s => ({ ...s, loading: true, error: null, result: null, headers: null, params }))
    try {
      const { data, headers } = await search(params)
      setQuick(s => ({ ...s, loading: false, result: data, headers }))
    } catch (e) { setQuick(s => ({ ...s, loading: false, error: e })) }
  }

  async function handleDeepSubmit(params) {
    setDeep(s => ({ ...s, loading: true, error: null, result: null, headers: null }))
    try {
      const { data, headers } = await agentQuery(params)
      setDeep(s => ({ ...s, loading: false, result: data, headers }))
    } catch (e) { setDeep(s => ({ ...s, loading: false, error: e })) }
  }

  function pickChip(text) {
    if (mode === 'quick') setQuery(text)
    else setQuestion(text)
  }

  function quickErrMsg(e) {
    if (!e) return null
    if (e.status === 400) return { type: 'blocked', reason: e.body?.detail?.reason }
    if (e.status === 404) return { type: 'generic', message: 'No documents found in this collection. Add documents in Library first.' }
    if (e.status === 429) {
      const isBudget = e.body?.error === 'daily_token_budget_exceeded'
      return { type: 'generic', message: isBudget ? 'Daily token budget exceeded. Resets at midnight UTC.' : 'Rate limit reached. Try again in a moment.' }
    }
    if (e.status === 502) return { type: 'generic', message: 'AI provider temporarily unavailable.' }
    return { type: 'generic', message: e.message || 'Unexpected error.' }
  }

  const err = quickErrMsg(quick.error)
  const spring = { type: 'spring', bounce: 0, duration: 0.35 }

  return (
    <div className={styles.page}>
      <AnimatePresence initial={false}>
        {!hasAnswered && (
          <motion.div
            className={styles.hero}
            initial={false}
            exit={reduce ? { opacity: 0 } : { opacity: 0, height: 0, marginBottom: -24 }}
            transition={reduce ? { duration: 0.15 } : spring}
          >
            <h1 className={styles.headline}>Answers you can <em>trace</em>.</h1>
            <p className={styles.sub}>Ask anything about your documents.</p>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div layout transition={reduce ? { duration: 0.15 } : spring} className={styles.inputCard}>
        <SegmentedControl options={MODES} value={mode} onChange={setMode} />
        {mode === 'quick'
          ? <SearchForm onSubmit={handleQuickSubmit} loading={quick.loading} config={config} query={query} setQuery={setQuery} />
          : <AgentForm onSubmit={handleDeepSubmit} loading={deep.loading} config={config} question={question} setQuestion={setQuestion} />}
      </motion.div>

      {!hasAnswered && (
        <div className={styles.chips}>
          {SUGGESTIONS.map(s => (
            <button key={s} type="button" className={styles.chip} onClick={() => pickChip(s)}>{s}</button>
          ))}
        </div>
      )}

      {mode === 'quick' && (
        <>
          {err && (
            <div className={styles.errorSection}>
              {err.type === 'blocked'
                ? <GuardrailBanner type="blocked" reason={err.reason} />
                : <div className={styles.genericError} role="alert">{err.message}</div>}
            </div>
          )}
          {quick.result && (
            <div className={styles.results} role="region" aria-label="Answer" aria-live="polite">
              {quick.result.needs_clarification && <GuardrailBanner type="clarification" />}
              {quick.result.flagged && <GuardrailBanner type="flagged" reason={quick.result.flag_reason} confidence={quick.result.confidence} floor={floor} />}
              {quick.result.rerank_applied === false && quick.params?.rerank === true && (
                <p className={styles.rerankNote}>Reranking was requested but is unavailable in this deployment mode.</p>
              )}

              <div className={styles.answerLayout}>
                <div className={styles.answerPanel}>
                  <AnswerBlock answer={quick.result.answer} />
                  <FeedbackButtons requestId={quick.headers?.queryId} endpoint="/search" />
                </div>
                <div className={styles.rail}>
                  <div className={styles.railCard}><ConfidenceGauge confidence={quick.result.confidence} floor={floor} /></div>
                  <div className={styles.railCard}><MetaBar headers={quick.headers} /></div>
                </div>
              </div>

              {quick.result.results?.length > 0 && (
                <section aria-label="Source citations">
                  <h2 className={styles.citationsTitle}>Sources <span className={styles.citCount}>{quick.result.total_results}</span></h2>
                  <div className={styles.citList}>{quick.result.results.map((r, i) => <CitationCard key={`${r.document_id}-${i}`} result={r} index={i} />)}</div>
                </section>
              )}
            </div>
          )}
          {quick.loading && (
            <div className={styles.loading} aria-busy="true" aria-label="Searching…">
              <div className={styles.loadingBar} />
              <p>Searching your documents…</p>
            </div>
          )}
        </>
      )}

      {mode === 'deep' && (
        <>
          {deep.error && <div className={styles.genericError} role="alert">{deep.error.body?.detail || deep.error.message}</div>}
          {deep.loading && (
            <div className={styles.loading} aria-busy="true">
              <div className={styles.loadingBar} />
              <p>Researching across your documents…</p>
            </div>
          )}
          {deep.result && (
            <div className={styles.results} role="region" aria-live="polite" aria-label="Research answer">
              <div className={styles.answerLayout}>
                <div className={styles.answerPanel}>
                  <AnswerBlock answer={deep.result.answer} />
                  <FeedbackButtons requestId={deep.headers?.queryId} endpoint="/agent/query" />
                </div>
                <div className={styles.rail}>
                  <div className={styles.railCard}><ConfidenceGauge confidence={deep.result.confidence} floor={floor} /></div>
                  <div className={styles.railCard}><VerificationBadge verified={deep.result.verified} notes={deep.result.verification_notes} /></div>
                  <div className={styles.railCard}><MetaBar headers={deep.headers} /></div>
                </div>
              </div>

              <ReasoningChain steps={deep.result.reasoning_steps} toolCallCount={deep.result.tool_calls_made} />

              {deep.result.citations?.length > 0 && (
                <section>
                  <h2 className={styles.citationsTitle}>Sources <span className={styles.citCount}>{deep.result.citations.length}</span></h2>
                  <div className={styles.citList}>{deep.result.citations.map((c, i) => <AgentCitationCard key={`${c.document_id}-${i}`} citation={c} index={i} />)}</div>
                </section>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
