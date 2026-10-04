const BASE = import.meta.env.VITE_API_URL ?? '/api'

// Every product route lives under /v1. Only / and /health are unversioned.
export const API_PREFIX = '/v1'

// NOTE: BASE is NOT exported. Modules that can't use this wrapper
// (e.g., ingest.js which uses multipart) use import.meta.env directly
// and import API_PREFIX for the version prefix.
export async function apiFetch(path, options = {}) {
  const response = await fetch(`${BASE}${API_PREFIX}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const headers = extractHeaders(response.headers)
  if (!response.ok) {
    let errorBody
    try { errorBody = await response.json() }
    catch { errorBody = { error: { code: 'http_error', message: `HTTP ${response.status}` } } }
    // Every API error has the shape { error: { code, message, request_id } }.
    const error = new Error(errorBody.error?.message || 'Request failed')
    error.code = errorBody.error?.code
    error.requestId = errorBody.error?.request_id
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
    traceId:         h.get('X-Trace-ID'),
    processTime:     h.get('X-Process-Time'),
    cache:           h.get('X-Cache'),
    cacheType:       h.get('X-Cache-Type'),
    budgetRemaining: h.get('X-Budget-Remaining'),
    budgetLimit:     h.get('X-Budget-Limit'),
    rateLimitLimit:  h.get('X-RateLimit-Limit'),
    rateLimitRemain: h.get('X-RateLimit-Remaining'),
  }
}
