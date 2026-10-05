import { ThumbsDown, ThumbsUp } from '@phosphor-icons/react'
import { useState } from 'react'
import { api } from '@/api/endpoints'
import { cn } from '@/lib/utils'

/** Rate an answer. It posts to /v1/feedback with the query id the API returned. */
export function FeedbackButtons({ queryId, endpoint }: { queryId: string; endpoint: string }) {
  const [sent, setSent] = useState<'up' | 'down' | null>(null)
  const [failed, setFailed] = useState(false)

  async function rate(rating: 'up' | 'down') {
    if (sent) return
    try {
      await api.feedback({ request_id: queryId, endpoint, rating })
      setSent(rating)
      setFailed(false)
    } catch {
      setFailed(true)
    }
  }
  const btn = 'rounded-sm p-1.5 text-fg-secondary hover:bg-muted disabled:opacity-60'
  return (
    <div role="group" aria-label="Rate this answer" className="flex items-center gap-1">
      <button type="button" className={cn(btn, sent === 'up' && 'bg-brand-tint text-fg')} disabled={!!sent} aria-pressed={sent === 'up'} aria-label="Helpful" onClick={() => void rate('up')}>
        <ThumbsUp size={16} />
      </button>
      <button type="button" className={cn(btn, sent === 'down' && 'bg-brand-tint text-fg')} disabled={!!sent} aria-pressed={sent === 'down'} aria-label="Not helpful" onClick={() => void rate('down')}>
        <ThumbsDown size={16} />
      </button>
      {sent ? <span className="ml-2 text-footnote text-fg-secondary">Thanks for the feedback</span> : null}
      {failed ? <span role="alert" className="ml-2 text-footnote text-deny">Could not send feedback. Try again.</span> : null}
    </div>
  )
}
