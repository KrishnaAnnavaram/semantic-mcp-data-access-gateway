import clsx from 'clsx'
import { Compass, BookOpen, Scale, Plug, CheckCircle2, HelpCircle, ChevronDown, type LucideIcon } from 'lucide-react'
import { Badge } from './Badge'
import type { TraceKind, TraceStep } from '../types/chat'

const STEP_ICON: Record<TraceKind, LucideIcon> = {
  intent: Compass,
  knowledge: BookOpen,
  decision: Scale,
  tool_call: Plug,
  clarification: HelpCircle,
  answer: CheckCircle2,
}

function stepCaption(step: TraceStep): string | null {
  if (step.kind === 'knowledge' && Array.isArray(step.detail)) {
    return step.detail.join(' · ')
  }
  if (step.kind === 'tool_call' && step.detail && typeof step.detail === 'object') {
    const detail = step.detail as { title?: string; tools?: string[] }
    if (detail.title) return detail.title
    if (detail.tools) return detail.tools.join(' · ')
  }
  return null
}

// The domain-expert/mcp-agent negotiation step carries its outcome in the
// label text itself (pipeline.py: "Discussion: N round(s), converged|not
// converged") — pull it out into the same Badge the artifact panel's
// Discussion tab already uses, instead of leaving it as plain caption text.
function outcomeBadge(step: TraceStep): { variant: 'success' | 'warning'; label: string } | null {
  if (step.kind !== 'decision' || !step.label.startsWith('Discussion:')) return null
  const converged = step.label.endsWith(', converged')
  return { variant: converged ? 'success' : 'warning', label: converged ? 'Converged' : 'Did not converge' }
}

// A node per step, connected by a directional arrow — reads as a flowchart
// of the pipeline rather than a plain timeline, while staying in the app's
// own design tokens (no diagramming library, no separate theme to sync).
function TraceStepRow({ step, isLast }: { step: TraceStep; isLast: boolean }) {
  const Icon = STEP_ICON[step.kind] ?? CheckCircle2
  const caption = stepCaption(step)
  const outcome = outcomeBadge(step)
  const label = outcome ? step.label.replace(/,\s*(not )?converged$/, '') : step.label
  const isFinal = step.kind === 'answer'

  return (
    <div>
      <div className="flex items-start gap-2.5 rounded-lg border border-border bg-surface-2 px-3 py-2.5 shadow-sm">
        <div
          className={clsx(
            'flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
            isFinal ? 'bg-success/10 text-success' : 'bg-accent/10 text-accent',
          )}
        >
          <Icon size={13} />
        </div>
        <div className="min-w-0 flex-1 pt-0.5">
          <div className="text-[13px] leading-tight text-text">{label}</div>
          {outcome ? (
            <div className="mt-1">
              <Badge variant={outcome.variant}>{outcome.label}</Badge>
            </div>
          ) : (
            caption && <div className="mt-0.5 truncate text-[11px] text-text-faint">{caption}</div>
          )}
        </div>
      </div>
      {!isLast && (
        <div className="flex flex-col items-center py-0.5">
          <div className="h-2 w-px bg-text-faint" />
          <ChevronDown size={14} className="text-text-muted" />
        </div>
      )}
    </div>
  )
}

function RunningSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-2.5">
          <div className="h-6 w-6 shrink-0 animate-pulse rounded-full bg-surface-2" />
          <div
            className="h-3 animate-pulse rounded bg-surface-2"
            style={{ width: `${70 - i * 15}%` }}
          />
        </div>
      ))}
    </div>
  )
}

interface Props {
  trace: TraceStep[] | undefined
  sending: boolean
  hasStarted: boolean
}

// Always-visible pipeline view for the latest turn — orchestrator classify,
// Qdrant retrieval, the domain-expert/mcp-agent negotiation, the fetch, and
// the composed reply. This is the project's actual differentiator (grounded,
// negotiated, auditable reasoning), so it stays on screen rather than behind
// a tab click.
export function ReasoningRail({ trace, sending, hasStarted }: Props) {
  return (
    <div className="flex h-full flex-col border-l border-border bg-surface">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
          Reasoning
          {!sending && trace && trace.length > 0 && (
            <span className="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium normal-case tracking-normal text-text-muted">
              {trace.length} steps
            </span>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {sending ? (
          <RunningSkeleton />
        ) : trace && trace.length > 0 ? (
          <div>
            {trace.map((step, i) => (
              <TraceStepRow key={i} step={step} isLast={i === trace.length - 1} />
            ))}
          </div>
        ) : (
          <p className="text-[13px] text-text-faint">
            {hasStarted
              ? 'No reasoning trace was recorded for this turn.'
              : 'Ask a question to see how the answer was reached — orchestrator routing, knowledge retrieval, and the domain-expert / MCP-agent negotiation, step by step.'}
          </p>
        )}
      </div>
    </div>
  )
}
