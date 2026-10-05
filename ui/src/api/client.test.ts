import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request, setCsrfToken } from './client'

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fn = vi.fn().mockResolvedValue(new Response(status === 204 ? null : JSON.stringify(body), { status, headers }))
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('api client', () => {
  beforeEach(() => setCsrfToken(null))
  afterEach(() => vi.unstubAllGlobals())

  it('sends cookies, and no CSRF header on a GET', async () => {
    const fn = mockFetch(200, { ok: true })
    setCsrfToken('tok')
    await request('/v1/decisions', { query: { outcome: 'deny', limit: 5, action: '' } })
    const [url, init] = fn.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/v1/decisions?outcome=deny&limit=5')
    expect(init.credentials).toBe('include')
    expect((init.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined()
  })

  it.each(['POST', 'PUT', 'PATCH', 'DELETE'] as const)('adds X-CSRF-Token on %s', async (method) => {
    const fn = mockFetch(200, {})
    setCsrfToken('csrf-123')
    await request('/v1/thing', { method, json: { a: 1 } })
    const [, init] = fn.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-123')
  })

  it('maps the error format into a typed ApiError', async () => {
    mockFetch(403, { error: { code: 'policy_denied', message: 'Denied by policy (reason: kb_not_allowed)', request_id: 'req-5' } })
    const err = await request('/v1/search', { method: 'POST', json: {} }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 403, code: 'policy_denied', requestId: 'req-5' })
  })

  it('falls back to the request id header and a generic code when the body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>bad gateway</html>', { status: 502, headers: { 'X-Request-ID': 'req-h' } })))
    const err = await request('/v1/health').catch((e: unknown) => e)
    expect(err).toMatchObject({ status: 502, code: 'http_error', requestId: 'req-h' })
  })

  it('reports a network failure as network_error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed to fetch')))
    const err = await request('/v1/health').catch((e: unknown) => e)
    expect(err).toMatchObject({ status: 0, code: 'network_error' })
  })

  it('returns the request id from the response header, and handles 204', async () => {
    mockFetch(204, null, { 'X-Request-ID': 'req-d' })
    const res = await request('/v1/session', { method: 'DELETE' })
    expect(res.requestId).toBe('req-d')
    expect(res.data).toBeUndefined()
  })
})
