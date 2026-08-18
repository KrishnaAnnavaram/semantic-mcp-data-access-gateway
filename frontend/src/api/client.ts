// Transport layer, mirroring frontend's old agent_client.py: one error type,
// one result shape, two swappable implementations, chosen by VITE_AGENT_BACKEND.

import { getSettings } from '../config'
import { mockDemoAnswer } from './mockFixtures'
import type { ChatResponse, ChatMessage, DataPlan, Negotiation, Table, ElicitationPayload, TraceStep } from '../types/chat'

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
}

interface AgentClient {
  ask(query: string, sessionId: string): Promise<AnswerResult>
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
  }
}

class RestAgentClient implements AgentClient {
  private baseUrl: string
  private timeoutMs: number

  constructor(baseUrl: string, timeoutMs: number) {
    this.baseUrl = baseUrl
    this.timeoutMs = timeoutMs
  }

  async ask(query: string, sessionId: string): Promise<AnswerResult> {
    const started = performance.now()
    let response: Response
    try {
      response = await this.post('/chat', { query, session_id: sessionId }, this.timeoutMs)
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

export async function askAgent(query: string, sessionId: string): Promise<AnswerResult> {
  return buildClient().ask(query, sessionId)
}

export async function summariseSession(messages: ChatMessage[]): Promise<string | null> {
  try {
    return await buildClient().summarise(messages)
  } catch {
    return null
  }
}
