import { Tray, WarningOctagon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { isApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

/** The error state: the API error code and request id, with a retry action. */
export function ErrorState({ error, onRetry, title = 'Could not load this.' }: { error: unknown; onRetry?: () => void; title?: string }) {
  const code = isApiError(error) ? error.code : 'unknown_error'
  const requestId = isApiError(error) ? error.requestId : null
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-md border border-hairline bg-surface p-4">
      <div className="flex items-center gap-2 text-deny">
        <WarningOctagon size={20} weight="bold" aria-hidden="true" />
        <h3 className="text-deny">{title}</h3>
      </div>
      <p className="text-callout text-fg-secondary">{message}</p>
      <dl className="mono grid grid-cols-[auto_1fr] gap-x-3 text-footnote">
        <dt className="text-fg-secondary">code</dt>
        <dd data-testid="error-code">{code}</dd>
        <dt className="text-fg-secondary">request_id</dt>
        <dd data-testid="error-request-id">{requestId ?? 'none'}</dd>
      </dl>
      {onRetry ? <Button variant="secondary" size="sm" onClick={onRetry}>Try again</Button> : null}
    </div>
  )
}

/** The empty state says what would appear here and how to make it appear. */
export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-md border border-dashed border-hairline p-6">
      <Tray size={24} aria-hidden="true" className="text-fg-secondary" />
      <h3>{title}</h3>
      <p className="max-w-prose text-callout text-fg-secondary">{children}</p>
      {action}
    </div>
  )
}

/** Skeleton rows in the final table shape. Never a centered spinner. */
export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" role="status" className="flex flex-col gap-2">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }, (_, c) => <Skeleton key={c} className="h-6" />)}
        </div>
      ))}
    </div>
  )
}

export function PageHeader({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1>{title}</h1>
        {children ? <p className="mt-1 max-w-prose text-callout text-fg-secondary">{children}</p> : null}
      </div>
      {actions}
    </header>
  )
}
