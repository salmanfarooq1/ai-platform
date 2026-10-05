/** Typed fetch client (blueprint section 4). Sends cookies, adds X-CSRF-Token on unsafe methods, maps errors. */

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError
}

let csrfToken: string | null = null

/** The session provider sets this after sign-in and clears it on sign-out. */
export function setCsrfToken(token: string | null): void {
  csrfToken = token
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

type Query = Record<string, string | number | boolean | undefined | null>

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  query?: Query
  json?: unknown
  form?: FormData
  signal?: AbortSignal
}

export interface ApiResult<T> {
  data: T
  requestId: string | null
  headers: Headers
}

function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

async function toApiError(res: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = `HTTP ${res.status}`
  let requestId: string | null = res.headers.get('X-Request-ID')
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string; request_id?: string } }
    if (body.error) {
      code = body.error.code ?? code
      message = body.error.message ?? message
      requestId = body.error.request_id ?? requestId
    }
  } catch {
    // Not JSON (for example a proxy error page). Keep the HTTP defaults.
  }
  return new ApiError(res.status, code, message, requestId)
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<ApiResult<T>> {
  const method = opts.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.json)
  } else if (opts.form) {
    body = opts.form // the browser sets the multipart boundary
  }
  if (!SAFE_METHODS.has(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken

  let res: Response
  try {
    res = await fetch(withQuery(path, opts.query), { method, headers, body, credentials: 'include', signal: opts.signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'network_error', 'The API could not be reached.', null)
  }
  if (!res.ok) throw await toApiError(res)
  const requestId = res.headers.get('X-Request-ID')
  if (res.status === 204) return { data: undefined as T, requestId, headers: res.headers }
  return { data: (await res.json()) as T, requestId, headers: res.headers }
}

export async function get<T>(path: string, query?: Query, signal?: AbortSignal): Promise<T> {
  return (await request<T>(path, { query, signal })).data
}
