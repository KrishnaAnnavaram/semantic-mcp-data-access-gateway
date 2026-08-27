import { describe, expect, it } from 'vitest'
import { buildEventGraph, toActivity, toWaterfall, elapsedOf } from './executionEvents'
import { layerOf, layoutGraph } from './graphLayout'
import type { ExecutionEvent } from '../types/execution'

// The derivations behind the Execution, Latency and Graph views. Pure, so they
// are tested without mounting React — and the property that matters most is
// negative: a graph must not draw a step that did not happen.

let sequence = 0
function event(partial: Partial<ExecutionEvent> & { event_type: string }): ExecutionEvent {
  sequence += 1
  return {
    request_id: 'r1',
    sequence,
    agent: 'system',
    title: partial.event_type,
    summary: '',
    status: 'completed',
    timestamp: 1_700_000_000 + sequence,
    elapsed_ms: sequence * 100,
    duration_ms: null,
    span_id: '',
    parent_span_id: '',
    trace_id: '',
    tool_name: '',
    metadata: {},
    ...partial,
  }
}

function reset() {
  sequence = 0
}

/** The events a fully executed risk turn publishes, in order. */
function fullTurn(): ExecutionEvent[] {
  reset()
  return [
    event({ event_type: 'REQUEST_RECEIVED', title: 'Request received' }),
    event({ event_type: 'ORCHESTRATOR_STARTED', agent: 'orchestrator', status: 'running' }),
    event({
      event_type: 'ORCHESTRATOR_DECISION',
      agent: 'orchestrator',
      metadata: { route: 'data_request' },
    }),
    event({
      event_type: 'AGENT_HANDOFF',
      agent: 'domain-expert',
      status: 'running',
      metadata: { caller: 'orchestrator', skill: 'derive_data_requirement' },
    }),
    event({
      event_type: 'RETRIEVAL_COMPLETED',
      agent: 'domain-expert',
      duration_ms: 740,
      metadata: { collection: 'quant_knowledge' },
    }),
    event({ event_type: 'AGENT_HANDOFF_COMPLETED', agent: 'domain-expert', duration_ms: 61000 }),
    event({
      event_type: 'AGENT_HANDOFF',
      agent: 'mcp-agent',
      status: 'running',
      metadata: { caller: 'orchestrator', skill: 'execute_data_plan' },
    }),
    event({
      event_type: 'MCP_TOOL_COMPLETED',
      agent: 'mcp-agent',
      tool_name: 'get_yield_curve',
      duration_ms: 440,
      metadata: { server: 'market-risk-data-mcp' },
    }),
    event({
      event_type: 'MCP_TOOL_COMPLETED',
      agent: 'mcp-agent',
      tool_name: 'get_rate_history',
      duration_ms: 210,
      metadata: { server: 'market-risk-data-mcp' },
    }),
    event({ event_type: 'AGENT_HANDOFF_COMPLETED', agent: 'mcp-agent', duration_ms: 2100 }),
    event({ event_type: 'REQUEST_COMPLETED', title: 'Completed' }),
  ]
}

/** The events a turn stopped at the requirement gate publishes. */
function gatedTurn(): ExecutionEvent[] {
  reset()
  return [
    event({ event_type: 'REQUEST_RECEIVED', title: 'Request received' }),
    event({ event_type: 'ORCHESTRATOR_STARTED', agent: 'orchestrator' }),
    event({
      event_type: 'ORCHESTRATOR_DECISION',
      agent: 'orchestrator',
      metadata: { route: 'data_request' },
    }),
    event({
      event_type: 'AGENT_HANDOFF',
      agent: 'domain-expert',
      status: 'running',
      metadata: { caller: 'orchestrator', skill: 'check_requirement_completeness' },
    }),
    event({
      event_type: 'DOMAIN_VALIDATION_COMPLETED',
      agent: 'domain-expert',
      duration_ms: 2,
      metadata: { intent: 'curve_comparison', complete: false },
    }),
    event({
      event_type: 'CLARIFICATION_REQUIRED',
      agent: 'domain-expert',
      status: 'failed',
      summary: 'comparison_period',
    }),
    event({ event_type: 'AGENT_HANDOFF_COMPLETED', agent: 'domain-expert', duration_ms: 4 }),
  ]
}

