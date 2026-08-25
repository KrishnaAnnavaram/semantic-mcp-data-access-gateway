// Mirrors backend/src/backend/api/service.py — ChatResponse and friends.
// Keep this file in lockstep with that pydantic model; it is the one contract
// the whole app is built against.

export interface ElicitationOption {
  label: string
  value: string
}

export interface ElicitationPayload {
  question: string
  options: ElicitationOption[]
}

export interface Provenance {
  dataset_snapshot_id?: string | null
  source_file?: string | null
  curve_date?: string | null
  /** A history table spans a window rather than sitting on one date, so it
   *  carries the window it actually observed instead of a curve date. */
  observed_from?: string | null
  observed_to?: string | null
  quote_basis?: string | null
  rate_kind?: string | null
  classification?: string | null
}

export type TableCell = string | number | null

export interface Table {
  columns: string[]
  rows: TableCell[][]
  row_count: number
  truncated?: boolean
  provenance?: Provenance | null
}

export type FieldVerdict = 'required' | 'not_needed' | 'unavailable'

export interface FieldNote {
  name: string
  verdict: FieldVerdict
  reason?: string | null
}

export interface Citation {
  domain: string
  source: string
  heading: string
  distance: number
}

export interface DataPlan {
  rows: number | null
  grounded: boolean
  row_quote: string | null
  row_reason?: string | null
  fields: string[]
  field_notes: FieldNote[]
  citations: Citation[]
  warnings: string[]
  answerable: boolean
  unanswerable_reason?: string | null
}

export type Speaker = 'domain_expert' | 'mcp_agent'

export interface NegotiationTurn {
  speaker: Speaker
  round: number
  message: string
}

export interface Negotiation {
  rounds_used: number
  converged: boolean
  outcome: string
  turns: NegotiationTurn[]
}

// One entry per pipeline step (agents/pipeline.py `trace.append(...)`).
// `detail` is deliberately loose — its shape depends on `kind` (a string for
// intent/answer, an array of chunk labels for knowledge, a nested object for
// decision/tool_call) and the rail only reads `kind`/`label` generically.
export type TraceKind = 'intent' | 'clarification' | 'knowledge' | 'decision' | 'tool_call' | 'answer'

export interface TraceStep {
  kind: TraceKind
  label: string
  detail?: unknown
}

// One recorded agent-to-agent call, mirroring the backend TurnLedger's handoff
// dict (agents/a2a/guardrails.py `Handoff.as_dict`). This is what drives the
// GRAPH view — a real record of who called whom, not a static picture.
export interface Handoff {
  sequence: number
  from: string
  to: string
  skill: string
  chain_length: number
  task_id: string
  context_id: string
  state: string
  duplicate: boolean
  repeatable: boolean
  negotiation_round: number
  negotiation_phase: string
  duration_ms: number
}

// The turn's handoff ledger (agents/a2a/guardrails.py `TurnLedger.as_dict`).
export interface Handoffs {
  user_request_id: string
  context_id: string
  handoffs_used: number
  handoff_limit: number
  chain_limit: number
  reentry_limit: number
  max_chain_reached: number
  negotiation_rounds: number
  duplicates_suppressed: number
  handoffs: Handoff[]
}

export interface ChatResponse {
  answer: string
  sources: string[]
  trace: TraceStep[]
  awaiting_clarification: boolean
  elicitation: ElicitationPayload | null
  route: string
  tables: Table[]
  data_plan: DataPlan | null
  negotiation: Negotiation | null
  catalogue: Record<string, unknown> | null
  calculation: Record<string, unknown> | null
  langsmith_url: string | null
  langsmith_trace_id: string | null
  langsmith_project: string | null
  handoffs: Handoffs | null
}

// What one assistant turn carries for its own trace/graph views. Every field is
// per-message: selecting an older answer shows *that* answer's trace and link,
// never one global "latest" reference.
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  tables?: Table[]
  data_plan?: DataPlan | null
  negotiation?: Negotiation | null
  trace?: TraceStep[]
  handoffs?: Handoffs | null
  langsmith_url?: string | null
  langsmith_trace_id?: string | null
  langsmith_project?: string | null
}

// The generic node the GRAPH and TRACE views render, derived from the trace
// steps and the handoff ledger. Category drives colour and icon; status drives
// the completed/running/failed/skipped styling.
export type TraceCategory =
  | 'pipeline'
  | 'agent'
  | 'llm'
  | 'a2a'
  | 'retriever'
  | 'mcp'
  | 'tool'
  | 'database'
  | 'cache'
export type TraceStatus = 'running' | 'completed' | 'failed' | 'skipped'

export interface TraceNode {
  id: string
  parentId?: string | null
  name: string
  category: TraceCategory
  status: TraceStatus
  durationMs?: number
  agent?: string
  detail?: string
  metadata?: Record<string, unknown>
}

// The LangSmith reference a message keeps, resolved from its own fields.
export interface LangSmithRef {
  url: string | null
  traceId: string | null
  project: string | null
}

export interface ChatSession {
  title: string
  messages: ChatMessage[]
  pending: ElicitationPayload | null
  startedAt: number
  titled: boolean
}

export interface OpenArtifact {
  message: number
  artifact: number
}
