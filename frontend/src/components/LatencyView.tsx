import clsx from 'clsx'
import type { ExecutionEvent, LatencyReport } from '../types/execution'
import type { TraceCategory } from '../types/chat'
import { toWaterfall, elapsedOf, agentLabel } from '../lib/executionEvents'
import { formatDuration } from '../lib/trace'

// The LATENCY tab: where this turn's time actually went.
//
// Two views of the same measured evidence — a waterfall placing every measured
// span at its real start, and the component table summed from those same spans.
// Both are computed per request from real durations; nothing here is a
// configured constant or a typical value, so a turn that was slow for an
// unusual reason shows the unusual reason.
//
// The honesty rule this component exists to keep: an A2A handoff CONTAINS the
// model calls, retrievals and tool calls made beneath it. Drawing it next to
// its own children would show the same seconds two or three times over, so
// nested rows are excluded from the chart and reported separately in the table,
// with no percentage — a percentage of a total it double-counts is a number
// with no meaning.

const CATEGORY_BAR: Record<TraceCategory, string> = {
  pipeline: 'bg-text-faint',
  agent: 'bg-accent',
  llm: 'bg-accent',
  a2a: 'bg-text-faint',
  retriever: 'bg-data',
  mcp: 'bg-warning',
  tool: 'bg-warning',
  database: 'bg-success',
  cache: 'bg-data',
}

// Component key -> the phrase a reader recognises. `llm:<call_site>` is split
// so the three model seats read as the agents they belong to, which is the
// distinction that makes the table actionable.
const COMPONENT_LABEL: Record<string, string> = {
  'llm:orchestrator': 'Orchestrator (LLM)',
  'llm:domain_expert': 'Domain Expert (LLM)',
  'llm:mcp_agent': 'MCP Agent (LLM)',
  'llm:host_agent': 'Host agent (LLM)',
  qdrant: 'Qdrant retrieval',
  mcp_tool: 'MCP tools',
  postgres: 'PostgreSQL',
  preflight: 'Requirement gate',
  a2a_handoff: 'A2A handoffs (contains the rows above)',
}

function componentLabel(key: string): string {
  if (COMPONENT_LABEL[key]) return COMPONENT_LABEL[key]
  if (key.startsWith('llm:')) return `${agentLabel(key.slice(4))} (LLM)`
  return key
}

function Waterfall({ events }: { events: ExecutionEvent[] }) {
  const rows = toWaterfall(events)
  const span = Math.max(elapsedOf(events), 1)
  if (rows.length === 0) return null

  return (
    <section>
      <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
        Waterfall
      </h3>
      <div className="space-y-1 rounded-lg border border-border bg-surface-2/40 px-3 py-2">
        {rows.map((row) => {
          const left = (row.startMs / span) * 100
          // A sub-percent span would render as an invisible sliver; 0.8% is the
          // narrowest bar that still reads as a bar. The label carries the real
          // duration, so the floor cannot mislead about the number.
          const width = Math.max(0.8, (row.durationMs / span) * 100)
          return (
            <div key={row.key} className="flex items-center gap-2">
              <span className="w-[38%] shrink-0 truncate text-[11px] text-text-muted" title={row.label}>
                {row.label}
              </span>
              <span className="relative h-2.5 flex-1 overflow-hidden rounded-sm bg-surface-2">
                <span
                  className={clsx(
                    'absolute inset-y-0 rounded-sm',
                    row.status === 'failed' ? 'bg-danger' : CATEGORY_BAR[row.category],
                  )}
                  style={{ left: `${Math.min(99, left)}%`, width: `${width}%` }}
                />
              </span>
              <span className="w-14 shrink-0 text-right font-mono text-[10px] text-text-muted">
                {formatDuration(row.durationMs)}
              </span>
            </div>
          )
        })}
      </div>
      <p className="mt-1 text-[10px] text-text-faint">
        Each bar is one measured span, placed at the time it actually started. Agent-to-agent
        handoffs are excluded here because each one contains the spans beneath it.
      </p>
    </section>
  )
}

function ComponentTable({ report }: { report: LatencyReport }) {
  if (!report.components.length) return null
  return (
    <section className="mt-4">
      <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
        By component
      </h3>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[26rem] border-collapse text-[11px]">
          <thead>
            <tr className="border-b border-border bg-surface-2/60 text-text-faint">
              <th className="px-2 py-1.5 text-left font-medium">Component</th>
              <th className="px-2 py-1.5 text-right font-medium">Calls</th>
              <th className="px-2 py-1.5 text-right font-medium">Total</th>
              <th className="px-2 py-1.5 text-right font-medium">Avg</th>
              <th className="px-2 py-1.5 text-right font-medium">Max</th>
              <th className="px-2 py-1.5 text-right font-medium">% turn</th>
            </tr>
          </thead>
          <tbody>
            {report.components.map((row) => (
              <tr
                key={row.component}
                className={clsx('border-b border-border/60 last:border-0', row.nested && 'text-text-faint')}
              >
                <td className="px-2 py-1.5 text-text">{componentLabel(row.component)}</td>
                <td className="px-2 py-1.5 text-right font-mono">{row.calls}</td>
                <td className="px-2 py-1.5 text-right font-mono text-data">
                  {formatDuration(row.total_ms)}
                </td>
                <td className="px-2 py-1.5 text-right font-mono">{formatDuration(row.avg_ms)}</td>
                <td className="px-2 py-1.5 text-right font-mono">{formatDuration(row.max_ms)}</td>
                <td className="px-2 py-1.5 text-right font-mono">
                  {row.pct == null ? <span title="Nested: contains the rows above">—</span> : `${row.pct}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

interface Props {
  events: ExecutionEvent[]
  latency: LatencyReport | null | undefined
}

export function LatencyView({ events, latency }: Props) {
  if (!latency && events.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <p className="text-[12px] text-text-faint">
          No timing was recorded for this turn. Latency is measured per request, so it appears once a
          question has been answered.
        </p>
      </div>
    )
  }

  const total = latency?.total_ms ?? elapsedOf(events)
  const unattributed = latency?.unattributed_ms ?? 0
  const attributed = latency?.attributed_ms ?? 0

  return (
    <div className="h-full overflow-y-auto px-4 py-4">
      <div className="mb-4 grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-border bg-surface-2 p-2.5">
          <div className="text-[10px] uppercase tracking-wide text-text-muted">Total turn</div>
          <div className="font-mono text-lg font-semibold text-data">{formatDuration(total)}</div>
        </div>
        <div className="rounded-lg border border-border bg-surface-2 p-2.5">
          <div className="text-[10px] uppercase tracking-wide text-text-muted">Instrumented</div>
          <div className="font-mono text-lg font-semibold text-text">{formatDuration(attributed)}</div>
        </div>
      </div>

      <Waterfall events={events} />
      {latency && <ComponentTable report={latency} />}

      {unattributed > 0 && (
        <p className="mt-3 text-[10px] leading-relaxed text-text-faint">
          {formatDuration(unattributed)} is not attributed to any component — HTTP handling,
          serialisation, session bookkeeping, and any stage with no instrumentation of its own. It is
          reported rather than distributed across the rows above, because spreading an unmeasured gap
          over measured components would make every number in the table slightly wrong.
        </p>
      )}
    </div>
  )
}
