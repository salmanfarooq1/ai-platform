import type { components } from './schema'

type S = components['schemas']

export type SessionInfo = S['SessionInfo']
export type DecisionSummary = S['DecisionSummary']
export type DecisionDetail = S['DecisionDetail']
export type DecisionPage = S['DecisionPage']
export type PolicyList = S['PolicyList']
export type PolicyVersion = S['PolicyVersion']
export type PrincipalSummary = S['PrincipalSummary']
export type KeySummary = S['KeySummary']
export type UsageSummary = S['UsageSummary']
export type SearchRequest = S['SearchRequest']
export type SearchResponse = S['SearchResponse']
export type SearchResult = S['SearchResult']
export type AgentRequest = S['AgentRequest']
export type AgentResponse = S['AgentResponse']
export type AgentCitation = S['AgentCitation']
export type HealthResponse = S['HealthResponse']
export type JobAccepted = S['JobAccepted']
export type Job = S['Job']
export type JobPage = S['JobPage']
export type AgentAccepted = S['AgentAccepted']
export type AgentRun = S['AgentRun']
export type AgentRunDetail = S['AgentRunDetail']
export type AgentRunPage = S['AgentRunPage']
export type RunTimelineItem = S['RunTimelineItem']
export type SandboxEvent = S['SandboxEventOut']
export type Overview = S['Overview']
export type RequestPage = S['RequestPage']
export type RequestSummary = S['RequestSummary']
export type RequestDetail = S['RequestDetail']
export type ReasonCode = S['ReasonCode']
export type FirstDeny = S['FirstDeny']
export type Receipt = S['Receipt']
export type ReceiptKey = S['ReceiptKey']
export type VerifyResult = S['VerifyResult']
export type VerifyCheck = S['VerifyCheck']
export type TrustSummary = S['TrustSummary']
export type EvalGate = S['EvalGate']

export type Outcome = 'allow' | 'deny'

/** Verdict states used across the UI. `unrecorded` has no decision row. */
export type Verdict = 'allow' | 'deny' | 'escalate' | 'unrecorded'

/** GET /v1/config has no response model in the OpenAPI document, so its shape is written here. */
export interface PlatformConfig {
  namespaces: Record<string, string>
  confidence_floor: number
  max_query_length: number
  daily_token_budget: number
  rate_limit_rpm: number
  rate_limit_window_seconds: number
  reranker_enabled: boolean
  agent_defaults: { max_iterations: number; enable_verifier: boolean; max_verify_retries: number }
}

export interface PlatformModule {
  name: string
  label: string
  pillar: 'platform' | 'gateway' | 'data' | 'agents'
  enabled: boolean
  nav_group: string | null
  always_on: boolean
}

export interface ModuleList {
  edition: string | null
  deploy_shape: 'single_tenant' | 'multi_tenant'
  modules: PlatformModule[]
}

/** One row of GET /v1/documents (no response model in the OpenAPI document). */
export interface DocumentRow {
  document_id: string
  namespace: string
  source_filename?: string | null
  chunk_count: number
  content_hash?: string | null
  last_ingested_at?: string | null
}

export interface DecisionFilters {
  outcome?: Outcome
  action?: string
  principal?: string
  policy_version?: number
  request_id?: string
  since?: string
}

export interface RequestFilters {
  outcome?: Outcome
  action?: string
  policy_version?: number
  since?: string
  include_console_reads?: boolean
}
