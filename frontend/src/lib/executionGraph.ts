// Derive an execution graph from what ACTUALLY ran this turn — the A2A handoff
// ledger and the decision trace — never a static picture. A node appears only
// when there is evidence it executed, so an orchestrator-only "hi" turn draws
// one node and a full risk turn draws the whole road to PostgreSQL.
//
// This is pure and unit-tested without mounting React. GraphView.tsx turns the
// nodes/edges below into a React Flow diagram; the truth lives here.

import type { Handoffs, TraceCategory, TraceStatus, TraceStep } from '../types/chat'

export interface GraphNode {
  id: string
  label: string
  sublabel?: string
  category: TraceCategory
  status: TraceStatus
  durationMs?: number
  detail?: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label?: string
}

export interface ExecutionGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

// Agent id strings as they travel on the wire (agents/a2a/identity.py).
const ORCH = 'orchestrator'
const DOMAIN = 'domain-expert'
const MCP = 'mcp-agent'

function stateToStatus(state: string | undefined): TraceStatus {
  switch (state) {
    case 'completed':
      return 'completed'
    case 'failed':
    case 'rejected':
    case 'unknown':
      return 'failed'
    case 'input-required':
    case 'working':
    case 'submitted':
      return 'running'
    default:
      return 'completed'
  }
}

interface AgentFacts {
  called: boolean
  durationMs: number
  status: TraceStatus
}

function agentFacts(handoffs: Handoffs | null | undefined, agent: string): AgentFacts {
  const calls = (handoffs?.handoffs ?? []).filter((h) => h.to === agent)
  if (calls.length === 0) return { called: false, durationMs: 0, status: 'completed' }
  const durationMs = calls.reduce((sum, h) => sum + (h.duration_ms || 0), 0)
  // The last call's state is the one that decides how this agent ended.
  const last = calls[calls.length - 1]
  return { called: true, durationMs, status: stateToStatus(last.state) }
}

function hasEdge(handoffs: Handoffs | null | undefined, from: string, to: string): boolean {
  return (handoffs?.handoffs ?? []).some((h) => h.from === from && h.to === to)
}

function traceHas(trace: TraceStep[] | undefined, kind: string, labelIncludes?: string): boolean {
  return (trace ?? []).some(
    (s) => s.kind === kind && (!labelIncludes || s.label.toLowerCase().includes(labelIncludes.toLowerCase())),
  )
}

/** Build the execution graph for one assistant turn. */
export function buildExecutionGraph(
  handoffs: Handoffs | null | undefined,
  trace: TraceStep[] | undefined,
): ExecutionGraph {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []

  const domain = agentFacts(handoffs, DOMAIN)
  const mcp = agentFacts(handoffs, MCP)
  // Qdrant retrieval is evidenced by a "knowledge" step (the domain expert
  // cited chunks) — never assumed just because the domain expert ran.
  const usedQdrant = traceHas(trace, 'knowledge')
  // A real fetch reached the data layer if a row-fetch step ran or the MCP agent
  // was asked to execute a plan.
  const fetched =
    traceHas(trace, 'tool_call', 'Fetched') ||
    traceHas(trace, 'tool_call', 'Resumed and fetched') ||
    (handoffs?.handoffs ?? []).some((h) => h.to === MCP && h.skill === 'execute_data_plan')
  const negotiated = hasEdge(handoffs, DOMAIN, MCP)

  // User → Orchestrator: always present, they are the frame of every turn.
  nodes.push({ id: 'user', label: 'User', category: 'pipeline', status: 'completed' })
  nodes.push({
    id: ORCH,
    label: 'Orchestrator',
    sublabel: 'routing + reply',
    category: 'agent',
    status: 'completed',
  })
  edges.push({ id: 'user-orch', source: 'user', target: ORCH })

  if (domain.called) {
    nodes.push({
      id: DOMAIN,
      label: 'Domain Expert',
      sublabel: 'requirement + citations',
      category: 'agent',
      status: domain.status,
      durationMs: domain.durationMs || undefined,
    })
    edges.push({ id: 'orch-domain', source: ORCH, target: DOMAIN, label: 'A2A' })
  }

  if (usedQdrant && domain.called) {
    nodes.push({ id: 'qdrant', label: 'Qdrant', sublabel: 'knowledge retrieval', category: 'retriever', status: 'completed' })
    edges.push({ id: 'domain-qdrant', source: DOMAIN, target: 'qdrant' })
  }

  if (mcp.called) {
    nodes.push({
      id: MCP,
      label: 'MCP Agent',
      sublabel: 'capability + fetch',
      category: 'agent',
      status: mcp.status,
      durationMs: mcp.durationMs || undefined,
    })
    // The MCP agent is reached from the domain expert during negotiation and
    // from the orchestrator for execution/choices; draw whichever really ran.
    if (negotiated) edges.push({ id: 'domain-mcp', source: DOMAIN, target: MCP, label: 'A2A' })
    if (hasEdge(handoffs, ORCH, MCP)) edges.push({ id: 'orch-mcp', source: ORCH, target: MCP, label: 'A2A' })
    // If neither specific edge is recorded but the MCP agent ran, connect it to
    // the orchestrator so the node is never left floating.
    if (!negotiated && !hasEdge(handoffs, ORCH, MCP)) {
      edges.push({ id: 'orch-mcp', source: ORCH, target: MCP, label: 'A2A' })
    }
  }

  if (fetched && mcp.called) {
    nodes.push({ id: 'mcp-server', label: 'MCP Server', sublabel: 'market-risk-data-mcp', category: 'mcp', status: 'completed' })
    edges.push({ id: 'mcp-server-edge', source: MCP, target: 'mcp-server' })
    nodes.push({ id: 'postgres', label: 'PostgreSQL', sublabel: 'Treasury rates', category: 'database', status: 'completed' })
    edges.push({ id: 'postgres-edge', source: 'mcp-server', target: 'postgres' })
  }

  return { nodes, edges }
}
