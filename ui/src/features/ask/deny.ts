import { isApiError } from '@/api/client'

/** The gateway puts the reason code in the message: "Denied by policy (reason: kb_not_allowed)". */
export function denyReason(message: string): string {
  return /reason:\s*([a-z0-9_.-]+)/i.exec(message)?.[1] ?? 'policy_denied'
}

/** Gateway denies that keep their own HTTP status. Their error code is the reason code itself. */
const OWN_CODE_DENIES = new Set(['query_blocked', 'rate_limit_exceeded', 'daily_token_budget_exceeded', 'dependency_unavailable', 'decision_unrecorded', 'module_disabled'])

/** The reason and message when an API error is a gateway deny, or null for any other error. */
export function denyFromError(e: unknown): { reason: string; message: string; requestId: string | null } | null {
  if (!isApiError(e)) return null
  if (e.status === 403 && e.code === 'policy_denied') return { reason: denyReason(e.message), message: e.message, requestId: e.requestId }
  if (OWN_CODE_DENIES.has(e.code)) return { reason: e.code, message: e.message, requestId: e.requestId }
  return null
}
