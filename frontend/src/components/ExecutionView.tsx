import { useEffect, useState } from 'react'
import clsx from 'clsx'
import {
  CheckCircle2,
  XCircle,
  Loader2,
  CircleDot,
  AlertTriangle,
  ArrowRightLeft,
  BookOpen,
  Brain,
  Cable,
  Compass,
  Database,
  Wrench,
} from 'lucide-react'
import type { ExecutionEvent, ExecutionStatus } from '../types/execution'
import { agentLabel, toActivity, type ActivityLine } from '../lib/executionEvents'
import { formatDuration } from '../lib/trace'

// The EXECUTION tab: what the backend is doing, while it does it.
//
// This is the answer to the complaint that started this work — a two-minute
// turn showing nothing but a spinner is indistinguishable from a hang. Every
// line here is a real event the backend published as it happened: the agent,
// the stage, the tool, the status, and the measured duration once it finishes.
//
// What is deliberately NOT here: model prompts, completions, retrieved chunk
// text, or anything else that would amount to showing private reasoning. The
// backend never sends those (agents/events.py sanitises at the source), and
// this component would have nothing to render even if a caller tried.

const STATUS_STYLE: Record<ExecutionStatus, { icon: typeof CheckCircle2; className: string }> = {
  completed: { icon: CheckCircle2, className: 'text-success' },
  failed: { icon: XCircle, className: 'text-danger' },
  running: { icon: Loader2, className: 'text-warning animate-spin' },
  skipped: { icon: CircleDot, className: 'text-text-faint' },
  info: { icon: CircleDot, className: 'text-text-faint' },
}

const AGENT_ICON: Record<string, typeof Compass> = {
  orchestrator: Compass,
  'domain-expert': Brain,
  domain_expert: Brain,
  'mcp-agent': Cable,
  mcp_agent: Cable,
  'data-layer': Database,
  system: ArrowRightLeft,
}

function iconFor(line: ActivityLine) {
  if (line.eventType.startsWith('RETRIEVAL')) return BookOpen
  if (line.eventType.startsWith('MCP_TOOL')) return Wrench
  if (line.eventType.startsWith('DB_QUERY')) return Database
  if (line.eventType === 'CLARIFICATION_REQUIRED') return AlertTriangle
  return AGENT_ICON[line.agent] ?? ArrowRightLeft
}

function clockOf(timestamp: number): string {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return ''
  return new Date(timestamp * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

function ActivityRow({ line }: { line: ActivityLine }) {
  const isClarification = line.eventType === 'CLARIFICATION_REQUIRED'
  // A clarification gets the warning treatment, not the failure treatment: the
  // system stopped on purpose, and colouring that red teaches the reader to
  // distrust the one colour that should mean something went wrong.
  const { icon: StatusIcon, className } = isClarification
    ? { icon: AlertTriangle, className: 'text-warning' }
    : (STATUS_STYLE[line.status] ?? STATUS_STYLE.info)
  const Icon = iconFor(line)
  const duration = formatDuration(line.durationMs)

  return (
    <li
      className={clsx(
        'flex items-start gap-2 rounded-md px-2 py-1.5',
        isClarification && 'bg-warning/10',
        line.status === 'failed' && !isClarification && 'bg-danger/5',
      )}
    >
      <StatusIcon size={13} className={clsx('mt-0.5 shrink-0', className)} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="flex min-w-0 items-baseline gap-1.5">
            <Icon size={11} className="shrink-0 translate-y-px text-text-faint" />
            <span className="truncate text-[12px] text-text">{line.title}</span>
          </span>
          <span className="shrink-0 font-mono text-[10px] text-text-muted">
            {duration ?? (line.status === 'running' ? '…' : '')}
          </span>
        </div>
        <div className="mt-0.5 flex items-baseline gap-2 text-[10px] text-text-faint">
          <span className="font-mono">{clockOf(line.timestamp)}</span>
          <span className="truncate">{agentLabel(line.agent)}</span>
          {line.summary && <span className="truncate text-text-muted">· {line.summary}</span>}
        </div>
      </div>
    </li>
  )
}

/** Seconds elapsed, ticking while a turn is live. */
function useElapsed(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (startedAt == null) return
    // One second is the right resolution for a turn measured in minutes, and it
    // keeps the re-render rate at 1 Hz rather than tied to event arrival.
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [startedAt])
  return startedAt == null ? 0 : Math.max(0, Math.round((now - startedAt) / 1000))
}

interface Props {
  events: ExecutionEvent[]
  live: boolean
  startedAt: number | null
}

export function ExecutionView({ events, live, startedAt }: Props) {
  const lines = toActivity(events)
  const elapsed = useElapsed(live ? startedAt : null)
  const running = lines.filter((l) => l.status === 'running').length
  // Only genuine faults. A clarification is `info` at the source, so this
  // counts what actually went wrong rather than everything that stopped.
  const failed = lines.filter((l) => l.status === 'failed').length
  const clarified = lines.some((l) => l.eventType === 'CLARIFICATION_REQUIRED')

  if (lines.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <p className="text-[12px] text-text-faint">
          {live
            ? 'Connecting to the execution stream…'
            : 'Ask a question to watch the agents work — each routing decision, knowledge search, agent handoff and MCP tool call appears here as it happens.'}
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
          {live ? (
            <>
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-warning" />
              Running
            </>
          ) : (
            <>
              <span
                className={clsx('h-1.5 w-1.5 rounded-full',
                  failed ? 'bg-danger' : clarified ? 'bg-warning' : 'bg-success')}
              />
              {failed ? 'Finished with failures' : clarified ? 'Waiting for you' : 'Finished'}
            </>
          )}
        </span>
        <span className="font-mono text-[11px] text-text-muted">
          {live ? `${elapsed}s elapsed` : `${lines.length} steps`}
          {live && running > 0 ? ` · ${running} active` : ''}
        </span>
      </div>
      <ol className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
        {lines.map((line) => (
          <ActivityRow key={line.key} line={line} />
        ))}
      </ol>
    </div>
  )
}
