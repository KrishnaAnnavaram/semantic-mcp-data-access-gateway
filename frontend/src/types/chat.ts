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
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  tables?: Table[]
  data_plan?: DataPlan | null
  negotiation?: Negotiation | null
  trace?: TraceStep[]
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
