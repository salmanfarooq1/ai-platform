import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import type { PlatformConfig } from '@/api/types'
import { renderWithProviders } from '@/test/render'
import AskPage from './ask-page'

const config = (namespaces: Record<string, string>): PlatformConfig => ({
  namespaces, confidence_floor: 0.5, max_query_length: 1000, daily_token_budget: 1, rate_limit_rpm: 1, rate_limit_window_seconds: 60, reranker_enabled: false,
  agent_defaults: { max_iterations: 1, enable_verifier: false, max_verify_retries: 0 },
})

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

describe('AskPage knowledge base field', () => {
  it('starts on the first knowledge base the policy allows', async () => {
    vi.spyOn(api, 'config').mockResolvedValue(config({ default: 'General', legal: 'Legal' }))
    renderWithProviders(<AskPage />)
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
