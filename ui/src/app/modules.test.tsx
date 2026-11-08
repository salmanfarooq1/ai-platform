import { act, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import type { ModuleList, SessionInfo } from '@/api/types'
import { renderWithProviders, testClient } from '@/test/render'
import ModulesPage from '@/features/system/modules-page'

const firstSession: SessionInfo = {
  csrf_token: 'csrf-a', expires_at: '2099-01-01T00:00:00Z', preview: false, scopes: ['admin'],
  tenant: { id: '00000000-0000-4000-8000-000000000001', slug: 'test' },
  principal: { id: '00000000-0000-4000-8000-000000000002', kind: 'user', name: 'First' },
}
const secondSession: SessionInfo = {
  ...firstSession, csrf_token: 'csrf-b',
  principal: { ...firstSession.principal, id: '00000000-0000-4000-8000-000000000003', name: 'Second' },
}
const moduleList = (edition: string): ModuleList => ({ edition, deploy_shape: 'single_tenant', modules: [] })

afterEach(() => vi.restoreAllMocks())

describe('module metadata', () => {
  it('metadata is refetched on session change', async () => {
    let resolveSecond: (value: ModuleList) => void = () => {}
    const fetchModules = vi.spyOn(api, 'modules')
      .mockResolvedValueOnce(moduleList('first identity'))
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve }))
    const client = testClient()
    const { client: queryClient } = renderWithProviders(<ModulesPage />, { client, session: firstSession, modules: null })

    await waitFor(() => expect(fetchModules).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('first identity')).toBeInTheDocument()
    await act(async () => { queryClient.setQueryData(['session'], secondSession) })

    await waitFor(() => expect(fetchModules).toHaveBeenCalledTimes(2))
    expect(queryClient.getQueryData(['system-modules', firstSession.tenant.id, firstSession.principal.id])).toEqual(moduleList('first identity'))
    expect(queryClient.getQueryData(['system-modules', secondSession.tenant.id, secondSession.principal.id])).toBeUndefined()
    expect(screen.queryByText('first identity')).not.toBeInTheDocument()

    await act(async () => { resolveSecond(moduleList('second identity')) })
    expect(await screen.findByText('second identity')).toBeInTheDocument()
  })
})
