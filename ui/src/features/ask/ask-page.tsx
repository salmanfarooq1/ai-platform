import { useMutation, useQuery } from '@tanstack/react-query'
import { Brain, MagnifyingGlass, PaperPlaneRight } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { ApiError, isApiError } from '@/api/client'
import type { AgentAccepted, AgentResponse, SearchResponse, Verdict } from '@/api/types'
import { DenyCallout } from '@/components/governance/deny-callout'
import { ErrorState, PageHeader } from '@/components/governance/states'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { Button } from '@/components/ui/button'
import { Segmented } from '@/components/ui/segmented'
import { Skeleton } from '@/components/ui/skeleton'
import { Input, Textarea } from '@/components/ui/input'
import { addHistory } from '@/features/history/history-store'
import { AnswerView } from './answer-view'
import { GovernanceLine } from './governance-line'
import { denyFromError } from './deny'

type Mode = 'search' | 'agent'
type Outcome =
  | { kind: 'answer'; mode: Mode; data: SearchResponse | AgentResponse; requestId: string | null; queryId: string | null }
  | { kind: 'denied'; reason: string; message: string; requestId: string | null }

const KB_KEY = 'collection'
const POLL_START_MS = 1000
const POLL_MAX_MS = 4000
const POLL_GIVE_UP_MS = 10 * 60_000

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function isAccepted(data: AgentResponse | AgentAccepted): data is AgentAccepted {
  return 'execution_id' in data && 'job_id' in data && !('answer' in data)
}

/** The run is still going after the API's sync wait (202). Follow it by execution id until it ends, slowing the
 *  poll as it goes. A failed or stopped run becomes an error; a run that does not end in ten minutes gives up. */
async function followRun(executionId: string, onWaiting: () => void): Promise<AgentResponse> {
  onWaiting()
  const started = Date.now()
  let delay = POLL_START_MS
  for (;;) {
    await wait(delay)
    const run = await api.agentRun(executionId)
    if (run.status === 'succeeded' && run.result) return run.result
    if (run.status === 'failed' || run.status === 'stopped') {
      throw new ApiError(500, run.error_code ?? 'agent_run_failed', run.status === 'stopped' ? 'The run was stopped.' : 'The agent run failed.', null)
    }
    if (Date.now() - started > POLL_GIVE_UP_MS) throw new ApiError(504, 'run_timeout', 'The run is taking too long. Check the Agent runs page.', null)
    delay = Math.min(delay * 1.5, POLL_MAX_MS)
  }
}

/** The plain sentence and the policy field for a denied ask. The stage comes from the recorded decision. */
function DenyDetail({ requestId, reason }: { requestId: string | null; reason: string }) {
  const q = useQuery({
    queryKey: ['request', requestId],
    queryFn: () => api.requestDetail(requestId as string),
    enabled: !!requestId,
    retry: 1,
    retryDelay: 300,
    staleTime: 30_000,
  })
  const denied = q.data?.decisions.find((d) => d.outcome === 'deny')
  if (!denied) return null
  return <DenyCallout reason={denied.reason || reason} stage={denied.stage} policyVersion={denied.policy_version} action={denied.action} resource={denied.resource} />
}

