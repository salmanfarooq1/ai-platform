import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { ROUTER_FUTURE } from './future'
import { SessionProvider } from './session'

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 15_000 } } }))
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter future={ROUTER_FUTURE}>
        <SessionProvider>{children}</SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
