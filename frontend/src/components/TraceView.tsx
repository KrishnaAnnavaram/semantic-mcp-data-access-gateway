import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { ExternalLink, CheckCircle2, XCircle, Loader2, CircleDot, RefreshCw } from 'lucide-react'
import type { ChatMessage, Handoff, TraceStatus } from '../types/chat'
import type { ExecutionEvent, LangSmithRun, LangSmithTrace } from '../types/execution'
import { formatDuration, hasTrace, langsmithRef } from '../lib/trace'
import { fetchLangSmithTrace } from '../api/executionStream'
import { agentLabel } from '../lib/executionEvents'

// The TRACE tab: this turn's execution, at three levels of detail.
//
//  1. The gateway's own timeline — every stage with its offset from the start.
//     Always present, because it is built from events this process recorded.
//  2. The agent-to-agent handoff ledger, with the durations the backend measured.
//  3. The LangSmith span tree, fetched ON DEMAND through the backend.
//
// The third is deliberately last and deliberately optional. LangSmith is
// observability, not application state: it ingests asynchronously, it can be
// disabled, and it can be unreachable — so a trace view that went blank without
// it would go blank exactly when someone was trying to work out what went wrong.
// The first two levels answer the question on their own; LangSmith adds the
// model-level spans underneath.
//
// No API key is in this bundle. The browser sends a trace id — which is not a
// credential — to the gateway, which holds the key and sanitises the response
// (backend/src/backend/api/langsmith_reader.py). Prompts, completions and
// retrieved text never cross that boundary.

function statusOf(state: string): TraceStatus {
  if (state === 'completed') return 'completed'
  if (state === 'failed' || state === 'rejected' || state === 'unknown') return 'failed'
  if (state === 'input-required' || state === 'working' || state === 'submitted') return 'running'
  return 'completed'
}

const STATUS_STYLE: Record<TraceStatus, { icon: typeof CheckCircle2; className: string }> = {
  completed: { icon: CheckCircle2, className: 'text-success' },
  failed: { icon: XCircle, className: 'text-danger' },
  running: { icon: Loader2, className: 'text-warning' },
  skipped: { icon: CircleDot, className: 'text-text-faint' },
}

function StatusIcon({ status }: { status: TraceStatus }) {
  const { icon: Icon, className } = STATUS_STYLE[status]
  return <Icon size={13} className={className} />
}