describe('toActivity', () => {
  it('keeps a started-but-unfinished step visible as running', () => {
    reset()
    const lines = toActivity([
      event({ event_type: 'MODEL_CALL_STARTED', agent: 'domain_expert', status: 'running' }),
    ])
    expect(lines).toHaveLength(1)
    expect(lines[0].status).toBe('running')
    expect(lines[0].durationMs).toBeNull()
  })

  it('upgrades the start line in place when its completion arrives', () => {
    reset()
    const lines = toActivity([
      event({ event_type: 'MODEL_CALL_STARTED', agent: 'domain_expert', status: 'running' }),
      event({ event_type: 'MODEL_CALL_COMPLETED', agent: 'domain_expert', duration_ms: 61000 }),
    ])
    // One line, not two: pairing them here is what stops the feed reading as a
    // wall of "started… completed…" the reader has to match up by eye.
    expect(lines).toHaveLength(1)
    expect(lines[0].status).toBe('completed')
    expect(lines[0].durationMs).toBe(61000)
  })

  it('pairs repeated calls from one agent in arrival order', () => {
    reset()
    const lines = toActivity([
      event({ event_type: 'MODEL_CALL_STARTED', agent: 'domain_expert', status: 'running' }),
      event({ event_type: 'MODEL_CALL_STARTED', agent: 'domain_expert', status: 'running' }),
      event({ event_type: 'MODEL_CALL_COMPLETED', agent: 'domain_expert', duration_ms: 10 }),
    ])
    // A negotiation issues several model calls from the same agent. The first
    // completion closes the first start; the second is still running.
    expect(lines).toHaveLength(2)
    expect(lines[0].durationMs).toBe(10)
    expect(lines[1].status).toBe('running')
  })

  it('marks a failed tool call as failed rather than leaving it running', () => {
    reset()
    const lines = toActivity([
      event({ event_type: 'MCP_TOOL_STARTED', agent: 'mcp-agent', tool_name: 'get_curve', status: 'running' }),
      event({
        event_type: 'MCP_TOOL_FAILED',
        agent: 'mcp-agent',
        tool_name: 'get_curve',
        status: 'failed',
        summary: 'TimeoutError',
        duration_ms: 30000,
      }),
    ])
    expect(lines).toHaveLength(1)
    expect(lines[0].status).toBe('failed')
    expect(lines[0].summary).toBe('TimeoutError')
  })
})

describe('toWaterfall', () => {
  it('places each measured span at its real start', () => {
    const rows = toWaterfall(fullTurn())
    const curve = rows.find((r) => r.label === 'get_yield_curve')!
    // start = elapsed at completion − duration, both from one server clock.
    expect(curve.startMs).toBe(800 - 440)
    expect(curve.durationMs).toBe(440)
  })

  it('excludes nested A2A spans by default', () => {
    // A handoff contains the model calls, retrievals and tool calls beneath it.
    // Drawing it beside its own children shows the same seconds twice.
    expect(toWaterfall(fullTurn()).some((r) => r.category === 'a2a')).toBe(false)
    expect(toWaterfall(fullTurn(), true).some((r) => r.category === 'a2a')).toBe(true)
  })

  it('draws nothing for a span with no measured duration', () => {
    reset()
    const rows = toWaterfall([event({ event_type: 'MODEL_CALL_STARTED', agent: 'orchestrator' })])
    expect(rows).toEqual([])
  })
})

