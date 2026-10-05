import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/endpoints'
import type { PolicyVersion, ReasonCode } from '@/api/types'

/** What the UI shows for one reason code. */
export interface ReasonView {
  code: string
  title: string
  sentence: string
  /** The policy document key behind the deny, or null when no policy key is behind it. */
  policyField: string | null
  known: boolean
}

export const REASONS_KEY = ['reason-codes'] as const

/** The reason catalogue is public data and does not change while the app runs. It is fetched once and kept. */
export function useReasonCodes() {
  const q = useQuery({
    queryKey: REASONS_KEY,
    queryFn: api.reasonCodes,
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  })
  return { byCode: indexReasons(q.data), isLoading: q.isLoading, error: q.error }
}

export function indexReasons(list: ReasonCode[] | undefined): Record<string, ReasonCode> {
  const out: Record<string, ReasonCode> = {}
  for (const r of list ?? []) out[r.code] = r
  return out
}

/**
 * Describe a reason code with the catalogue sentence. A code the catalogue does not know still gets a plain
 * fallback, so a deny is never shown without words.
 */
export function describeReason(byCode: Record<string, ReasonCode> | undefined, code: string): ReasonView {
  const info = byCode?.[code]
  if (!info) {
    return { code, title: code, sentence: 'The gateway stopped this call. The reason code is shown below.', policyField: null, known: false }
  }
  return { code, title: info.title, sentence: info.sentence, policyField: info.policy_field, known: true }
}

/**
 * `query_blocked` is also raised by the built-in injection patterns, which every tenant has. So it only names a
 * policy key when the tenant policy really holds `blocked_terms`.
 */
export function policyFieldFor(view: ReasonView, policy: PolicyVersion | undefined): string | null {
  if (view.code !== 'query_blocked') return view.policyField
  const terms = (policy?.document as Record<string, unknown> | undefined)?.['blocked_terms']
  return Array.isArray(terms) && terms.length > 0 ? 'blocked_terms' : null
}

/** The view for one deny, with the policy-field rule for `query_blocked` applied. */
export function useDenyReason(code: string, policyVersion: number | null | undefined): ReasonView {
  const { byCode } = useReasonCodes()
  const view = describeReason(byCode, code)
  const needsPolicy = code === 'query_blocked' && policyVersion != null
  const policy = useQuery({
    queryKey: ['policy', policyVersion],
    queryFn: () => api.policy(policyVersion as number),
    enabled: needsPolicy,
    staleTime: Infinity,
    retry: false,
  })
  return { ...view, policyField: policyFieldFor(view, policy.data) }
}
