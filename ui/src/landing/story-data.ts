export const STORY_STEPS = [
  {
    id: 'ask',
    title: 'Agent asks',
    body: 'An agent or a person sends a question with a key. The platform resolves the key to a principal and a tenant. The tenant never comes from a header or a body.',
  },
  {
    id: 'gateway',
    title: 'Gateway',
    body: 'The call enters one function. It checks the principal, the execution boundary, the tenant policy, the input guardrails, the rate limit and the token budget, in that order.',
  },
  {
    id: 'policy',
    title: 'Policy',
    body: 'The tenant policy narrows what is allowed: which knowledge bases, tools and models, and how many tool calls and tokens. With no policy, scopes grant against the platform defaults.',
  },
  {
    id: 'verdict',
    title: 'Allow or deny',
    body: 'The answer is yes or no, with a reason code. An error in any check is a deny. When a check cannot run, nothing is allowed.',
  },
  {
    id: 'receipt',
    title: 'Receipt',
    body: 'Every call writes a decision row with its id, policy version, action, resource and the SHA-256 of the input. The text of the input is not stored.',
  },
] as const

export type StepId = (typeof STORY_STEPS)[number]['id']
