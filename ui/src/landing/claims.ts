/**
 * Every claim on the landing page and How it works, with the item of the "may claim" list it rests on.
 * The list is in docs/design/CONTENT_STYLE.md. `npm run copy-check` prints this map and checks the copy.
 */
export interface Claim {
  title: string
  body: string
  /** Number of the item in the may-claim list (CONTENT_STYLE.md). */
  claim: number
}

export const CAPABILITIES: Claim[] = [
  { claim: 1, title: 'One gateway for every call', body: 'Models, tools and knowledge bases are reached only through the gateway. Agent code does not import the model client, and a test checks it.' },
  { claim: 2, title: 'Policies that only narrow', body: 'A tenant policy limits knowledge bases, tools, models, tool calls and tokens. It is versioned, and every request is checked against the active version.' },
  { claim: 3, title: 'A record for every call', body: 'Each call, allowed or denied, leaves a record with the reason, the policy version and a hash of the input. The input text is not stored.' },
  { claim: 4, title: 'Tenants kept apart by the database', body: 'Postgres row-level security separates tenants, so one tenant cannot read another.' },
  { claim: 5, title: 'Closed when in doubt', body: 'If a check cannot run, or the record cannot be written, the call is denied.' },
  { claim: 6, title: 'Rate limits and budgets', body: 'Each tenant has rate limits and a daily token budget.' },
  { claim: 7, title: 'Read-only previews', body: 'A preview session cannot write. Its key stays on the server, in a secure cookie session.' },
  { claim: 8, title: 'Works with agent clients over MCP', body: 'Agent clients that speak MCP use the same gateway and meet the same checks.' },
]

export const USE_CASES: Array<{ title: string; body: string; claim: number }> = [
  { claim: 2, title: 'An internal knowledge assistant over company documents', body: 'People ask questions. The policy lists which knowledge bases can be read.' },
  { claim: 2, title: 'An agent with tool access', body: 'The agent can call only the tools the policy lists, up to the limit the policy sets.' },
  { claim: 3, title: 'A team that must see what its agents did', body: 'Open any request and see each check, the verdict and the policy version that applied.' },
]

export const WHY_OUTSIDE = {
  title: 'Why the gateway sits outside the agent',
  body: 'Checks inside agent code can be skipped or changed by that code. A gateway sits outside it, so every call is checked.',
  claim: 1,
}

export const HEADLINE = 'Your agents can only ever do less.'
export const SUBLINE = 'Control what your agents can do. See everything they did.'
