import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { ROUTER_FUTURE } from '@/app/future'
import { SessionProvider } from '@/app/session'
import type { ModuleList, SessionInfo } from '@/api/types'

const TEST_SESSION: SessionInfo = {
  csrf_token: 'test-csrf', expires_at: '2099-01-01T00:00:00Z', preview: false, scopes: ['admin'],
  tenant: { id: '00000000-0000-4000-8000-000000000001', slug: 'test' },
  principal: { id: '00000000-0000-4000-8000-000000000002', kind: 'user', name: 'Test User' },
}

const TEST_MODULES: ModuleList = {
  edition: 'agents', deploy_shape: 'single_tenant', modules: [
    { name: 'gateway', label: 'Gateway', pillar: 'gateway', enabled: true, nav_group: 'Governance', always_on: true },
    { name: 'agents', label: 'Agents', pillar: 'agents', enabled: true, nav_group: 'Governance', always_on: false },
  ],
}

/** A fresh query client per test, with retries off so errors show at once. */
export function testClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime: Infinity } } })
}

/** Render inside a query client and a memory router. */
export function renderWithProviders(ui: ReactElement, {
  route = '/', client = testClient(), session = TEST_SESSION, modules = TEST_MODULES,
}: { route?: string; client?: QueryClient; session?: SessionInfo; modules?: ModuleList | null } = {}): RenderResult & { client: QueryClient } {
  if (!client.getQueryData(['session'])) client.setQueryData(['session'], session)
  if (modules && !client.getQueryData(['system-modules', session.tenant.id, session.principal.id])) {
    client.setQueryData(['system-modules', session.tenant.id, session.principal.id], modules)
  }
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={ROUTER_FUTURE} initialEntries={[route]}><SessionProvider>{ui}</SessionProvider></MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, client }
}
