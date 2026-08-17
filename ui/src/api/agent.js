import { apiFetch } from './client'
export async function agentQuery({ question, namespace = 'default', maxIterations = 6, enableVerifier = true, maxVerifyRetries = 1 }) {
  return apiFetch('/agent/query', {
    method: 'POST',
    body: JSON.stringify({
      question,
      namespace,
      max_iterations: maxIterations,
      enable_verifier: enableVerifier,
      max_verify_retries: maxVerifyRetries,
    }),
  })
  // Returns: { data: AgentResponse, headers }
}
