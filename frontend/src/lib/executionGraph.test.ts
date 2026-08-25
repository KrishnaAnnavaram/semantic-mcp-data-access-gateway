import { describe, expect, it } from 'vitest'
import { buildExecutionGraph } from './executionGraph'
import type { Handoff, Handoffs, TraceStep } from '../types/chat'

function handoff(over: Partial<Handoff>): Handoff {
  return {
    sequence: 1,
    from: 'orchestrator',
    to: 'domain-expert',
    skill: 'derive_data_requirement',
    chain_length: 2,
    task_id: 't',
    context_id: 'c',
    state: 'completed',
    duplicate: false,
    repeatable: false,
    negotiation_round: 0,
    negotiation_phase: '',
    duration_ms: 1000,
    ...over,
  }
}

function ledger(handoffs: Handoff[]): Handoffs {
  return {
    user_request_id: 'u',
    context_id: 'c',
    handoffs_used: handoffs.length,
    handoff_limit: 20,
    chain_limit: 8,
    reentry_limit: 3,
    max_chain_reached: Math.max(0, ...handoffs.map((h) => h.chain_length)),
    negotiation_rounds: 0,
    duplicates_suppressed: 0,
    handoffs,
  }
}

const nodeIds = (g: ReturnType<typeof buildExecutionGraph>) => g.nodes.map((n) => n.id)

describe('buildExecutionGraph', () => {
  it('draws only user + orchestrator for a direct turn (no handoffs, no trace)', () => {
    const g = buildExecutionGraph(null, undefined)
    expect(nodeIds(g)).toEqual(['user', 'orchestrator'])
    expect(g.edges).toHaveLength(1)
  })

  it('adds the domain expert when it was actually called', () => {
    const g = buildExecutionGraph(ledger([handoff({ to: 'domain-expert' })]), [])
    expect(nodeIds(g)).toContain('domain-expert')
    expect(g.edges.some((e) => e.source === 'orchestrator' && e.target === 'domain-expert')).toBe(true)
  })

  it('adds Qdrant only when a knowledge step is present', () => {
    const withKnowledge: TraceStep[] = [{ kind: 'knowledge', label: 'Domain expert cited 3 chunks' }]
    const g = buildExecutionGraph(ledger([handoff({ to: 'domain-expert' })]), withKnowledge)
    expect(nodeIds(g)).toContain('qdrant')

    const g2 = buildExecutionGraph(ledger([handoff({ to: 'domain-expert' })]), [])
    expect(nodeIds(g2)).not.toContain('qdrant')
  })

  it('draws the full road to PostgreSQL for a fetch turn', () => {
    const handoffs = ledger([
      handoff({ to: 'domain-expert' }),
      handoff({ from: 'domain-expert', to: 'mcp-agent', skill: 'assess_data_requirement', chain_length: 3 }),
      handoff({ from: 'orchestrator', to: 'mcp-agent', skill: 'execute_data_plan', duration_ms: 900 }),
    ])
    const trace: TraceStep[] = [
      { kind: 'knowledge', label: 'cited 2 chunks' },
      { kind: 'tool_call', label: 'Fetched 250 row(s)' },
    ]
    const g = buildExecutionGraph(handoffs, trace)
    expect(nodeIds(g)).toEqual(
      expect.arrayContaining(['user', 'orchestrator', 'domain-expert', 'qdrant', 'mcp-agent', 'mcp-server', 'postgres']),
    )
  })

  it('marks an agent failed when its last call failed', () => {
    const g = buildExecutionGraph(ledger([handoff({ to: 'mcp-agent', state: 'failed' })]), [])
    const mcp = g.nodes.find((n) => n.id === 'mcp-agent')
    expect(mcp?.status).toBe('failed')
  })

  it('sums durations across an agent’s calls', () => {
    const g = buildExecutionGraph(
      ledger([
        handoff({ to: 'mcp-agent', duration_ms: 300 }),
        handoff({ to: 'mcp-agent', duration_ms: 700, skill: 'execute_data_plan' }),
      ]),
      [],
    )
    expect(g.nodes.find((n) => n.id === 'mcp-agent')?.durationMs).toBe(1000)
  })

  it('handles partial/undefined data without throwing', () => {
    expect(() => buildExecutionGraph(undefined, undefined)).not.toThrow()
    expect(() => buildExecutionGraph(ledger([]), [])).not.toThrow()
  })
})
