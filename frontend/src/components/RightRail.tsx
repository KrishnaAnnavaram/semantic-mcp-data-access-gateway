import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { Lightbulb, PanelRightClose, GitBranch, ListTree, Table2 } from 'lucide-react'
import { ArtifactPanel } from './ArtifactPanel'
import { ReasoningRail } from './ReasoningRail'
import { GraphView } from './GraphView'
import { TraceView } from './TraceView'
import type { ChatMessage, DataPlan, Negotiation, Table } from '../types/chat'

interface ResolvedArtifact {
  table: Table
  plan: DataPlan | null
  negotiation: Negotiation | null
}

type Tab = 'reasoning' | 'graph' | 'trace' | 'data'

const TABS: { key: Tab; label: string; icon: typeof Lightbulb }[] = [
  { key: 'reasoning', label: 'Reasoning', icon: Lightbulb },
  { key: 'graph', label: 'Graph', icon: GitBranch },
  { key: 'trace', label: 'Trace', icon: ListTree },
  { key: 'data', label: 'Data', icon: Table2 },
]

interface Props {
  artifact: ResolvedArtifact | null
  onCloseArtifact: () => void
  // The latest assistant turn — the source for Reasoning, Graph and Trace. Each
  // is read from this one message, so the panel always reflects one turn's own
  // execution rather than a mix.
  message: ChatMessage | undefined
  sending: boolean
  hasStarted: boolean
}

// The right rail is now four tabs — REASONING | GRAPH | TRACE | DATA — over the
// same turn. Reasoning keeps the existing grounded/negotiated pipeline view;
// Graph and Trace are the LangSmith-driven observability views; Data is the
// existing artifact panel (table, data plan, discussion, source). Opening an
// artifact card jumps to the Data tab.
export function RightRail({ artifact, onCloseArtifact, message, sending, hasStarted }: Props) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<Tab>('reasoning')
  const visible = open || artifact != null

  // Opening a table (clicking its card) surfaces it in the Data tab.
  useEffect(() => {
    if (artifact != null) {
      setOpen(true)
      setTab('data')
    }
  }, [artifact])

  if (!visible) {
    return (
      <div className="flex w-9 shrink-0 flex-col items-center border-l border-border bg-surface pt-3">
        <button
          onClick={() => setOpen(true)}
          aria-label="Show reasoning panel"
          title="Show reasoning"
          className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
        >
          <Lightbulb size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex w-[380px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border pl-1 pr-2">
        <div className="flex" role="tablist" aria-label="Reasoning and observability">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={clsx(
                'flex items-center gap-1.5 border-b-2 px-2.5 py-2.5 text-[11px] font-semibold uppercase tracking-wide transition-colors',
                tab === key
                  ? 'border-accent text-text'
                  : 'border-transparent text-text-faint hover:text-text-muted',
              )}
            >
              <Icon size={13} />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>
        <button
          onClick={() => {
            setOpen(false)
            if (artifact) onCloseArtifact()
          }}
          aria-label="Hide reasoning panel"
          title="Hide panel"
          className="rounded-md p-1 text-text-faint transition-colors hover:bg-surface-hover hover:text-text"
        >
          <PanelRightClose size={14} />
        </button>
      </div>

      <div className="min-h-0 flex-1">
        {tab === 'reasoning' && (
          <ReasoningRail trace={message?.trace} sending={sending} hasStarted={hasStarted} hideHeader />
        )}
        {tab === 'graph' && <GraphView message={message} />}
        {tab === 'trace' && <TraceView message={message} />}
        {tab === 'data' &&
          (artifact ? (
            <ArtifactPanel
              table={artifact.table}
              plan={artifact.plan}
              negotiation={artifact.negotiation}
              onClose={() => {
                onCloseArtifact()
                setTab('reasoning')
              }}
            />
          ) : (
            <div className="flex h-full items-center justify-center px-6 text-center">
              <p className="text-[12px] text-text-faint">
                Open a result table from the chat to inspect its data, data plan, the domain-expert / MCP-agent
                discussion, and its source here.
              </p>
            </div>
          ))}
      </div>
    </div>
  )
}
