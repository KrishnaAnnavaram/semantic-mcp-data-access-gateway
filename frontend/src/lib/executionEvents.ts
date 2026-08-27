// Everything the observability views derive from one turn's execution events.
//
// One input (the event list), four outputs: the activity feed, the timeline,
// the latency waterfall, and the execution graph. They agree by construction
// because they are computed from the same evidence — the previous graph was
// built from a different source than the trace beside it, which is how two
// panels describing the same turn could disagree.
//
// Pure and unit-tested without mounting React. Nothing here invents a duration:
// an event with no measured `duration_ms` produces a row with no bar, because a
// plausible-looking width on an unmeasured span is worse than a gap.

import type { ExecutionEvent, ExecutionStatus } from '../types/execution'
import type { TraceCategory } from '../types/chat'

export interface ActivityLine {
  key: string
  agent: string
  title: string
  summary: string
  status: ExecutionStatus
  elapsedMs: number
  durationMs: number | null
  timestamp: number
  tool: string
  eventType: string
}

/** Agent ids as they travel on the wire (agents/a2a/identity.py). */
export const ORCH = 'orchestrator'
export const DOMAIN = 'domain-expert'
export const MCP = 'mcp-agent'

const AGENT_LABEL: Record<string, string> = {
  [ORCH]: 'Orchestrator',
  [DOMAIN]: 'Domain Expert',
  [MCP]: 'MCP Agent',
  orchestrator_agent: 'Orchestrator',
  domain_expert: 'Domain Expert',
  mcp_agent: 'MCP Agent',
  'data-layer': 'Data layer',
  system: 'Gateway',
}

export function agentLabel(agent: string): string {
  return AGENT_LABEL[agent] ?? agent
}

// Start events whose only job is to open a stage. They are dropped from the
// feed once their completion arrives, so a finished step reads as one line with
// a duration rather than two lines the reader has to pair up themselves.
const START_OF: Record<string, string> = {
  // Routing genuinely is a span: it starts when the orchestrator picks the
  // question up and ends when it has chosen a route. Pairing them means one
  // line that resolves into its own answer, rather than a line that spins for
  // the life of the turn because nothing was ever going to complete it.
  ORCHESTRATOR_STARTED: 'ORCHESTRATOR_DECISION',
  MODEL_CALL_STARTED: 'MODEL_CALL_COMPLETED',
  RETRIEVAL_STARTED: 'RETRIEVAL_COMPLETED',
  MCP_TOOL_STARTED: 'MCP_TOOL_COMPLETED',
  DB_QUERY_STARTED: 'DB_QUERY_COMPLETED',
  DOMAIN_VALIDATION_STARTED: 'DOMAIN_VALIDATION_COMPLETED',
  AGENT_HANDOFF: 'AGENT_HANDOFF_COMPLETED',
  RESPONSE_SYNTHESIS_STARTED: 'RESPONSE_SYNTHESIS_COMPLETED',
}

// A failure terminates its stage too, so a started step whose failure arrived
// must not keep showing as still running.
const FAILURE_OF: Record<string, string> = {
  MODEL_CALL_FAILED: 'MODEL_CALL_STARTED',
  MCP_TOOL_FAILED: 'MCP_TOOL_STARTED',
}

// Completion (or failure) event type -> the start type it closes. Derived once
// from START_OF so the two tables cannot drift apart.
const CLOSES: Record<string, string> = {
  ...Object.fromEntries(Object.entries(START_OF).map(([start, done]) => [done, start])),
  ...FAILURE_OF,
}

/**
 * The activity feed: one line per step.
 *
 * A step that has started but not finished stays on the list as a running line
 * — that is the whole value of the panel, since the thing a user wants to know
 * during a two-minute turn is what is happening *now*. When its completion
 * arrives the same line is upgraded in place with the measured duration, rather
 * than a second line appearing that the reader has to pair up by eye.
 *
 * Pairing is by (start type, agent, tool) in arrival order: a negotiation
 * issues several model calls from the same agent, and the second completion
 * belongs to the second start.
 */
export function toActivity(events: ExecutionEvent[]): ActivityLine[] {
  const lines: ActivityLine[] = []
  const open = new Map<string, ActivityLine[]>()
  const bucketOf = (startType: string, event: ExecutionEvent) =>
    `${startType}|${event.agent}|${event.tool_name}`

  for (const event of events) {
    const closesStart = CLOSES[event.event_type]
    if (closesStart) {
      const queue = open.get(bucketOf(closesStart, event))
      const line = queue?.shift()
      if (line) {
        line.status = event.status
        line.durationMs = event.duration_ms
        line.elapsedMs = event.elapsed_ms
        line.eventType = event.event_type
        if (event.summary) line.summary = event.summary
        continue
      }
    }

    const line: ActivityLine = {
      key: `${event.sequence}`,
      agent: event.agent,
      title: event.title,
      summary: event.summary,
      status: event.status,
      elapsedMs: event.elapsed_ms,
      durationMs: event.duration_ms,
      timestamp: event.timestamp,
      tool: event.tool_name,
      eventType: event.event_type,
    }
    lines.push(line)
    if (event.event_type in START_OF) {
      const bucket = bucketOf(event.event_type, event)
      const queue = open.get(bucket) ?? []
      queue.push(line)
      open.set(bucket, queue)
    }
  }
  return lines
}

