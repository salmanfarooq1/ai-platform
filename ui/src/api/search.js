import { apiFetch } from './client'
export async function search({ query, namespace = 'legal', topK = 5, retrievalMode = 'hybrid', rerank = true }) {
  return apiFetch('/search', {
    method: 'POST',
    body: JSON.stringify({ query, namespace, top_k: topK, retrieval_mode: retrievalMode, rerank }),
  })
  // Returns: { data: SearchResponse, headers }
}
