import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ROUTER_FUTURE } from '@/app/future'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { DecisionsTable } from '@/features/decisions/decisions-table'
import { decision, detail } from '@/test/fixtures'
import { EmptyState, ErrorState } from './states'
import { Receipt } from './receipt'
import { TraceTimeline } from './trace-timeline'
import { VerdictBadge } from './verdict-badge'

describe('VerdictBadge', () => {
  it('shows an icon, a word and the verdict for each state', () => {
    const { rerender, container } = render(<VerdictBadge verdict="allow" />)
    expect(screen.getByText('Allowed')).toBeInTheDocument()
    expect(container.querySelector('svg')).not.toBeNull()
    expect(container.querySelector('[data-verdict="allow"]')).not.toBeNull()

    rerender(<VerdictBadge verdict="escalate" />)
    expect(screen.getByText('Needs approval')).toBeInTheDocument()
    rerender(<VerdictBadge verdict="unrecorded" />)
    expect(screen.getByText('Not recorded')).toBeInTheDocument()
  })

  it('shows the reason code in mono for a denial, and not for an allow', () => {
    const { rerender } = render(<VerdictBadge verdict="deny" reason="kb_not_allowed" />)
    const code = screen.getByText('kb_not_allowed')
    expect(code.tagName).toBe('CODE')
    expect(screen.getByText('Denied')).toBeInTheDocument()
    rerender(<VerdictBadge verdict="allow" reason="allowed" />)
    expect(screen.queryByText('allowed')).not.toBeInTheDocument()
  })
})

describe('TraceTimeline', () => {
  it('lists the steps oldest first with action, resource, stage and time to the next step', () => {
    render(<TraceTimeline steps={detail().trace} currentId="dec-1" />)
    const items = within(screen.getByRole('list', { name: 'Request trace' })).getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('agent.run')
    expect(items[1]).toHaveTextContent('kb.read')
    expect(items[1]).toHaveAttribute('aria-current', 'step')
    expect(items[0]).toHaveTextContent('100 ms to next')
    expect(items[2]).not.toHaveTextContent('to next')
  })

  it('marks the denied step and shows its reason code', () => {
    render(<TraceTimeline steps={detail().trace} />)
    const denied = screen.getAllByRole('listitem').find((li) => li.getAttribute('data-outcome') === 'deny')
    expect(denied).toBeDefined()
    expect(denied).toHaveTextContent('Denied')
    expect(denied).toHaveTextContent('kb_not_allowed')
  })

  it('says so when there are no steps', () => {
    render(<TraceTimeline steps={[]} />)
    expect(screen.getByText('No steps were recorded for this request.')).toBeInTheDocument()
  })
})

describe('Receipt', () => {
  it('shows the ids, policy version, tenant and the input hash in mono', () => {
    render(<Receipt decision={detail()} />)
    const receipt = screen.getByRole('region', { name: 'Receipt' })
    for (const label of ['Decision id', 'Policy version', 'Tenant', 'Input SHA-256']) expect(receipt).toHaveTextContent(label)
    expect(within(receipt).getByText('a'.repeat(64)).tagName).toBe('CODE')
    expect(within(receipt).getByText('northwind')).toBeInTheDocument()
    expect(receipt).toHaveTextContent('The platform keeps a hash of the input, not the text.')
  })

  it('shows "none" for a missing hash or policy version, and has a copy button for each value', () => {
    render(<Receipt decision={detail({ input_sha256: null, policy_version: null })} />)
    expect(screen.getAllByText('none').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: 'Copy decision id' })).toBeInTheDocument()
  })

  it('copies a value to the clipboard', async () => {
    const user = userEvent.setup()
    render(<Receipt decision={detail()} />)
    await user.click(screen.getByRole('button', { name: 'Copy decision id' }))
    expect(await screen.findByRole('button', { name: 'decision id copied' })).toBeInTheDocument()
    expect(await navigator.clipboard.readText()).toBe('dec-1')
  })
})

describe('DecisionsTable states', () => {
  const wrap = (ui: React.ReactElement) => render(<MemoryRouter future={ROUTER_FUTURE}>{ui}</MemoryRouter>)

  it('loading: shows skeleton rows in the table shape, not a spinner', () => {
    wrap(<DecisionsTable items={undefined} isLoading />)
    expect(screen.getByRole('status', { name: 'Loading' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('empty: says what would appear and how to make it appear', () => {
    wrap(<DecisionsTable items={[]} isLoading={false} />)
    expect(screen.getByText('No decisions yet.')).toBeInTheDocument()
    expect(screen.getByText(/Ask a question in the workspace/)).toBeInTheDocument()
  })

  it('empty with filters: points at the filters', () => {
    wrap(<DecisionsTable items={[]} isLoading={false} filtered />)
    expect(screen.getByText('No decisions match these filters.')).toBeInTheDocument()
  })

  it('error: shows the API code and request id, and retries', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    wrap(<DecisionsTable items={undefined} isLoading={false} error={new ApiError(403, 'forbidden', 'Missing scope audit:read', 'req-77')} onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByTestId('error-code')).toHaveTextContent('forbidden')
    expect(screen.getByTestId('error-request-id')).toHaveTextContent('req-77')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('rows: one row per decision with verdict, resource and policy version, and a link to the detail', () => {
    wrap(<DecisionsTable items={[decision(), decision({ id: 'dec-2', outcome: 'deny', reason: 'kb_not_allowed', resource: 'legal', policy_version: null, principal: null })]} isLoading={false} selectedId="dec-1" search="?outcome=deny" />)
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveAttribute('aria-selected', 'true')
    expect(rows[1]).toHaveAttribute('data-outcome', 'deny')
    expect(rows[1]).toHaveTextContent('kb_not_allowed')
    expect(rows[1]).toHaveTextContent('default') // no policy version means the platform default
    expect(rows[1]).toHaveTextContent('unknown') // null principal
    expect(within(rows[0] as HTMLElement).getByRole('link')).toHaveAttribute('href', '/app/decisions/dec-1?outcome=deny')
  })
})

describe('shared states', () => {
  it('ErrorState falls back when the error is not an ApiError', () => {
    render(<ErrorState error={new Error('boom')} />)
    expect(screen.getByTestId('error-code')).toHaveTextContent('unknown_error')
    expect(screen.getByTestId('error-request-id')).toHaveTextContent('none')
  })
  it('EmptyState renders its title and text', () => {
    render(<EmptyState title="Nothing here">Do this to fill it.</EmptyState>)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
    expect(screen.getByText('Do this to fill it.')).toBeInTheDocument()
  })
})
