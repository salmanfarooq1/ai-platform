import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { api } from '@/api/endpoints'
import type { AgentResponse, ModuleList, PlatformConfig } from '@/api/types'
import { renderWithProviders, testClient } from '@/test/render'
import AskPage from './ask-page'

const config = (namespaces: Record<string, string>): PlatformConfig => ({
  namespaces, confidence_floor: 0.5, max_query_length: 1000, daily_token_budget: 1, rate_limit_rpm: 1, rate_limit_window_seconds: 60, reranker_enabled: false,
  agent_defaults: { max_iterations: 1, enable_verifier: false, max_verify_retries: 0 },
})

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

describe('AskPage knowledge base field', () => {
  it('starts on the first knowledge base the policy allows', async () => {
    const client = testClient()
    client.setQueryData(['config'], config({ default: 'General', legal: 'Legal' }))
    renderWithProviders(<AskPage />, { client })
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Knowledge base' })).toHaveValue('default'))
  })

  it('does not fill the field in once the person has focused it, even if the config reply is late', async () => {
    let resolve: (c: PlatformConfig) => void = () => {}
    vi.spyOn(api, 'config').mockReturnValue(new Promise((r) => { resolve = r }))
    renderWithProviders(<AskPage />)
    const field = screen.getByRole('combobox', { name: 'Knowledge base' })
    await userEvent.click(field)
    resolve(config({ default: 'General' }))
    await waitFor(() => expect(api.config).toHaveBeenCalled())
    await userEvent.type(field, 'legal')
    expect(field).toHaveValue('legal')
  })
})

const modulesWithAgents = (enabled: boolean): ModuleList => ({
  edition: enabled ? 'agents' : 'gateway', deploy_shape: 'single_tenant', modules: [
    { name: 'gateway', label: 'Gateway', pillar: 'gateway', enabled: true, nav_group: 'Governance', always_on: true },
    { name: 'agents', label: 'Agents', pillar: 'agents', enabled, nav_group: 'Governance', always_on: false },
  ],
})

describe('Ask module availability', () => {
  it('agent mode hidden when agents off', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ legal: 'Legal' }))
    const search = vi.spyOn(api, 'search').mockResolvedValue({
      data: { answer: 'Found it.', confidence: 0.9, flagged: false, needs_clarification: false, query: 'How long?', rerank_applied: false, results: [], total_results: 0 },
      requestId: 'req-search', headers: new Headers(), status: 200,
    })
    renderWithProviders(<AskPage />, { modules: modulesWithAgents(false) })

    expect(screen.queryByRole('radio', { name: 'Agent' })).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Search' })).toBeInTheDocument()
    await userEvent.type(screen.getByRole('textbox', { name: 'Question' }), 'How long?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(search).toHaveBeenCalledWith({ query: 'How long?', namespace: 'legal' }))
  })

  it('stale agent mode sends no agent request', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ legal: 'Legal' }))
    const agent = vi.spyOn(api, 'agent')
    const search = vi.spyOn(api, 'search').mockResolvedValue({
      data: { answer: 'Found it.', confidence: 0.9, flagged: false, needs_clarification: false, query: 'How long?', rerank_applied: false, results: [], total_results: 0 },
      requestId: 'req-search', headers: new Headers(), status: 200,
    })
    const { client } = renderWithProviders(<AskPage />)
    await userEvent.click(screen.getByRole('radio', { name: 'Agent' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Question' }), 'How long?')

    await act(async () => {
      client.setQueryData(['system-modules', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002'], modulesWithAgents(false))
    })
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Search' })).toHaveAttribute('data-state', 'on'))
    expect(screen.getByText('Agent mode is off for this workspace.')).toBeInTheDocument()
    expect(agent).not.toHaveBeenCalled()
    expect(search).not.toHaveBeenCalled()
  })

  it('retry keeps the original mode', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ legal: 'Legal' }))
    const agent = vi.spyOn(api, 'agent').mockRejectedValue(new Error('agent unavailable'))
    const search = vi.spyOn(api, 'search')
    const { client } = renderWithProviders(<AskPage />)
    await userEvent.click(screen.getByRole('radio', { name: 'Agent' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Question' }), 'How long?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByRole('alert')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(agent).toHaveBeenCalledTimes(2))
    expect(agent).toHaveBeenLastCalledWith({ question: 'How long?', namespace: 'legal' })
    expect(search).toHaveBeenCalledTimes(0)

    await act(async () => {
      client.setQueryData(['system-modules', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002'], modulesWithAgents(false))
    })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument())
    expect(screen.getByText('Agent mode is off for this workspace.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask with Search instead' })).toBeInTheDocument()
    expect(agent).toHaveBeenCalledTimes(2)
    expect(search).toHaveBeenCalledTimes(0)
  })

  it('keeps a completed answer visible when agents turn off', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ legal: 'Legal' }))
    vi.spyOn(api, 'agent').mockResolvedValue({
      data: { question: 'How long?', answer: 'Seventy-two hours.', confidence: 0.9, citations: [], model_used: 'fake', verified: true, verification_notes: '', reasoning_steps: [], tool_calls_made: 1, total_time_seconds: 1, total_cost_usd: 0, flagged: false, flag_reason: null, agent_reported: [] } as AgentResponse,
      requestId: 'req-agent', headers: new Headers(), status: 200,
    })
    const { client } = renderWithProviders(<AskPage />)
    await userEvent.click(screen.getByRole('radio', { name: 'Agent' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Question' }), 'How long?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByRole('region', { name: 'Answer' })).toHaveTextContent('Seventy-two hours.')

    await act(async () => {
      client.setQueryData(['system-modules', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002'], modulesWithAgents(false))
    })
    expect(await screen.findByText('Agent mode is off for this workspace.')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Answer' })).toHaveTextContent('Seventy-two hours.')
  })

  it('shows a server module_disabled response in the deny view with its request id', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ legal: 'Legal' }))
    vi.spyOn(api, 'agent').mockRejectedValue(new ApiError(404, 'module_disabled', 'The agents module is disabled.', 'req-server'))
    vi.spyOn(api, 'requestDetail').mockResolvedValue({ decisions: [] } as never)
    renderWithProviders(<AskPage />)
    await userEvent.click(screen.getByRole('radio', { name: 'Agent' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Question' }), 'How long?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByRole('alert', { name: 'Denied' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open receipt in Decisions' })).toHaveAttribute('href', '/app/decisions?request_id=req-server')
  })

  it('asks with Search only after the explicit fallback is clicked', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ legal: 'Legal' }))
    const agent = vi.spyOn(api, 'agent')
    const search = vi.spyOn(api, 'search').mockResolvedValue({
      data: { answer: 'Found it.', confidence: 0.9, flagged: false, needs_clarification: false, query: 'How long?', rerank_applied: false, results: [], total_results: 0 },
      requestId: 'req-search', headers: new Headers(), status: 200,
    })
    const { client } = renderWithProviders(<AskPage />)
    await userEvent.click(screen.getByRole('radio', { name: 'Agent' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Question' }), 'How long?')

    await act(async () => {
      client.setQueryData(['system-modules', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002'], modulesWithAgents(false))
    })
    await screen.findByRole('button', { name: 'Ask with Search instead' })
    expect(agent).not.toHaveBeenCalled()
    expect(search).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Ask with Search instead' }))
    await waitFor(() => expect(search).toHaveBeenCalledTimes(1))
    expect(search).toHaveBeenCalledWith({ query: 'How long?', namespace: 'legal' })
    expect(agent).not.toHaveBeenCalled()
  })
})
