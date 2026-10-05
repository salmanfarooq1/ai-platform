import { ArrowUpRight, FileText } from '@phosphor-icons/react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'
import type { AgentResponse, SearchResponse } from '@/api/types'
import { VerdictBadge } from '@/components/governance/verdict-badge'
import { cn } from '@/lib/utils'
import { FeedbackButtons } from './feedback-buttons'
import { confidenceLevel, type ConfidenceLevel } from './confidence'

const LEVEL_CLS: Record<ConfidenceLevel, string> = { high: 'bg-success-tint text-success', medium: 'bg-warning-tint text-warning', low: 'bg-danger-tint text-danger' }

export function ConfidenceChip({ score, floor }: { score: number; floor?: number }) {
  const level = confidenceLevel(score, floor)
  return (
    <span className={cn('tabular rounded-full px-2.5 py-1 text-callout font-medium', LEVEL_CLS[level])} data-testid="confidence">
      {level.toUpperCase()} {Math.round(score * 100)}%
    </span>
  )
}

export function EvidenceCard({ title, meta, excerpt, index }: { title: string; meta: string; excerpt: string; index: number }) {
  return (
    <li className="rounded-md border border-hairline bg-surface p-3">
      <div className="mb-1 flex items-center gap-2 text-callout font-medium">
        <FileText size={16} aria-hidden="true" className="shrink-0 text-fg-secondary" />
        <span className="truncate">{index + 1}. {title}</span>
      </div>
      <p className="mono mb-1.5 text-footnote text-fg-secondary">{meta}</p>
      <p className="line-clamp-4 text-callout text-fg-secondary">{excerpt}</p>
    </li>
  )
}

interface AnswerViewProps {
  kind: 'search' | 'agent'
  data: SearchResponse | AgentResponse
  requestId: string | null
  queryId?: string | null
  floor?: number
}

export function AnswerView({ kind, data, requestId, queryId, floor }: AnswerViewProps) {
  const search = kind === 'search' ? (data as SearchResponse) : null
  const agent = kind === 'agent' ? (data as AgentResponse) : null
  const confidence = data.confidence ?? 0
  const evidence = search
    ? search.results.map((r) => ({
        title: String((r.metadata as Record<string, unknown>)['source_filename'] ?? r.document_id),
        meta: `${r.namespace} score ${r.score.toFixed(3)}`,
        excerpt: r.content,
      }))
    : (agent?.citations ?? []).map((c) => ({
        title: c.source_filename, meta: `chunk ${c.chunk_index} relevance ${c.relevance_score.toFixed(3)}`, excerpt: c.excerpt,
      }))

  return (
    <div className="flex flex-col gap-4" role="region" aria-label="Answer" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <VerdictBadge verdict="allow" />
        <ConfidenceChip score={confidence} floor={floor} />
        {agent?.verified != null ? (
          <span className="rounded-full bg-muted px-2.5 py-1 text-callout text-fg-secondary">{agent.verified ? 'Verified against sources' : 'Not verified'}</span>
        ) : null}
        {requestId ? (
          <Link to={`/app/decisions?request_id=${encodeURIComponent(requestId)}`} className="ml-auto inline-flex items-center gap-1 text-callout font-medium text-brand underline-offset-2 hover:underline">
            Open receipt in Decisions <ArrowUpRight size={14} aria-hidden="true" />
          </Link>
        ) : null}
      </div>

      {data.flagged ? (
        <p role="note" className="rounded-sm bg-warning-tint px-3 py-2 text-callout text-warning">
          This answer was flagged{data.flag_reason ? `: ${data.flag_reason}` : ''}. Check the evidence before relying on it.
        </p>
      ) : null}

      <div className="rounded-md border border-hairline bg-surface p-4 text-body leading-relaxed text-fg [&_a]:text-brand [&_li]:ml-5 [&_li]:list-disc [&_p+p]:mt-3 [&_table]:text-callout">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.answer}</ReactMarkdown>
      </div>

      {queryId ? <FeedbackButtons queryId={queryId} endpoint={kind === 'search' ? '/search' : '/agent/query'} /> : null}

      {agent && agent.reasoning_steps.length > 0 ? (
        <details className="rounded-md border border-hairline bg-surface p-3">
          <summary className="cursor-pointer text-callout font-medium">Reasoning steps ({agent.reasoning_steps.length}), {agent.tool_calls_made} tool calls</summary>
          <ol className="mono mt-2 flex list-decimal flex-col gap-1 pl-5 text-footnote text-fg-secondary">
            {agent.reasoning_steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </details>
      ) : null}

      <section aria-label="Evidence">
        <h2 className="mb-2 text-headline">Evidence <span className="tabular text-fg-secondary">{evidence.length}</span></h2>
        {evidence.length === 0 ? (
          <p className="text-callout text-fg-secondary">No sources were returned for this answer.</p>
        ) : (
          <ul className="m-0 grid list-none gap-2 p-0 md:grid-cols-2">
            {evidence.map((e, i) => <EvidenceCard key={`${e.title}-${i}`} index={i} {...e} />)}
          </ul>
        )}
      </section>
    </div>
  )
}
