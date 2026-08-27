// Placing an execution graph whose node set is not known in advance.
//
// The previous graph could use a table of fixed pixel positions because it drew
// the same seven nodes every time. Once nodes come from the event stream that
// stops working: a turn may draw one MCP tool or four, one Qdrant collection or
// two, a clarification branch or none — and a node with no entry in the table
// would land at the origin, on top of another node.
//
// So position is computed. A longest-path layering (rather than a plain BFS
// depth) puts every node strictly below all of its predecessors, which is what
// makes the flow readable top-to-bottom: with BFS depth, an MCP tool reached
// both from the agent and from a later edge could be placed above something it
// depends on.

import type { EventGraph, EventGraphNode } from './executionEvents'

export interface Placed {
  x: number
  y: number
}

const COLUMN_WIDTH = 210
const ROW_HEIGHT = 108

/**
 * Assign a layer to every node: one more than the deepest of its predecessors.
 *
 * Cycles cannot make this loop forever — the visited guard stops a node being
 * relaxed on a path it already sits on. A cycle is possible here in principle
 * (the orchestrator asks the user, the user answers) so the guard is load-
 * bearing, not defensive decoration.
 */
export function layerOf(graph: EventGraph): Map<string, number> {
  const parents = new Map<string, string[]>()
  for (const node of graph.nodes) parents.set(node.id, [])
  for (const edge of graph.edges) {
    if (!parents.has(edge.target) || !parents.has(edge.source)) continue
    // A self-loop and a back-edge to an earlier node must not deepen the
    // layout; ordering by first appearance keeps the graph a DAG for layout
    // purposes while leaving the real edge drawn.
    parents.get(edge.target)!.push(edge.source)
  }

  const order = new Map(graph.nodes.map((n, i) => [n.id, i]))
  const layers = new Map<string, number>()

  const depth = (id: string, seen: Set<string>): number => {
    if (layers.has(id)) return layers.get(id)!
    if (seen.has(id)) return 0
    seen.add(id)
    let best = 0
    for (const parent of parents.get(id) ?? []) {
      // Only edges that go forward in discovery order contribute depth. The
      // "orchestrator answers the user" edge points back at the first node and
      // must not push the orchestrator below itself.
      if ((order.get(parent) ?? 0) >= (order.get(id) ?? 0)) continue
      best = Math.max(best, depth(parent, seen) + 1)
    }
    seen.delete(id)
    layers.set(id, best)
    return best
  }

  for (const node of graph.nodes) depth(node.id, new Set())
  return layers
}

/** Lay the graph out top-to-bottom, siblings spread across their row. */
export function layoutGraph(graph: EventGraph): Map<string, Placed> {
  const layers = layerOf(graph)
  const rows = new Map<number, EventGraphNode[]>()
  for (const node of graph.nodes) {
    const layer = layers.get(node.id) ?? 0
    const row = rows.get(layer) ?? []
    row.push(node)
    rows.set(layer, row)
  }

  const positions = new Map<string, Placed>()
  for (const [layer, nodes] of rows) {
    // Centre each row on a common axis so the spine stays straight when a layer
    // holds one node and fans out when it holds four.
    const offset = ((nodes.length - 1) * COLUMN_WIDTH) / 2
    nodes
      .slice()
      .sort((a, b) => a.order - b.order)
      .forEach((node, index) => {
        positions.set(node.id, {
          x: index * COLUMN_WIDTH - offset,
          y: layer * ROW_HEIGHT,
        })
      })
  }
  return positions
}
