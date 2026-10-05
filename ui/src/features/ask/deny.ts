/** The gateway puts the reason code in the message: "Denied by policy (reason: kb_not_allowed)". */
export function denyReason(message: string): string {
  return /reason:\s*([a-z0-9_.-]+)/i.exec(message)?.[1] ?? 'policy_denied'
}
