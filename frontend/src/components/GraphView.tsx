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
import type { ChatMessage, TraceCategory, TraceStatus } from '../types/chat'
import { buildExecutionGraph, type GraphNode } from '../lib/executionGraph'
import { formatDuration } from '../lib/trace'

// The GRAPH tab: an interactive React Flow diagram of which agents and services
// actually executed this turn, derived from the handoff ledger + trace (see
// lib/executionGraph.ts). Zoom, pan, fit-view and clickable nodes; nothing is
// drawn that did not run.

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

const STATUS_DOT: Record<TraceStatus, string> = {
  completed: 'bg-success',
  failed: 'bg-danger',
  running: 'bg-warning',
  skipped: 'bg-text-faint',
}

// Fixed, readable layered layout. Only nodes that ran are placed.
const POSITIONS: Record<string, { x: number; y: number }> = {
  user: { x: 150, y: 0 },
  orchestrator: { x: 150, y: 100 },
  'domain-expert': { x: 150, y: 210 },
  qdrant: { x: 370, y: 210 },
  'mcp-agent': { x: 150, y: 320 },
  'mcp-server': { x: 150, y: 430 },
  postgres: { x: 150, y: 530 },
}

// Which handles each edge connects, so the qdrant branch goes sideways and the
// spine goes top-to-bottom.
const EDGE_HANDLES: Record<string, { sourceHandle: string; targetHandle: string }> = {
  'domain-qdrant': { sourceHandle: 'r', targetHandle: 'l' },
}

// React Flow v12 constrains node data to Record<string, unknown>; intersecting
// with it adds the index signature while keeping GraphNode's fields typed.
type ServiceNodeData = GraphNode & { selected?: boolean } & Record<string, unknown>

function ServiceNode({ data }: NodeProps<Node<ServiceNodeData>>) {
  const duration = formatDuration(data.durationMs)
  return (
    <div
      className={clsx(
        'min-w-[150px] rounded-lg border-l-[3px] bg-surface px-3 py-2 shadow-sm ring-1 ring-border transition-shadow',
        CATEGORY_ACCENT[data.category],
        data.selected && 'ring-2 ring-accent',
      )}
    >
      <Handle type="target" position={Position.Top} id="t" className="!bg-text-faint" />
      <Handle type="target" position={Position.Left} id="l" className="!bg-text-faint" />
      <div className="flex items-center gap-1.5">
        <span className={clsx('h-2 w-2 shrink-0 rounded-full', STATUS_DOT[data.status])} />
        <span className="text-[13px] font-medium text-text">{data.label}</span>
      </div>
      {data.sublabel && <div className="mt-0.5 text-[10px] text-text-faint">{data.sublabel}</div>}
      <div className="mt-1 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wide text-text-muted">{data.status}</span>
        {duration && <span className="font-mono text-[10px] text-text-muted">{duration}</span>}
      </div>
      <Handle type="source" position={Position.Bottom} id="b" className="!bg-text-faint" />
      <Handle type="source" position={Position.Right} id="r" className="!bg-text-faint" />
    </div>
  )
}

const nodeTypes = { service: ServiceNode }

function NodeDetail({ node, onClose }: { node: GraphNode; onClose: () => void }) {
  const duration = formatDuration(node.durationMs)
  return (
    <div className="absolute bottom-3 left-3 right-3 z-10 rounded-lg border border-border bg-surface p-3 shadow-lg">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[13px] font-semibold text-text">{node.label}</div>
          {node.sublabel && <div className="text-[11px] text-text-faint">{node.sublabel}</div>}
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

export function GraphView({ message }: { message: ChatMessage | undefined }) {
  const [selected, setSelected] = useState<string | null>(null)

  const graph = useMemo(
    () => buildExecutionGraph(message?.handoffs ?? null, message?.trace),
    [message?.handoffs, message?.trace],
  )

  const nodes: Node<ServiceNodeData>[] = useMemo(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: 'service',
        position: POSITIONS[n.id] ?? { x: 150, y: 0 },
        data: { ...n, selected: n.id === selected },
        draggable: false,
      })),
    [graph.nodes, selected],
  )

  const edges: Edge[] = useMemo(
    () =>
      graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        ...EDGE_HANDLES[e.id],
        animated: e.label === 'A2A',
        style: { stroke: 'rgb(var(--color-text-faint))' },
        labelStyle: { fontSize: 9, fill: 'rgb(var(--color-text-muted))' },
      })),
    [graph.edges],
  )

  const selectedNode = graph.nodes.find((n) => n.id === selected) ?? null

  if (graph.nodes.length <= 1) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <p className="text-[12px] text-text-faint">
          This turn was answered directly by the orchestrator — no specialist agents or data services ran, so there is
          no execution graph to show.
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
        minZoom={0.3}
        maxZoom={2}
      >
        <Background gap={16} className="!bg-surface" />
        <Controls showInteractive={false} />
      </ReactFlow>
      {selectedNode && <NodeDetail node={selectedNode} onClose={() => setSelected(null)} />}
    </div>
  )
}
