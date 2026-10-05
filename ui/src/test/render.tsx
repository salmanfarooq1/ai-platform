import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { ROUTER_FUTURE } from '@/app/future'

/** A fresh query client per test, with retries off so errors show at once. */
export function testClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime: Infinity } } })
}

/** Render inside a query client and a memory router. */
export function renderWithProviders(ui: ReactElement, { route = '/', client = testClient() }: { route?: string; client?: QueryClient } = {}): RenderResult & { client: QueryClient } {
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={ROUTER_FUTURE} initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, client }
}
