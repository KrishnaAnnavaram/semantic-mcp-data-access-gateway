// Mirrors agents/events.py — the one normalised execution event, and the two
// derived views the backend also serves (/trace/{id} and its latency report).
// Keep this file in lockstep with that module; it is the contract the live
// execution view, the timeline, the waterfall and the dynamic graph all read.

export type ExecutionStatus = 'running' | 'completed' | 'failed' | 'skipped' | 'info'

export type ExecutionEventType =
  | 'REQUEST_RECEIVED'
  | 'ORCHESTRATOR_STARTED'
  | 'ORCHESTRATOR_DECISION'
  | 'DOMAIN_VALIDATION_STARTED'
  | 'DOMAIN_VALIDATION_COMPLETED'
  | 'CLARIFICATION_REQUIRED'
  | 'RETRIEVAL_STARTED'
  | 'RETRIEVAL_COMPLETED'
  | 'AGENT_HANDOFF'
  | 'AGENT_HANDOFF_COMPLETED'
  | 'NEGOTIATION_ROUND'
  | 'MCP_AGENT_STARTED'
  | 'MCP_TOOL_STARTED'
  | 'MCP_TOOL_COMPLETED'
  | 'MCP_TOOL_FAILED'
  | 'DB_QUERY_STARTED'
  | 'DB_QUERY_COMPLETED'
  | 'MODEL_CALL_STARTED'
  | 'MODEL_CALL_COMPLETED'
  | 'MODEL_CALL_FAILED'
  | 'RESPONSE_SYNTHESIS_STARTED'
  | 'RESPONSE_SYNTHESIS_COMPLETED'
  | 'REQUEST_COMPLETED'
  | 'REQUEST_FAILED'

export interface ExecutionEvent {
  request_id: string
  sequence: number
  event_type: ExecutionEventType | string
  agent: string
  title: string
  summary: string
  status: ExecutionStatus
  /** Unix seconds, for the wall-clock stamp beside each line. */
  timestamp: number
  /** Milliseconds since the turn started — what the timeline is built from. */
  elapsed_ms: number
  /** Only on completion events, and only where it was really measured. */
  duration_ms: number | null
  span_id: string
  parent_span_id: string
  trace_id: string
  tool_name: string
  metadata: Record<string, unknown>
}

export interface LatencyComponent {
  component: string
  calls: number
  total_ms: number
  avg_ms: number
  max_ms: number
  /** Null for nested components, where a percentage would double-count. */
  pct: number | null
  nested: boolean
}

export interface LatencyReport {
  request_id: string
  total_ms: number
  components: LatencyComponent[]
  attributed_ms: number
  unattributed_ms: number
  events: number
}

/** GET /trace/{request_id} — the gateway's own trace, always available. */
export interface RequestTrace {
  request_id: string
  available: boolean
  finished: boolean
  events: ExecutionEvent[]
  latency: LatencyReport
}

/** GET /langsmith/trace/{trace_id} — sanitized server-side; never has prompts. */
export interface LangSmithRun {
  id: string
  parent_id: string
  trace_id: string
  name: string
  run_type: string
  start_time: string
  end_time: string
  latency_ms: number | null
  status: string
  error: boolean
  model: string
  input_tokens?: number
  output_tokens?: number
  total_tokens?: number
}

export interface LangSmithTrace {
  available: boolean
  reason?: string
  trace_id?: string
  project?: string
  runs: LangSmithRun[]
  run_count?: number
  truncated?: boolean
  started_at?: string
  ended_at?: string
}

// --- the structured answer (agents/answer_builder.py) ------------------------

export type SectionKind = 'text' | 'list' | 'keyvalue' | 'metrics' | 'table' | 'chart'

export interface AnswerMetric {
  label: string
  value: string
  unit?: string
  numeric?: number
}

export interface AnswerSection {
  id: string
  title: string
  kind: SectionKind
  body?: string
  items?: (string | { label: string; value: string })[]
  metrics?: AnswerMetric[]
  table_index?: number
  chart?: { table_index: number }
}

export interface StructuredAnswer {
  shape: 'direct' | 'clarification' | 'refusal' | 'lookup' | 'analysis' | 'stress'
  headline: string
  sections: AnswerSection[]
  lineage: {
    request_id: string
    trace_id: string
    langsmith_url: string
    calculation: string
    validation: string
  }
}
