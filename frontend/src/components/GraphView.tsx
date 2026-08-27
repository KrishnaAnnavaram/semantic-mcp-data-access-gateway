import { useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import clsx from 'clsx'
import type { ChatMessage, TraceCategory } from '../types/chat'
import type { ExecutionEvent } from '../types/execution'
import { buildExecutionGraph, type GraphNode } from '../lib/executionGraph'
import { buildEventGraph, type EventGraphNode } from '../lib/executionEvents'
import { layoutGraph } from '../lib/graphLayout'
import { formatDuration } from '../lib/trace'

// The GRAPH tab: what actually executed for THIS request.
//
// Built from the turn's execution events, so the picture differs per request by
// construction rather than by intention. A question stopped at the requirement
// gate draws User -> Orchestrator -> Domain Expert -> Requirement gate ->
// Clarification, and draws no Qdrant, no MCP and no PostgreSQL, because none of
// those ran. A full risk turn draws each MCP tool as its own node with its own
// duration. Neither picture is configured anywhere; both are consequences of
// what the backend published.
//
// Positions are computed (lib/graphLayout.ts), not tabulated. A fixed position
// table only works when the node set is fixed, and the node set is exactly what
// stopped being fixed.
//
// Older messages, sent before the live stream existed or after a page reload,
// have no events. Those fall back to the handoff-ledger graph in
// lib/executionGraph.ts — coarser, but still evidence rather than a stock
// diagram.

const CATEGORY_ACCENT: Record<TraceCategory, string> = {
  pipeline: 'border-text-faint',
  agent: 'border-accent',
  llm: 'border-accent',
  a2a: 'border-accent',
  retriever: 'border-data',
  mcp: 'border-warning',
  tool: 'border-warning',
  database: 'border-success',
  cache: 'border-data',
}

const STATUS_DOT: Record<string, string> = {
  completed: 'bg-success',
  failed: 'bg-danger',
  running: 'bg-warning',
  skipped: 'bg-text-faint',
  info: 'bg-text-faint',
}

type ServiceNodeData = {
  label: string
  sublabel?: string
  category: TraceCategory
  status: string
  durationMs?: number
  calls?: number
  selected?: boolean
} & Record<string, unknown>

function ServiceNode({ data }: NodeProps<Node<ServiceNodeData>>) {
  const duration = formatDuration(data.durationMs as number | undefined)
  return (
    <div
      className={clsx(
        'min-w-[150px] max-w-[190px] rounded-lg border-l-[3px] bg-surface px-3 py-2 shadow-sm ring-1 ring-border transition-shadow',
        CATEGORY_ACCENT[data.category],
        data.selected && 'ring-2 ring-accent',
      )}
    >
      <Handle type="target" position={Position.Top} id="t" className="!bg-text-faint" />
      <div className="flex items-center gap-1.5">
        <span className={clsx('h-2 w-2 shrink-0 rounded-full', STATUS_DOT[data.status] ?? 'bg-text-faint')} />
        <span className="truncate text-[13px] font-medium text-text" title={data.label}>
          {data.label}
        </span>
      </div>
      {data.sublabel ? (
        <div className="mt-0.5 truncate text-[10px] text-text-faint" title={String(data.sublabel)}>
          {data.sublabel}
        </div>
      ) : null}
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wide text-text-muted">
          {data.status}
          {typeof data.calls === 'number' && data.calls > 1 ? ` ×${data.calls}` : ''}
        </span>
        {duration && <span className="font-mono text-[10px] text-text-muted">{duration}</span>}
      </div>
      <Handle type="source" position={Position.Bottom} id="b" className="!bg-text-faint" />
    </div>
  )
}

const nodeTypes = { service: ServiceNode }

interface DetailNode {
  id: string
  label: string
  sublabel?: string
  category: TraceCategory
  status: string
  durationMs?: number
  calls?: number
}

function NodeDetail({ node, onClose }: { node: DetailNode; onClose: () => void }) {
  const duration = formatDuration(node.durationMs)
  return (
    <div className="absolute bottom-3 left-3 right-3 z-10 rounded-lg border border-border bg-surface p-3 shadow-lg">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-text">{node.label}</div>
          {node.sublabel && <div className="truncate text-[11px] text-text-faint">{node.sublabel}</div>}
        </div>
        <button onClick={onClose} className="text-[11px] text-text-faint hover:text-text" aria-label="Close details">
          ✕
        </button>
      </div>
      <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-[11px]">
        <dt className="text-text-faint">Type</dt>
        <dd className="text-text">{node.category}</dd>
        <dt className="text-text-faint">Status</dt>
        <dd className="text-text">{node.status}</dd>
        {typeof node.calls === 'number' && (
          <>
            <dt className="text-text-faint">Calls</dt>
            <dd className="font-mono text-text">{node.calls}</dd>
          </>
        )}
        {duration && (
          <>
            <dt className="text-text-faint">Duration</dt>
            <dd className="font-mono text-text">{duration}</dd>
          </>
        )}
      </dl>
    </div>
  )
}

/** Normalise the two graph sources into one shape the renderer understands. */
function resolveGraph(events: ExecutionEvent[], message: ChatMessage | undefined) {
  if (events.length > 0) {
    const graph = buildEventGraph(events)
    return {
      nodes: graph.nodes as (EventGraphNode & DetailNode)[],
      edges: graph.edges,
      source: 'events' as const,
    }
  }
  const fallback = buildExecutionGraph(message?.handoffs ?? null, message?.trace)
  return {
    nodes: fallback.nodes.map((n: GraphNode, i) => ({ ...n, order: i })) as (EventGraphNode & DetailNode)[],
    edges: fallback.edges.map((e) => ({ ...e, count: 1 })),
    source: 'handoffs' as const,
  }
}

interface Props {
  message: ChatMessage | undefined
  events: ExecutionEvent[]
}

export function GraphView({ message, events }: Props) {
  const [selected, setSelected] = useState<string | null>(null)
  const graph = useMemo(() => resolveGraph(events, message), [events, message])
  const positions = useMemo(() => layoutGraph(graph), [graph])

  const nodes: Node<ServiceNodeData>[] = useMemo(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: 'service',
        position: positions.get(n.id) ?? { x: 0, y: 0 },
        data: {
          label: n.label,
          sublabel: n.sublabel,
          category: n.category,
          status: String(n.status),
          durationMs: n.durationMs,
          calls: n.calls,
          selected: n.id === selected,
        },
        draggable: false,
      })),
    [graph, positions, selected],
  )

  const edges: Edge[] = useMemo(
    () =>
      graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: (e.count ?? 1) > 1 ? `${e.label ?? ''} ×${e.count}`.trim() : e.label,
        animated: e.label === 'A2A',
        style: { stroke: 'rgb(var(--color-text-faint))' },
        labelStyle: { fontSize: 9, fill: 'rgb(var(--color-text-muted))' },
      })),
    [graph],
  )

  const selectedNode = graph.nodes.find((n) => n.id === selected) ?? null

  if (graph.nodes.length <= 1) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <p className="text-[12px] text-text-faint">
          This turn was answered directly by the orchestrator — no specialist agents or data services
          ran, so there is no execution graph to show.
        </p>
      </div>
    )
  }

  return (
    <div className="relative h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        colorMode="system"
        onNodeClick={(_e, node) => setSelected(node.id)}
        onPaneClick={() => setSelected(null)}
        minZoom={0.2}
        maxZoom={2}
      >
        <Background gap={16} className="!bg-surface" />
        <Controls showInteractive={false} />
      </ReactFlow>
      {graph.source === 'handoffs' && (
        <div className="absolute right-2 top-2 z-10 rounded bg-surface-2/90 px-2 py-1 text-[10px] text-text-faint">
          from the handoff ledger
        </div>
      )}
      {selectedNode && <NodeDetail node={selectedNode} onClose={() => setSelected(null)} />}
    </div>
  )
}
