export const STORY_STEPS = [
  { id: 'ask', title: 'Agent asks', body: 'An agent or a person sends a question with a key. The key tells the platform who is calling and which tenant they belong to.' },
  { id: 'gateway', title: 'Gateway', body: 'Every call enters one gateway and meets the same checks, in the same order.' },
  { id: 'policy', title: 'Policy', body: 'The tenant policy can only narrow access: which knowledge bases, tools and models, and how many tool calls and tokens.' },
  { id: 'verdict', title: 'Allow or deny', body: 'The answer is yes or no, with a reason. If a check cannot run, the call is denied.' },
  { id: 'receipt', title: 'Record', body: 'Every call leaves a record with its id, policy version, verdict and a hash of the input. The input text is not stored.' },
] as const

export type StepId = (typeof STORY_STEPS)[number]['id']
