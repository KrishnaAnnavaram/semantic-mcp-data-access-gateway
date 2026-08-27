// Transport layer, mirroring frontend's old agent_client.py: one error type,
// one result shape, two swappable implementations, chosen by VITE_AGENT_BACKEND.

import { getSettings } from '../config'
import { mockDemoAnswer } from './mockFixtures'
import type { ChatResponse, ChatMessage, DataPlan, Handoffs, Negotiation, Table, ElicitationPayload, TraceStep } from '../types/chat'
import type { LatencyReport, StructuredAnswer } from '../types/execution'

export class AgentClientError extends Error {}

export interface AnswerResult {
  answer: string
  sources: string[]
  latencyMs: number
  elicitation: ElicitationPayload | null
  route: string
  tables: Table[]
  dataPlan: DataPlan | null
  negotiation: Negotiation | null
  awaitingClarification: boolean
  trace: TraceStep[]
  // Observability — carried from the /chat payload so each assistant message
  // keeps its OWN LangSmith reference and handoff ledger. The previous mapper
  // silently dropped langsmith_url here, which is why the "Open trace" link
  // never reached the UI however correctly the backend produced it.
  handoffs: Handoffs | null
  langsmithUrl: string | null
  langsmithTraceId: string | null
  langsmithProject: string | null
  // The turn's correlation id — the same one the client chose before asking and
  // watched the live stream under, echoed back so a stored message can find its
  // own events, trace, waterfall and graph later.
  requestId: string | null
  structured: StructuredAnswer | null
  latency: LatencyReport | null
}

interface AgentClient {
  ask(query: string, sessionId: string, requestId?: string): Promise<AnswerResult>
  summarise(messages: ChatMessage[]): Promise<string | null>
}

function toResult(payload: ChatResponse, latencyMs: number): AnswerResult {
  return {
    answer: payload.answer,
    sources: payload.sources ?? [],
    latencyMs,
    elicitation: payload.elicitation ?? null,
    route: payload.route ?? 'quant',
    tables: payload.tables ?? [],
    dataPlan: payload.data_plan ?? null,
    negotiation: payload.negotiation ?? null,
    awaitingClarification: payload.elicitation != null,
    trace: payload.trace ?? [],
    handoffs: payload.handoffs ?? null,
    langsmithUrl: payload.langsmith_url ?? null,
    langsmithTraceId: payload.langsmith_trace_id ?? null,
    langsmithProject: payload.langsmith_project ?? null,
    requestId: payload.request_id ?? null,
    structured: payload.structured ?? null,
    latency: payload.latency ?? null,
  }
}

class RestAgentClient implements AgentClient {
  private baseUrl: string
  private timeoutMs: number

  constructor(baseUrl: string, timeoutMs: number) {
    this.baseUrl = baseUrl
    this.timeoutMs = timeoutMs
  }

  async ask(query: string, sessionId: string, requestId?: string): Promise<AnswerResult> {
    const started = performance.now()
    let response: Response
    try {
      // `request_id` is chosen by the caller and sent with the question, so the
      // live stream it already subscribed to and this answer carry the same id.
      response = await this.post(
        '/chat',
        { query, session_id: sessionId, request_id: requestId },
        this.timeoutMs,
      )
    } catch (err) {
      throw new AgentClientError(`Could not reach the agent service: ${(err as Error).message}`)
    }
    if (!response.ok) {
      throw new AgentClientError(`Agent service returned ${response.status} ${response.statusText}`)
    }
    const payload = (await response.json()) as Partial<ChatResponse>
    if (typeof payload.answer !== 'string') {
      throw new AgentClientError('Agent service response is missing "answer".')
    }
    return toResult(payload as ChatResponse, performance.now() - started)
  }

  async summarise(messages: ChatMessage[]): Promise<string | null> {
    try {
      const response = await this.post('/summarise', { messages }, Math.min(this.timeoutMs, 30_000))
      if (!response.ok) return null
      const payload = (await response.json()) as { title?: string }
      return payload.title ?? null
    } catch {
      // A title is cosmetic — never let it surface as a user-facing error.
      return null
    }
  }

  private async post(path: string, body: unknown, timeoutMs: number): Promise<Response> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      return await fetch(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } finally {
      clearTimeout(timer)
    }
  }
}

// Returns a realistic canned exchange (curve table, grounded data plan,
// domain-expert/mcp-agent discussion) shaped exactly like a live /chat
// response, so the full artifact panel can be demoed with no backend running.
// A question mentioning "30 year" triggers the elicitation flow instead,
// since that ambiguity (BC_30YEAR vs BC_30YEARDISPLAY) is the real system's
// own example of when it asks rather than guesses.
class MockAgentClient implements AgentClient {
  async ask(query: string): Promise<AnswerResult> {
    const started = performance.now()
    await new Promise((resolve) => setTimeout(resolve, 400))
    return mockDemoAnswer(query, performance.now() - started)
  }

  async summarise(): Promise<string | null> {
    return null
  }
}

function buildClient(): AgentClient {
  const settings = getSettings()
  if (settings.agentBackend === 'rest') return new RestAgentClient(settings.agentApiUrl, settings.agentTimeoutMs)
  if (settings.agentBackend === 'mock') return new MockAgentClient()
  throw new AgentClientError(
    `Unknown VITE_AGENT_BACKEND '${settings.agentBackend}'; expected 'mock' or 'rest'.`,
  )
}

export function isMockMode(): boolean {
  return getSettings().agentBackend !== 'rest'
}

export async function askAgent(
  query: string,
  sessionId: string,
  requestId?: string,
): Promise<AnswerResult> {
  return buildClient().ask(query, sessionId, requestId)
}

export async function summariseSession(messages: ChatMessage[]): Promise<string | null> {
  try {
    return await buildClient().summarise(messages)
  } catch {
    return null
  }
}
