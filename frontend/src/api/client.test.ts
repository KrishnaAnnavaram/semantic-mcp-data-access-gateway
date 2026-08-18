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
})
