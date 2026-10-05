import { renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { api } from '@/api/endpoints'
import type { PolicyVersion } from '@/api/types'
import { CATALOGUE } from '@/test/fixtures'
import { testClient } from '@/test/render'
import { describeReason, indexReasons, policyFieldFor, REASONS_KEY, useDenyReason, useReasonCodes } from './reasons'

const policy = (doc: Record<string, unknown>): PolicyVersion => ({ active: true, created_at: '2026-09-14T09:00:00Z', created_by: null, version: 3, document: doc as PolicyVersion['document'] })

describe('describeReason', () => {
  const by = indexReasons(CATALOGUE)

  it('gives the plain sentence and policy field from the catalogue', () => {
    const v = describeReason(by, 'kb_not_allowed')
    expect(v.sentence).toBe('The policy does not list this knowledge base.')
    expect(v.policyField).toBe('allowed_kbs')
    expect(v.title).toBe('Knowledge base not allowed')
    expect(v.known).toBe(true)
  })

  it('falls back to a plain sentence for a code the catalogue does not know', () => {
    const v = describeReason(by, 'brand_new_code')
    expect(v.known).toBe(false)
    expect(v.sentence).toMatch(/gateway stopped this call/)
    expect(v.policyField).toBeNull()
  })

  it('still answers before the catalogue has loaded', () => {
    expect(describeReason(undefined, 'kb_not_allowed').sentence).toMatch(/gateway stopped this call/)
  })
})

describe('policyFieldFor', () => {
  const by = indexReasons(CATALOGUE)

  it('names the policy key for ordinary reasons', () => {
    expect(policyFieldFor(describeReason(by, 'token_limit'), undefined)).toBe('max_tokens_per_request')
  })

  it('does not name blocked_terms for query_blocked unless the tenant has blocked terms', () => {
    const view = describeReason(by, 'query_blocked')
    expect(policyFieldFor(view, undefined)).toBeNull()
    expect(policyFieldFor(view, policy({ allowed_kbs: '*' }))).toBeNull()
    expect(policyFieldFor(view, policy({ blocked_terms: [] }))).toBeNull()
    expect(policyFieldFor(view, policy({ blocked_terms: ['payroll'] }))).toBe('blocked_terms')
  })
})

describe('the reason hooks', () => {
  function wrapper(client = testClient()) {
    return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  it('fetches the catalogue once and caches it', async () => {
    const spy = vi.spyOn(api, 'reasonCodes').mockResolvedValue(CATALOGUE)
    const client = testClient()
    const first = renderHook(() => useReasonCodes(), { wrapper: wrapper(client) })
    await waitFor(() => expect(first.result.current.byCode['kb_not_allowed']).toBeDefined())
    const second = renderHook(() => useReasonCodes(), { wrapper: wrapper(client) })
    expect(second.result.current.byCode['kb_not_allowed']?.title).toBe('Knowledge base not allowed')
    expect(spy).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })

  it('useDenyReason reads the policy only for query_blocked', async () => {
    const client = testClient()
    client.setQueryData(REASONS_KEY, CATALOGUE)
    const policySpy = vi.spyOn(api, 'policy').mockResolvedValue(policy({ blocked_terms: ['payroll'] }))
    const plain = renderHook(() => useDenyReason('kb_not_allowed', 3), { wrapper: wrapper(client) })
    expect(plain.result.current.policyField).toBe('allowed_kbs')
    expect(policySpy).not.toHaveBeenCalled()
    const blocked = renderHook(() => useDenyReason('query_blocked', 3), { wrapper: wrapper(client) })
    expect(blocked.result.current.policyField).toBeNull()
    await waitFor(() => expect(blocked.result.current.policyField).toBe('blocked_terms'))
    policySpy.mockRestore()
  })
})