export default function AskPage() {
  const [mode, setMode] = useState<Mode>('search')
  const [question, setQuestion] = useState('')
  const [kb, setKb] = useState(() => { try { return localStorage.getItem(KB_KEY) ?? '' } catch { return '' } })
  // Once the field has had focus, the page never fills it in. A late reply from the config call must not overwrite a value being typed.
  const touched = useRef(false)
  const config = useQuery({ queryKey: ['config'], queryFn: api.config, retry: false, staleTime: 300_000 })
  const kbs = Object.keys(config.data?.namespaces ?? {})

  // Start on the first knowledge base the policy shows. The field also accepts another slug, so a person can
  // see what the gateway does with a knowledge base the tenant policy does not allow.
  useEffect(() => {
    if (!kb && !touched.current && kbs.length > 0) setKb(kbs[0] ?? '')
  }, [kbs, kb])

  const [stillWorking, setStillWorking] = useState(false)
  const ask = useMutation<Outcome, unknown, { mode: Mode; question: string; kb: string }>({
    mutationFn: async ({ mode, question, kb }) => {
      try {
        if (mode === 'search') {
          const r = await api.search({ query: question, namespace: kb })
          return { kind: 'answer', mode, data: r.data, requestId: r.requestId, queryId: r.headers.get('X-Query-ID') }
        }
        const r = await api.agent({ question, namespace: kb })
        if (r.status === 202 && isAccepted(r.data)) {
          const data = await followRun(r.data.execution_id, () => setStillWorking(true))
          return { kind: 'answer', mode, data, requestId: r.requestId, queryId: r.headers.get('X-Query-ID') }
        }
        return { kind: 'answer', mode, data: r.data as AgentResponse, requestId: r.requestId, queryId: r.headers.get('X-Query-ID') }
      } catch (e) {
        const denial = denyFromError(e)
        if (denial) return { kind: 'denied', ...denial }
        throw e
      }
    },
    onSettled: () => setStillWorking(false),
    onSuccess: (out, vars) => {
      const verdict: Verdict = out.kind === 'denied' ? 'deny' : 'allow'
      addHistory({ mode: vars.mode, kb: vars.kb, question: vars.question, requestId: out.requestId, verdict, reason: out.kind === 'denied' ? out.reason : null })
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q || !kb || ask.isPending) return
    try { localStorage.setItem(KB_KEY, kb) } catch { /* optional */ }
    ask.mutate({ mode, question: q, kb })
  }

  const out = ask.data
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Ask">Answers come with their evidence, a confidence level and a receipt for the call.</PageHeader>

      <form onSubmit={submit} className="mb-6 flex flex-col gap-3 rounded-md border border-hairline bg-surface p-4" aria-label="Ask a question">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented<Mode>
            label="Mode"
            value={mode}
            onChange={setMode}
            options={[
              { value: 'search', label: 'Search', icon: <MagnifyingGlass size={14} aria-hidden="true" /> },
              { value: 'agent', label: 'Agent', icon: <Brain size={14} aria-hidden="true" /> },
            ]}
          />
          <label className="ml-auto flex items-center gap-2 text-footnote text-fg-secondary">
            Knowledge base
            <Input
              aria-label="Knowledge base"
              list="kb-options"
              value={kb}
              onFocus={() => { touched.current = true }}
              onChange={(e) => setKb(e.target.value.trim())}
              placeholder={config.isLoading ? 'Loading' : 'slug'}
              spellCheck={false}
              autoComplete="off"
              className="mono h-9 w-40"
            />
            <datalist id="kb-options">{kbs.map((k) => <option key={k} value={k} />)}</datalist>
          </label>
        </div>
        <label htmlFor="question" className="sr-only">Question</label>
        <Textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={config.data?.max_query_length}
          placeholder={mode === 'search' ? 'Ask a question about your documents' : 'Describe what the agent should research'}
        />
        <div className="flex items-center justify-between gap-3">
          <p className="text-footnote text-fg-secondary">
            {mode === 'search' ? 'Search retrieves passages and writes one answer.' : 'The agent may call several tools. Each call is checked by policy.'}
          </p>
          <Button type="submit" disabled={!question.trim() || !kb || ask.isPending}>
            <PaperPlaneRight size={16} aria-hidden="true" /> {ask.isPending ? 'Asking' : 'Ask'}
          </Button>
        </div>
        {config.error ? <p className="text-footnote text-deny" role="alert">Could not load knowledge bases ({isApiError(config.error) ? config.error.code : 'error'}).</p> : null}
      </form>

      {ask.isPending ? (
        <div role="status" aria-label="Working on the answer" className="flex flex-col gap-3">
          {stillWorking ? <p className="text-callout text-fg-secondary">Still working. The run is queued or running on a worker, and the answer appears here when it ends.</p> : null}
          <Skeleton className="h-7 w-64" /><Skeleton className="h-28" /><Skeleton className="h-20" />
        </div>
      ) : null}

      {ask.error ? <ErrorState error={ask.error} title="The question could not be answered." onRetry={() => ask.mutate({ mode, question: question.trim(), kb })} /> : null}

      {out?.kind === 'denied' ? (
        <div role="alert" aria-label="Denied" className="flex flex-col gap-3 rounded-md border border-hairline border-l-4 border-l-deny bg-surface p-4">
          <VerdictBadge verdict="deny" reason={out.reason} />
          <p className="text-callout text-fg">This request was stopped by the gateway before any data was read.</p>
          <p className="mono text-footnote text-fg-secondary">{out.message}</p>
          <DenyDetail requestId={out.requestId} reason={out.reason} />
          <GovernanceLine requestId={out.requestId} />
          {out.requestId ? (
            <Link to={`/app/decisions?request_id=${encodeURIComponent(out.requestId)}`} className="text-callout font-medium text-seal underline-offset-2 hover:underline">
              Open receipt in Decisions
            </Link>
          ) : null}
        </div>
      ) : null}

      {out?.kind === 'answer' ? <AnswerView kind={out.mode} data={out.data} requestId={out.requestId} queryId={out.queryId} floor={config.data?.confidence_floor} /> : null}

      {!out && !ask.isPending && !ask.error ? (
        <p className="text-callout text-fg-secondary">The answer, its evidence and the receipt link appear here.</p>
      ) : null}
    </div>
  )
}
