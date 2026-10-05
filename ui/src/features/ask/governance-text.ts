import type { RequestDetail } from '@/api/types'

/** "Checked by policy v3 · 2 checks · allowed". A request with no tenant policy says so. */
export function governanceLineText(r: Pick<RequestDetail, 'policy_version' | 'decisions' | 'outcome'>): string {
  const checks = r.decisions.length
  const policy = r.policy_version === null ? 'the platform default policy' : `policy v${r.policy_version}`
  return `Checked by ${policy} · ${checks} ${checks === 1 ? 'check' : 'checks'} · ${r.outcome === 'deny' ? 'denied' : 'allowed'}`
}

