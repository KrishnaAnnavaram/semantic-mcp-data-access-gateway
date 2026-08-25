import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { askAgent, AgentClientError } from './client'

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )

describe('askAgent (mock backend)', () => {
  beforeEach(() => {
    import.meta.env.VITE_AGENT_BACKEND = 'mock'
  })

  it('returns a realistic curve answer with table, data plan, and positive latency', async () => {
    const result = await askAgent('what is the 10y rate', 'session-1')
    expect(result.sources.length).toBeGreaterThan(0)
    expect(result.latencyMs).toBeGreaterThan(0)
    expect(result.awaitingClarification).toBe(false)
    expect(result.tables.length).toBe(1)
    expect(result.tables[0].columns).toEqual(['tenor', 'rate_pct'])
    expect(result.dataPlan?.grounded).toBe(true)
    expect(result.negotiation?.converged).toBe(true)
  })

  it('asks a clarifying question for an ambiguous "30 year" query', async () => {
    const result = await askAgent('what is the 30 year rate', 'session-1')
    expect(result.awaitingClarification).toBe(true)
    expect(result.elicitation?.options.length).toBeGreaterThan(0)
    expect(result.tables).toEqual([])
  })
})

describe('askAgent (rest backend)', () => {
  beforeEach(() => {
    import.meta.env.VITE_AGENT_BACKEND = 'rest'
    import.meta.env.VITE_AGENT_API_URL = 'http://localhost:8000'
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('parses a 200 response into answer/sources', async () => {
    vi.mocked(fetch).mockReturnValue(
      jsonResponse({ answer: 'The 10Y par yield is 4.21%.', sources: ['market_risk/curve_construction'] }),
    )
    const result = await askAgent('what is the 10y rate', 'session-1')
    expect(result.answer).toBe('The 10Y par yield is 4.21%.')
    expect(result.sources).toEqual(['market_risk/curve_construction'])
  })

  it('raises AgentClientError on HTTP 500', async () => {
    vi.mocked(fetch).mockReturnValue(jsonResponse({ detail: 'agent error' }, 500))
    await expect(askAgent('q', 'session-1')).rejects.toBeInstanceOf(AgentClientError)
  })

  it('raises AgentClientError when the response is missing "answer"', async () => {
    vi.mocked(fetch).mockReturnValue(jsonResponse({ sources: [] }))
    await expect(askAgent('q', 'session-1')).rejects.toBeInstanceOf(AgentClientError)
  })

  // The bug this whole layer had: the payload carried langsmith_url but the
  // mapper dropped it, so the "Open trace" link never reached the UI. These
  // assertions are the regression guard for that.
  it('preserves the LangSmith url, trace id and project from the payload', async () => {
    vi.mocked(fetch).mockReturnValue(
      jsonResponse({
        answer: 'ok',
        sources: [],
        langsmith_url: 'https://smith.langchain.com/o/x/projects/p/r/abc123',
        langsmith_trace_id: 'abc123',
        langsmith_project: 'semantic-mcp-data-access-gateway',
      }),
    )
    const result = await askAgent('q', 'session-1')
    expect(result.langsmithUrl).toBe('https://smith.langchain.com/o/x/projects/p/r/abc123')
    expect(result.langsmithTraceId).toBe('abc123')
    expect(result.langsmithProject).toBe('semantic-mcp-data-access-gateway')
  })

  it('preserves the handoff ledger from the payload', async () => {
    vi.mocked(fetch).mockReturnValue(
      jsonResponse({
        answer: 'ok',
        sources: [],
        handoffs: { handoffs_used: 3, handoffs: [{ from: 'orchestrator', to: 'domain-expert' }] },
      }),
    )
    const result = await askAgent('q', 'session-1')
    expect(result.handoffs?.handoffs_used).toBe(3)
    expect(result.handoffs?.handoffs?.[0]?.to).toBe('domain-expert')
  })

  it('degrades to null LangSmith fields when the backend omits them (tracing off)', async () => {
    vi.mocked(fetch).mockReturnValue(jsonResponse({ answer: 'ok', sources: [] }))
    const result = await askAgent('q', 'session-1')
    expect(result.langsmithUrl).toBeNull()
    expect(result.langsmithTraceId).toBeNull()
    expect(result.handoffs).toBeNull()
  })
})
