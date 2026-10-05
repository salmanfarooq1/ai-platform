import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from 'react'
import { api } from '@/api/endpoints'
import { ApiError, isApiError, setCsrfToken } from '@/api/client'
import type { SessionInfo } from '@/api/types'
import { clearHistory } from '@/features/history/history-store'

interface SessionState {
  session: SessionInfo | null
  isLoading: boolean
  error: unknown
  signIn: (apiKey: string) => Promise<SessionInfo>
  startPreview: () => Promise<SessionInfo>
  signOut: () => Promise<void>
  can: (scope: string) => boolean
}

const Ctx = createContext<SessionState | null>(null)
const SESSION_KEY = ['session'] as const

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: SESSION_KEY,
    retry: false,
    staleTime: 60_000,
    queryFn: async (): Promise<SessionInfo | null> => {
      try {
        return await api.getSession()
      } catch (e) {
        if (isApiError(e) && e.status === 401) return null
        throw e
      }
    },
  })
  const session = q.data ?? null

  useEffect(() => { setCsrfToken(session?.csrf_token ?? null) }, [session])

  // Another identity must never see this one's cached data. The session query itself stays so its observer keeps working.
  const dropCachedData = useCallback(() => {
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== SESSION_KEY[0] })
  }, [qc])

  const adopt = useCallback((info: SessionInfo) => {
    setCsrfToken(info.csrf_token)
    dropCachedData()
    qc.setQueryData(SESSION_KEY, info)
    return info
  }, [qc, dropCachedData])

  const value = useMemo<SessionState>(() => ({
    session,
    isLoading: q.isLoading,
    error: q.error,
    signIn: async (key) => adopt(await api.signIn(key)),
    startPreview: async () => adopt(await api.startPreview()),
    signOut: async () => {
      try {
        await api.signOut()
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 401)) throw e
      }
      setCsrfToken(null)
      clearHistory() // this browser's asks belong to the identity that signed out
      dropCachedData()
      qc.setQueryData(SESSION_KEY, null)
    },
    can: (scope) => !!session && (session.scopes.includes(scope) || session.scopes.includes('admin')),
  }), [session, q.isLoading, q.error, adopt, qc, dropCachedData])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSession(): SessionState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useSession must be used inside SessionProvider')
  return v
}
