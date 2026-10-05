import { get, request, type ApiResult } from './client'
import type {
  AgentRequest, AgentResponse, DecisionDetail, DecisionFilters, DecisionPage, DocumentRow, HealthResponse, IngestResponse,
  PlatformConfig, PolicyList, ReasonCode, RequestDetail, RequestFilters, RequestPage, Overview, PolicyVersion, PrincipalSummary, SearchRequest, SearchResponse, SessionInfo, UsageSummary,
} from './types'

export const api = {
  // Web edge
  getSession: () => get<SessionInfo>('/v1/session'),
  signIn: async (apiKey: string) => (await request<SessionInfo>('/v1/session', { method: 'POST', json: { api_key: apiKey } })).data,
  startPreview: async () => (await request<SessionInfo>('/v1/session/preview', { method: 'POST' })).data,
  signOut: async () => { await request<void>('/v1/session', { method: 'DELETE' }) },
  health: () => get<HealthResponse>('/v1/health'),
  config: () => get<PlatformConfig>('/v1/config'),

  // Console reads
  decisions: (filters: DecisionFilters, cursor?: string, limit = 50) =>
    get<DecisionPage>('/v1/decisions', { ...filters, cursor, limit }),
  decision: (id: string) => get<DecisionDetail>(`/v1/decisions/${encodeURIComponent(id)}`),
  policies: () => get<PolicyList>('/v1/policies'),
  policy: (version: number) => get<PolicyVersion>(`/v1/policies/${version}`),
  principals: () => get<PrincipalSummary[]>('/v1/principals'),
  overview: (days = 7) => get<Overview>('/v1/overview', { days }),
  requests: (filters: RequestFilters, cursor?: string, limit = 50) =>
    get<RequestPage>('/v1/requests', { ...filters, cursor, limit }),
  requestDetail: (id: string) => get<RequestDetail>(`/v1/requests/${encodeURIComponent(id)}`),
  reasonCodes: () => get<ReasonCode[]>('/v1/reason-codes'),
  usage: (days = 7) => get<UsageSummary>('/v1/usage/summary', { days }),

  // Workspace
  feedback: async (body: { request_id: string; endpoint: string; rating: 'up' | 'down' }) => {
    await request<{ status: string }>('/v1/feedback', { method: 'POST', json: body })
  },
  search: (body: Partial<SearchRequest> & Pick<SearchRequest, 'query'>): Promise<ApiResult<SearchResponse>> =>
    request<SearchResponse>('/v1/search', { method: 'POST', json: body }),
  agent: (body: Partial<AgentRequest> & Pick<AgentRequest, 'question'>): Promise<ApiResult<AgentResponse>> =>
    request<AgentResponse>('/v1/agent/query', { method: 'POST', json: body }),
  documents: async (namespace: string) =>
    (await get<{ documents: DocumentRow[]; count: number }>('/v1/documents', { namespace })).documents,
  ingest: async (file: File, namespace: string) => {
    const form = new FormData()
    form.append('file', file)
    return (await request<IngestResponse>('/v1/ingest', { method: 'POST', query: { namespace }, form })).data
  },
}