export interface WaterfallRow {
  key: string
  label: string
  agent: string
  category: TraceCategory
  startMs: number
  durationMs: number
  status: ExecutionStatus
}

const CATEGORY_OF: Record<string, TraceCategory> = {
  MODEL_CALL_COMPLETED: 'llm',
  MODEL_CALL_FAILED: 'llm',
  RETRIEVAL_COMPLETED: 'retriever',
  MCP_TOOL_COMPLETED: 'mcp',
  MCP_TOOL_FAILED: 'mcp',
  DB_QUERY_COMPLETED: 'database',
  DOMAIN_VALIDATION_COMPLETED: 'agent',
  AGENT_HANDOFF_COMPLETED: 'a2a',
  RESPONSE_SYNTHESIS_COMPLETED: 'llm',
}

/**
 * The waterfall: measured spans only, placed at their real start.
 *
 * `startMs` is back-computed as (elapsed at completion − duration), which is
 * exact rather than approximate: both numbers come from the same monotonic
 * clock on the server. A span with no duration is not drawn at all.
 *
 * `includeNested` is off by default. An A2A handoff contains every model call,
 * retrieval and tool call beneath it, so drawing it beside its own children
 * makes the chart look as though the work happened twice.
 */
export function toWaterfall(
  events: ExecutionEvent[],
  includeNested = false,
): WaterfallRow[] {
  const rows: WaterfallRow[] = []
  for (const event of events) {
    const category = CATEGORY_OF[event.event_type]
    if (!category || event.duration_ms == null) continue
    if (!includeNested && category === 'a2a') continue
    rows.push({
      key: `${event.sequence}`,
      label: event.tool_name || event.title,
      agent: event.agent,
      category,
      startMs: Math.max(0, event.elapsed_ms - event.duration_ms),
      durationMs: event.duration_ms,
      status: event.status,
    })
  }
  return rows.sort((a, b) => a.startMs - b.startMs)
}

// --- the execution graph -----------------------------------------------------

export interface EventGraphNode {
  id: string
  label: string
  sublabel?: string
  category: TraceCategory
  status: ExecutionStatus
  durationMs?: number
  /** Order of first appearance — the sequence a reader follows. */
  order: number
  calls?: number
}

export interface EventGraphEdge {
  id: string
  source: string
  target: string
  label?: string
  count?: number
}

export interface EventGraph {
  nodes: EventGraphNode[]
  edges: EventGraphEdge[]
}

/**
 * The graph of what actually executed, node by node, from the event stream.
 *
 * A node exists only where an event proves the thing ran, so an incomplete
 * request that stopped at the gate draws User → Orchestrator → Domain Expert →
 * Clarification and NO Qdrant, NO MCP, NO PostgreSQL — which is the whole point:
 * the picture has to show that the expensive path was avoided, not imply it ran.
 *
 * Every MCP tool gets its own node, so two tools in one turn are two boxes with
 * their own durations rather than one box labelled "MCP".
 */
