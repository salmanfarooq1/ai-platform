import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import type { AgentResponse, PlatformConfig } from '@/api/types'
import { renderWithProviders } from '@/test/render'
import AskPage from './ask-page'

const config = { namespaces: { legal: 'Legal' }, confidence_floor: 0.5, max_query_length: 1000, daily_token_budget: 1, rate_limit_rpm: 1, rate_limit_window_seconds: 60, reranker_enabled: false, agent_defaults: { max_iterations: 1, enable_verifier: false, max_verify_retries: 0 } } as PlatformConfig
const EXEC = '3f1c2d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'
const answer = { question: 'q', answer: 'Seventy-two hours.', confidence: 0.9, citations: [], model_used: 'fake', verified: true, verification_notes: '', reasoning_steps: [], tool_calls_made: 1, total_time_seconds: 30, total_cost_usd: 0, flagged: false, flag_reason: null } as AgentResponse
const accepted = (status: number, data: unknown) => ({ data, requestId: 'req-1', headers: new Headers(), status }) as never

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

async function askAgent() {
  vi.spyOn(api, 'config').mockResolvedValue(config)
  renderWithProviders(<AskPage />)
  await userEvent.click(screen.getByRole('radio', { name: 'Agent' }))
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Knowledge base' })).toHaveValue('legal'))
  await userEvent.type(screen.getByRole('textbox', { name: 'Question' }), 'How long?')
  await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

describe('Ask in Agent mode with a slow run', () => {
  it('shows a quiet "Still working" state while it polls the run, then the answer', async () => {
    vi.spyOn(api, 'agent').mockResolvedValue(accepted(202, { execution_id: EXEC, job_id: 'job-1' }))
    const run = vi.spyOn(api, 'agentRun')
      .mockResolvedValueOnce({ execution_id: EXEC, job_id: 'job-1', status: 'running', error_code: null, created_at: '', started_at: '', finished_at: null, result: null, decisions_url: '' })
      .mockResolvedValue({ execution_id: EXEC, job_id: 'job-1', status: 'succeeded', error_code: null, created_at: '', started_at: '', finished_at: '', result: answer, decisions_url: '' })
    await askAgent()
    expect(await screen.findByText(/Still working/)).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Working on the answer' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('region', { name: 'Answer' })).toHaveTextContent('Seventy-two hours.'), { timeout: 8000 })
    expect(run).toHaveBeenCalledWith(EXEC)
    expect(screen.queryByText(/Still working/)).not.toBeInTheDocument()
  }, 15000)

  it('a run that failed becomes an error, not a silent empty answer', async () => {
    vi.spyOn(api, 'agent').mockResolvedValue(accepted(202, { execution_id: EXEC, job_id: 'job-1' }))
    vi.spyOn(api, 'agentRun').mockResolvedValue({ execution_id: EXEC, job_id: 'job-1', status: 'failed', error_code: 'agent_run_failed', created_at: '', started_at: '', finished_at: '', result: null, decisions_url: '' })
    await askAgent()
    expect(await screen.findByText('The question could not be answered.', {}, { timeout: 4000 })).toBeInTheDocument()
  }, 15000)

  it('an answer that arrives at once (200) never polls', async () => {
    vi.spyOn(api, 'agent').mockResolvedValue(accepted(200, answer))
    const run = vi.spyOn(api, 'agentRun')
    await askAgent()
    expect(await screen.findByRole('region', { name: 'Answer' })).toHaveTextContent('Seventy-two hours.')
    expect(run).not.toHaveBeenCalled()
  })
})
