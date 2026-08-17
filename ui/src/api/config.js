import { apiFetch } from './client'
export async function getConfig() {
  const { data } = await apiFetch('/config', { method: 'GET' })
  return data
  // {
  //   namespaces: { "legal": "description...", "kyc_aml": "...", "default": "..." },
  //   confidence_floor: 0.45,
  //   max_query_length: 1000,
  //   daily_token_budget: 500000,
  //   rate_limit_rpm: 60,
  //   rate_limit_window_seconds: 60,
  //   reranker_enabled: true,
  //   agent_defaults: { max_iterations: 6, enable_verifier: true, max_verify_retries: 1 }
  // }
}
