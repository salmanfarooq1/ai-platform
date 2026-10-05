import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { addHistory, readHistory } from '@/features/history/history-store'
import { SessionProvider, useSession } from './session'

vi.mock('@/api/endpoints', () => ({
  api: {
    getSession: vi.fn().mockResolvedValue(null),
    signOut: vi.fn().mockResolvedValue(undefined),
  },
}))

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <SessionProvider>{children}</SessionProvider>
    </QueryClientProvider>
  )
}

describe('signOut', () => {
  beforeEach(() => localStorage.clear())

  it('clears this browser\'s ask history', async () => {
    addHistory({ mode: 'search', kb: 'legal', question: 'q', requestId: 'r-1', verdict: 'allow', reason: null })
    expect(readHistory()).toHaveLength(1)
    const { result } = renderHook(() => useSession(), { wrapper })
    await act(async () => { await result.current.signOut() })
    expect(readHistory()).toEqual([])
  })
})