/** Milliseconds since the turn started, as `mm:ss.mmm`. */
function offset(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const millis = Math.floor(ms % 1000)
  return `${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
}

function Timeline({ events }: { events: ExecutionEvent[] }) {
  if (events.length === 0) return null
  return (
    <section>
      <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
        Timeline
      </h3>
      <ol className="rounded-lg border border-border bg-surface-2/40 px-3 py-2 font-mono text-[11px]">
        {events.map((event) => (
          <li key={event.sequence} className="flex gap-2 py-0.5">
            <span className="shrink-0 text-text-faint">{offset(event.elapsed_ms)}</span>
            <span
              className={clsx(
                'min-w-0 flex-1 truncate',
                event.status === 'failed' ? 'text-danger' : 'text-text-muted',
              )}
              title={`${agentLabel(event.agent)} — ${event.title}`}
            >
              {event.title}
            </span>
            {event.duration_ms != null && (
              <span className="shrink-0 text-text-faint">{formatDuration(event.duration_ms)}</span>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}

function HandoffRow({ handoff, maxMs }: { handoff: Handoff; maxMs: number }) {
  const status = statusOf(handoff.state)
  const duration = formatDuration(handoff.duration_ms)
  const width = maxMs > 0 && handoff.duration_ms > 0 ? Math.max(4, (handoff.duration_ms / maxMs) * 100) : 0
  const indent = Math.max(0, handoff.chain_length - 1)
  return (
    <div className="flex items-center gap-2 py-1" style={{ paddingLeft: `${indent * 12}px` }}>
      <StatusIcon status={status} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate text-[12px] text-text">
            <span className="text-text-faint">{handoff.from}</span>
            <span className="text-text-faint"> → </span>
            <span className="font-medium">{handoff.to}</span>
            <span className="text-text-muted">.{handoff.skill}</span>
          </span>
          <span className="shrink-0 font-mono text-[11px] text-text-muted">{duration ?? '—'}</span>
        </div>
        <div className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-surface-2">
          {width > 0 && (
            <div
              className={clsx('h-full rounded-full', status === 'failed' ? 'bg-danger' : 'bg-accent')}
              style={{ width: `${width}%` }}
            />
          )}
        </div>
        {handoff.negotiation_round > 0 && (
          <div className="mt-0.5 text-[10px] text-text-faint">
            round {handoff.negotiation_round}
            {handoff.negotiation_phase ? ` · ${handoff.negotiation_phase.toLowerCase()}` : ''}
            {handoff.duplicate ? ' · answered from earlier call' : ''}
          </div>
        )}
      </div>
    </div>
  )
}

/** Nest the flat LangSmith run list by parent, preserving start order. */
function nest(runs: LangSmithRun[]): { run: LangSmithRun; depth: number }[] {
  const children = new Map<string, LangSmithRun[]>()
  const roots: LangSmithRun[] = []
  const ids = new Set(runs.map((r) => r.id))
  for (const run of runs) {
    // A run whose parent is outside this trace is a root here: showing it at
    // depth zero is better than dropping a span that really executed.
    if (run.parent_id && ids.has(run.parent_id)) {
      children.set(run.parent_id, [...(children.get(run.parent_id) ?? []), run])
    } else {
      roots.push(run)
    }
  }
  const out: { run: LangSmithRun; depth: number }[] = []
  const walk = (run: LangSmithRun, depth: number) => {
    // Bounded: a malformed parent chain must not recurse forever in a browser.
    if (depth > 12) return
    out.push({ run, depth })
    for (const child of children.get(run.id) ?? []) walk(child, depth + 1)
  }
  for (const root of roots) walk(root, 0)
  return out
}

function LangSmithTree({ traceId }: { traceId: string }) {
  const [trace, setTrace] = useState<LangSmithTrace | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    setTrace(await fetchLangSmithTrace(traceId))
    setLoading(false)
  }

  // Not fetched automatically: LangSmith ingests asynchronously, so an
  // immediate fetch usually returns nothing and the user reads "no runs yet"
  // for a turn that traced perfectly well. On request, it is almost always there.
  useEffect(() => {
    setTrace(null)
  }, [traceId])

  if (!trace) {
    return (
      <button
        onClick={load}
        disabled={loading}
        className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-[11px] text-text-muted transition-colors hover:border-accent/40 hover:text-text disabled:opacity-50"
      >
        <RefreshCw size={11} className={loading ? 'animate-spin' : undefined} />
        {loading ? 'Loading spans…' : 'Load LangSmith spans'}
      </button>
    )
  }

  if (!trace.available) {
    return (
      <div className="mt-2 rounded-md border border-border bg-surface-2 p-2.5 text-[11px] text-text-muted">
        {trace.reason ?? 'The LangSmith trace is not available.'}
        <button onClick={load} className="ml-2 text-accent-hover underline underline-offset-2">
          retry
        </button>
      </div>
    )
  }

  const rows = nest(trace.runs)
  const maxMs = rows.reduce((max, r) => Math.max(max, r.run.latency_ms ?? 0), 0)

  return (
    <div className="mt-2 space-y-0.5">
      {rows.map(({ run, depth }) => (
        <div
          key={run.id}
          className="flex items-baseline gap-2 text-[11px]"
          style={{ paddingLeft: `${depth * 10}px` }}
        >
          <span className={clsx('h-1.5 w-1.5 shrink-0 rounded-full', run.error ? 'bg-danger' : 'bg-accent/60')} />
          <span className="min-w-0 flex-1 truncate text-text-muted" title={`${run.run_type} · ${run.name}`}>
            {run.name}
          </span>
          {run.model && <span className="shrink-0 text-text-faint">{run.model}</span>}
          {run.total_tokens != null && (
            <span className="shrink-0 font-mono text-text-faint">{run.total_tokens}t</span>
          )}
          <span className="w-14 shrink-0 text-right font-mono text-text-muted">
            {formatDuration(run.latency_ms) ?? '—'}
          </span>
        </div>
      ))}
      <p className="pt-1 text-[10px] text-text-faint">
        {trace.run_count} span(s) in project {trace.project}
        {trace.truncated ? ' (truncated)' : ''}. Prompts, completions and retrieved text are removed
        server-side and never reach this page. Longest span {formatDuration(maxMs)}.
      </p>
    </div>
  )
}

function LangSmithFooter({ message }: { message: ChatMessage | undefined }) {
  const ref = langsmithRef(message)
  const traced = hasTrace(message)
  return (
    <div className="border-t border-border px-4 py-3">
      <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
        LangSmith
        <span
          className={clsx(
            'inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium normal-case tracking-normal',
            traced ? 'bg-success/10 text-success' : 'bg-surface-2 text-text-muted',
          )}
        >
          <span className={clsx('h-1.5 w-1.5 rounded-full', traced ? 'bg-success' : 'bg-text-faint')} />
          {traced ? 'Traced' : 'Not traced'}
        </span>
      </div>
      {ref.project && <div className="text-[11px] text-text-muted">Project: {ref.project}</div>}

      {/* The deep link and the span tree are gated on DIFFERENT facts, and
          conflating them was a real defect: a turn can carry a run URL without
          a trace id, and treating the missing id as "not traced" hid a working
          link behind a sentence saying there was nothing to show.
          - `url`     -> the deep link out to LangSmith works.
          - `traceId` -> the backend can also fetch the spans and render them here.
          Only when neither is present is this turn genuinely untraced. */}
      {traced && (
        <a
          href={ref.url as string}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-[12px] font-medium text-accent-hover transition-colors hover:bg-accent/20"
        >
          Open full trace
          <ExternalLink size={12} />
        </a>
      )}
      {ref.traceId && <LangSmithTree traceId={ref.traceId} />}
      {!traced && !ref.traceId && (
        <p className="mt-1.5 text-[11px] text-text-faint">
          No LangSmith trace for this turn — tracing is disabled or was unavailable when it ran. The
          gateway's own timeline above is unaffected.
        </p>
      )}
    </div>
  )
}

interface Props {
  message: ChatMessage | undefined
  events: ExecutionEvent[]
}

export function TraceView({ message, events }: Props) {
  const handoffs = message?.handoffs?.handoffs ?? []
  const trace = message?.trace ?? []
  const maxMs = handoffs.reduce((max, h) => Math.max(max, h.duration_ms || 0), 0)

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <Timeline events={events} />

        {handoffs.length > 0 ? (
          <section className={events.length ? 'mt-4' : undefined}>
            <div className="mb-1.5 flex items-center justify-between">
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">
                Agent timeline
              </h3>
              <span className="text-[10px] text-text-faint">
                {handoffs.length} call{handoffs.length === 1 ? '' : 's'}
                {message?.handoffs?.max_chain_reached ? ` · depth ${message.handoffs.max_chain_reached}` : ''}
              </span>
            </div>
            <div className="rounded-lg border border-border bg-surface-2/40 px-3 py-2">
              {handoffs.map((h) => (
                <HandoffRow key={h.sequence} handoff={h} maxMs={maxMs} />
              ))}
            </div>
          </section>
        ) : (
          events.length === 0 && (
            <p className="text-[12px] text-text-faint">
              No agent-to-agent calls were recorded for this turn (a direct answer needs none).
            </p>
          )
        )}

        {trace.length > 0 && (
          <section className="mt-4">
            <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
              Steps
            </h3>
            <ol className="space-y-1">
              {trace.map((step, i) => (
                <li key={i} className="flex items-baseline gap-2 text-[12px]">
                  <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent/60" />
                  <span className="text-text-muted">{step.label}</span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
      <LangSmithFooter message={message} />
    </div>
  )
}
