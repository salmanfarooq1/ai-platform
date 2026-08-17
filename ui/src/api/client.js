const BASE = import.meta.env.VITE_API_URL ?? '/api'

// NOTE: BASE is NOT exported. Modules that can't use this wrapper
// (e.g., ingest.js which uses multipart) use import.meta.env directly.
export async function apiFetch(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const headers = extractHeaders(response.headers)
  if (!response.ok) {
    let errorBody
    try { errorBody = await response.json() }
    catch { errorBody = { detail: `HTTP ${response.status}` } }
    const error = new Error(
      errorBody.detail?.reason || errorBody.detail || errorBody.error || 'Request failed'
    )
    error.status = response.status
    error.body = errorBody
    error.headers = headers
    throw error
  }
  return { data: await response.json(), headers }
}

function extractHeaders(h) {
  return {
    costUsd:         h.get('X-Cost-USD'),
    tokensIn:        h.get('X-Tokens-In'),
    tokensOut:       h.get('X-Tokens-Out'),
    queryId:         h.get('X-Query-ID'),
    requestId:       h.get('X-Request-ID'),
    processTime:     h.get('X-Process-Time'),
    cache:           h.get('X-Cache'),
    cacheType:       h.get('X-Cache-Type'),
    budgetRemaining: h.get('X-Budget-Remaining'),
    budgetLimit:     h.get('X-Budget-Limit'),
    rateLimitLimit:  h.get('X-RateLimit-Limit'),
    rateLimitRemain: h.get('X-RateLimit-Remaining'),
  }
}
