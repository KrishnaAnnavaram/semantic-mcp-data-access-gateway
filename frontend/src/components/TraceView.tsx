import clsx from 'clsx'
import { ExternalLink, CheckCircle2, XCircle, Loader2, CircleDot } from 'lucide-react'
import type { ChatMessage, Handoff, TraceStatus } from '../types/chat'
import { formatDuration, hasTrace, langsmithRef } from '../lib/trace'

// Engineering observability for one turn: the real agent-to-agent timeline (with
// the durations and states the backend actually recorded), the reasoning steps,
// and a link into LangSmith for the full LLM-level span tree. Timing is shown
// only where it exists — never invented.

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
      {traced ? (
        <a
          href={ref.url as string}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-[12px] font-medium text-accent-hover transition-colors hover:bg-accent/20"
        >
          Open full trace
          <ExternalLink size={12} />
        </a>
      ) : (
        <p className="mt-1.5 text-[11px] text-text-faint">
          No LangSmith trace for this turn — tracing is disabled or was unavailable when it ran.
        </p>
      )}
    </div>
  )
}

export function TraceView({ message }: { message: ChatMessage | undefined }) {
  const handoffs = message?.handoffs?.handoffs ?? []
  const trace = message?.trace ?? []
  const maxMs = handoffs.reduce((max, h) => Math.max(max, h.duration_ms || 0), 0)

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {handoffs.length > 0 ? (
          <section>
            <div className="mb-1.5 flex items-center justify-between">
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">Agent timeline</h3>
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
          <p className="text-[12px] text-text-faint">
            No agent-to-agent calls were recorded for this turn (a direct answer needs none).
          </p>
        )}

        {trace.length > 0 && (
          <section className="mt-4">
            <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">Steps</h3>
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