export function buildEventGraph(events: ExecutionEvent[]): EventGraph {
  const nodes = new Map<string, EventGraphNode>()
  const edges = new Map<string, EventGraphEdge>()
  let order = 0

  const node = (id: string, init: Omit<EventGraphNode, 'id' | 'order'>) => {
    const existing = nodes.get(id)
    if (existing) return existing
    order += 1
    const created: EventGraphNode = { id, order, ...init }
    nodes.set(id, created)
    return created
  }
  const edge = (source: string, target: string, label?: string) => {
    const id = `${source}->${target}`
    const existing = edges.get(id)
    if (existing) {
      existing.count = (existing.count ?? 1) + 1
      return
    }
    edges.set(id, { id, source, target, label, count: 1 })
  }

  if (events.length === 0) return { nodes: [], edges: [] }

  node('user', { label: 'User', category: 'pipeline', status: 'completed' })

  for (const event of events) {
    switch (event.event_type) {
      case 'ORCHESTRATOR_STARTED':
      case 'ORCHESTRATOR_DECISION': {
        const orch = node(ORCH, {
          label: 'Orchestrator',
          sublabel: 'routing + reply',
          category: 'agent',
          status: 'completed',
        })
        if (event.event_type === 'ORCHESTRATOR_DECISION') {
          orch.sublabel = String(event.metadata.route ?? orch.sublabel)
        }
        edge('user', ORCH)
        break
      }
      case 'AGENT_HANDOFF': {
        // `user-boundary` is the FastAPI service acting for the human — it is
        // the user's side of the system, not a separate participant. Normalise
        // it to the `user` node before creating anything, or the graph grows a
        // second root that is the same actor under its internal name.
        const raw = String(event.metadata.caller ?? ORCH)
        const caller = raw === 'user-boundary' ? 'user' : raw
        const target = event.agent
        node(caller, {
          label: agentLabel(caller),
          category: caller === 'user' ? 'pipeline' : 'agent',
          status: 'completed',
        })
        node(target, {
          label: agentLabel(target),
          sublabel: String(event.metadata.skill ?? ''),
          category: 'agent',
          status: 'running',
        })
        edge(caller, target, 'A2A')
        break
      }
      case 'AGENT_HANDOFF_COMPLETED': {
        const target = nodes.get(event.agent)
        if (target) {
          target.durationMs = (target.durationMs ?? 0) + (event.duration_ms ?? 0)
          target.calls = (target.calls ?? 0) + 1
          target.status = event.status === 'failed' ? 'failed' : 'completed'
        }
        break
      }
      case 'DOMAIN_VALIDATION_COMPLETED': {
        const gate = node('preflight', {
          label: 'Requirement gate',
          sublabel: String(event.metadata.intent ?? 'completeness check'),
          category: 'agent',
          status: event.metadata.complete ? 'completed' : 'failed',
        })
        gate.durationMs = event.duration_ms ?? undefined
        edge(DOMAIN, 'preflight')
        break
      }
      case 'CLARIFICATION_REQUIRED': {
        node('clarification', {
          label: 'Clarification required',
          sublabel: String(event.summary || 'missing inputs'),
          category: 'pipeline',
          status: 'failed',
        })
        edge('preflight', 'clarification')
        edge('clarification', ORCH, 'ask user')
        edge(ORCH, 'user', 'question')
        break
      }
      case 'RETRIEVAL_COMPLETED': {
        const id = `qdrant:${event.metadata.collection ?? 'knowledge'}`
        const store = node(id, {
          label: 'Qdrant',
          sublabel: String(event.metadata.collection ?? 'knowledge'),
          category: 'retriever',
          status: event.status,
        })
        store.durationMs = (store.durationMs ?? 0) + (event.duration_ms ?? 0)
        store.calls = (store.calls ?? 0) + 1
        edge(DOMAIN, id)
        break
      }
      case 'MCP_TOOL_COMPLETED':
      case 'MCP_TOOL_FAILED': {
        const tool = event.tool_name || 'mcp tool'
        const id = `tool:${tool}`
        const toolNode = node(id, {
          label: tool,
          sublabel: String(event.metadata.server ?? 'MCP'),
          category: 'tool',
          status: event.event_type === 'MCP_TOOL_FAILED' ? 'failed' : 'completed',
        })
        toolNode.durationMs = (toolNode.durationMs ?? 0) + (event.duration_ms ?? 0)
        toolNode.calls = (toolNode.calls ?? 0) + 1
        if (event.event_type === 'MCP_TOOL_FAILED') toolNode.status = 'failed'
        edge(MCP, id)
        edge(id, 'postgres')
        node('postgres', {
          label: 'PostgreSQL',
          sublabel: 'Treasury rates',
          category: 'database',
          status: 'completed',
        })
        break
      }
      case 'DB_QUERY_COMPLETED': {
        const db = node('postgres', {
          label: 'PostgreSQL',
          sublabel: 'Treasury rates',
          category: 'database',
          status: event.status,
        })
        db.durationMs = (db.durationMs ?? 0) + (event.duration_ms ?? 0)
        db.calls = (db.calls ?? 0) + 1
        break
      }
      case 'MODEL_CALL_COMPLETED':
      case 'MODEL_CALL_FAILED': {
        // Model time is attributed to the agent that spent it rather than
        // drawn as its own node: a box labelled "LLM" hanging off every agent
        // adds three boxes and no information the durations do not already
        // carry.
        const site = String(event.metadata.call_site ?? event.agent)
        const owner =
          site.startsWith('domain') ? DOMAIN : site.startsWith('mcp') ? MCP : ORCH
        const target = nodes.get(owner)
        if (target && event.event_type === 'MODEL_CALL_FAILED') target.status = 'failed'
        break
      }
      case 'REQUEST_COMPLETED': {
        if (nodes.has(ORCH) && !nodes.has('clarification')) edge(ORCH, 'user', 'answer')
        break
      }
      default:
        break
    }
  }

  // Nothing floats. An agent that ran but whose caller was never recorded is
  // still attached to the orchestrator, because a disconnected node in an
  // execution graph reads as a bug in the system rather than in the drawing.
  for (const id of nodes.keys()) {
    if (id === 'user' || id === ORCH) continue
    const hasParent = [...edges.values()].some((e) => e.target === id)
    if (!hasParent && nodes.has(ORCH)) edge(ORCH, id)
  }

  return {
    nodes: [...nodes.values()].sort((a, b) => a.order - b.order),
    edges: [...edges.values()],
  }
}

/** Total elapsed time for a turn, from its last event. */
export function elapsedOf(events: ExecutionEvent[]): number {
  return events.length ? events[events.length - 1].elapsed_ms : 0
}
