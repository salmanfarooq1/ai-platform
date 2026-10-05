import { useQuery } from '@tanstack/react-query'
import { ShieldCheck } from '@phosphor-icons/react'
import { Link } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { isApiError } from '@/api/client'
import { Skeleton } from '@/components/ui/skeleton'
import { governanceLineText } from './governance-text'

/** The governance line under an answer. It reads the request the answer belongs to and links to its drawer. */
export function GovernanceLine({ requestId }: { requestId: string | null }) {
  const q = useQuery({
    queryKey: ['request', requestId],
    queryFn: () => api.requestDetail(requestId as string),
    enabled: !!requestId,
    retry: 1,
    retryDelay: 300,
    staleTime: 30_000,
  })
  if (!requestId) return null
  if (q.isLoading) return <Skeleton aria-hidden="true" className="h-5 w-72" />
  if (q.error || !q.data) {
    const code = isApiError(q.error) ? q.error.code : 'unknown_error'
    return <p className="text-footnote text-fg-secondary" data-testid="governance-line-error">The governance record is not available yet. <span className="mono">{code}</span></p>
  }
  return (
    <Link
      to={`/app/requests/${encodeURIComponent(requestId)}`}
      data-testid="governance-line"
      className="inline-flex items-center gap-1.5 self-start rounded-sm text-callout text-fg-secondary underline-offset-2 transition-colors duration-fast hover:text-seal hover:underline"
    >
      <ShieldCheck size={16} aria-hidden="true" />
      {governanceLineText(q.data)}
    </Link>
  )
}