describe('buildEventGraph', () => {
  it('draws every MCP tool as its own node with its own duration', () => {
    const graph = buildEventGraph(fullTurn())
    const ids = graph.nodes.map((n) => n.id)
    expect(ids).toContain('tool:get_yield_curve')
    expect(ids).toContain('tool:get_rate_history')
    expect(graph.nodes.find((n) => n.id === 'tool:get_yield_curve')!.durationMs).toBe(440)
  })

  it('draws NO data-layer nodes for a request stopped at the gate', () => {
    // The property the whole graph rework exists for: a picture that showed MCP
    // and PostgreSQL on a turn that never reached them would be describing a
    // system rather than a request.
    const graph = buildEventGraph(gatedTurn())
    const ids = graph.nodes.map((n) => n.id)

    expect(ids).toContain('preflight')
    expect(ids).toContain('clarification')
    expect(ids).not.toContain('postgres')
    expect(ids.some((id) => id.startsWith('tool:'))).toBe(false)
    expect(ids.some((id) => id.startsWith('qdrant:'))).toBe(false)
  })

  it('produces a different graph for a different execution', () => {
    const full = buildEventGraph(fullTurn())
    const gated = buildEventGraph(gatedTurn())
    expect(full.nodes.map((n) => n.id)).not.toEqual(gated.nodes.map((n) => n.id))
  })

  it('does not draw the user twice under two different names', () => {
    // `user-boundary` is the service acting for the human, not a second actor.
    // Drawn as its own node it produced two disconnected roots for one person.
    const graph = buildEventGraph(fullTurn())
    const ids = graph.nodes.map((n) => n.id)
    expect(ids).toContain('user')
    expect(ids).not.toContain('user-boundary')
    expect(ids.filter((id) => id === 'user')).toHaveLength(1)
  })

  it('draws nothing at all when nothing was recorded', () => {
    expect(buildEventGraph([])).toEqual({ nodes: [], edges: [] })
  })

  it('leaves no node without a parent', () => {
    // A disconnected box in an execution graph reads as a bug in the system
    // rather than in the drawing.
    const graph = buildEventGraph(fullTurn())
    for (const node of graph.nodes) {
      if (node.id === 'user') continue
      expect(graph.edges.some((e) => e.target === node.id)).toBe(true)
    }
  })

  it('counts repeated edges rather than drawing duplicates', () => {
    const graph = buildEventGraph(fullTurn())
    expect(graph.edges.filter((e) => e.id === 'mcp-agent->postgres')).toHaveLength(0)
    const ids = graph.edges.map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe('layoutGraph', () => {
  it('places every node below all of its predecessors', () => {
    const graph = buildEventGraph(fullTurn())
    const layers = layerOf(graph)
    for (const edge of graph.edges) {
      const source = layers.get(edge.source)!
      const target = layers.get(edge.target)!
      // Back-edges (the orchestrator answering the user) are allowed to point
      // upward; every forward edge must descend.
      if (edge.target === 'user') continue
      expect(target).toBeGreaterThan(source - 1)
    }
  })

  it('gives every node a position, whatever the node set turns out to be', () => {
    // The reason positions are computed at all: a fixed table cannot cover a
    // node set that changes per request, and a node with no entry would land at
    // the origin on top of another.
    const graph = buildEventGraph(fullTurn())
    const positions = layoutGraph(graph)
    expect(positions.size).toBe(graph.nodes.length)
    for (const node of graph.nodes) expect(positions.get(node.id)).toBeDefined()
  })

  it('terminates on a graph containing a cycle', () => {
    const cyclic = {
      nodes: [
        { id: 'a', label: 'a', category: 'agent' as const, status: 'completed' as const, order: 0 },
        { id: 'b', label: 'b', category: 'agent' as const, status: 'completed' as const, order: 1 },
      ],
      edges: [
        { id: 'a->b', source: 'a', target: 'b' },
        { id: 'b->a', source: 'b', target: 'a' },
      ],
    }
    expect(() => layoutGraph(cyclic)).not.toThrow()
  })
})

describe('elapsedOf', () => {
  it('reads the turn length from the last event', () => {
    expect(elapsedOf(fullTurn())).toBe(1100)
    expect(elapsedOf([])).toBe(0)
  })
})
