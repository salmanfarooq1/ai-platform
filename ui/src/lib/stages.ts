/** Plain names for the gateway stages. The stage on a decision row is the source of truth. */
const LABELS: Record<string, string> = {
  principal: 'Identity check',
  boundary: 'Scope check',
  policy: 'Tenant policy',
  guardrails: 'Input guardrails',
  rate: 'Rate limit',
  budget: 'Token budget',
  enforce: 'Gateway',
  record: 'Decision record',
  allow: 'Passed all checks',
}

export function stageLabel(stage: string): string {
  return LABELS[stage] ?? stage
}
