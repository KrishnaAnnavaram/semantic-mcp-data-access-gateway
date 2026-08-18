import { Compass, BookOpen, Scale, Plug, CheckCircle2, HelpCircle, type LucideIcon } from 'lucide-react'
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

function TraceStepRow({ step, isLast }: { step: TraceStep; isLast: boolean }) {
  const Icon = STEP_ICON[step.kind] ?? CheckCircle2
  const caption = stepCaption(step)
  return (
    <div className="flex gap-2.5">
      <div className="flex flex-col items-center">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-accent">
          <Icon size={12} />
        </div>
        {!isLast && <div className="w-px flex-1 bg-border" />}
      </div>
      <div className="pb-4">
        <div className="pt-0.5 text-[13px] leading-tight text-text">{step.label}</div>
        {caption && <div className="mt-0.5 truncate text-[11px] text-text-faint">{caption}</div>}
      </div>
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
        <div className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">Reasoning</div>
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
