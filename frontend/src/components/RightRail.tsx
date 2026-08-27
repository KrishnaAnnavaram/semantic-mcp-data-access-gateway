import { useCallback, useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import {
  Lightbulb,
  PanelRightClose,
  GitBranch,
  ListTree,
  Table2,
  Activity,
  Timer,
  Maximize2,
  Minimize2,
} from 'lucide-react'
import { ArtifactPanel } from './ArtifactPanel'
import { ReasoningRail } from './ReasoningRail'
import { GraphView } from './GraphView'
import { TraceView } from './TraceView'
import { ExecutionView } from './ExecutionView'
import { LatencyView } from './LatencyView'
import { useExecutionStore } from '../store/executionStore'
import type { ChatMessage, DataPlan, Negotiation, Table } from '../types/chat'

interface ResolvedArtifact {
  table: Table
  plan: DataPlan | null
  negotiation: Negotiation | null
}

type Tab = 'execution' | 'reasoning' | 'graph' | 'trace' | 'latency' | 'data'

const TABS: { key: Tab; label: string; icon: typeof Lightbulb }[] = [
  { key: 'execution', label: 'Execution', icon: Activity },
  { key: 'reasoning', label: 'Reasoning', icon: Lightbulb },
  { key: 'graph', label: 'Graph', icon: GitBranch },
  { key: 'trace', label: 'Trace', icon: ListTree },
  { key: 'latency', label: 'Latency', icon: Timer },
  { key: 'data', label: 'Data', icon: Table2 },
]

// Width bounds. The lower one keeps the tab strip legible; the upper stops the
// rail from squeezing the conversation out of existence on a narrow screen.
const MIN_WIDTH = 320
const MAX_WIDTH = 900
const DEFAULT_WIDTH = 400
const WIDTH_KEY = 'smcp.rail.width'

interface Props {
  artifact: ResolvedArtifact | null
  onCloseArtifact: () => void
  // The latest assistant turn — the source for every tab. Each is read from
  // this one message, so the panel always reflects one turn's own execution.
  message: ChatMessage | undefined
  sending: boolean
  hasStarted: boolean
}

/** Remembered width, clamped — a stored value from a wider screen must not
 *  reopen the rail wider than this one. */
function storedWidth(): number {
  try {
    const raw = Number(localStorage.getItem(WIDTH_KEY))
    if (Number.isFinite(raw) && raw > 0) return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, raw))
  } catch {
    // Private mode, or site data blocked. A remembered width is a convenience;
    // failing to read one is not worth a broken panel.
  }
  return DEFAULT_WIDTH
}

// The right rail: six tabs over one turn, resizable and maximisable.
//
// EXECUTION is first and is the default, because during the two minutes a real
// risk question takes it is the only tab with anything to say — and a spinner
// with nothing behind it is what made the app feel frozen. It streams live
// while the turn runs and stays readable afterwards.
//
// Width is draggable and remembered, and the whole rail can be maximised over
// the conversation. That is not decoration: a 250-row history in a 380px column
// cannot be reviewed, and the panel is where every reviewable artifact lives.
export function RightRail({ artifact, onCloseArtifact, message, sending, hasStarted }: Props) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<Tab>('execution')
  const [width, setWidth] = useState(storedWidth)
  const [maximised, setMaximised] = useState(false)
  const dragging = useRef(false)
  const visible = open || artifact != null

  const activeRequestId = useExecutionStore((s) => s.activeRequestId)
  const startedAt = useExecutionStore((s) => s.startedAt)
  const runs = useExecutionStore((s) => s.runs)

  // While a turn is in flight the panel follows the LIVE run; once it finishes
  // it follows the selected message's own run. Without the first half the panel
  // would show the previous answer's events during the wait, which is precisely
  // when the user is looking at it.
  const events = activeRequestId
    ? (runs[activeRequestId] ?? [])
    : (runs[message?.request_id ?? ''] ?? [])

  // Opening a table (clicking its card) surfaces it in the Data tab.
  useEffect(() => {
    if (artifact != null) {
      setOpen(true)
      setTab('data')
    }
  }, [artifact])

  // A new turn pulls the panel back to Execution, so the live view is what is
  // on screen while the work happens rather than whatever tab was last read.
  useEffect(() => {
    if (sending) {
      setOpen(true)
      setTab('execution')
    }
  }, [sending])

  const onDrag = useCallback((event: MouseEvent) => {
    if (!dragging.current) return
    // The rail is anchored right, so its width is the distance from the cursor
    // to the window edge.
    const next = window.innerWidth - event.clientX
    setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next)))
  }, [])

  const stopDrag = useCallback(() => {
    if (!dragging.current) return
    dragging.current = false
    document.body.style.userSelect = ''
    try {
      localStorage.setItem(WIDTH_KEY, String(width))
    } catch {
      // Not being able to remember the width costs nothing this session.
    }
  }, [width])

  useEffect(() => {
    window.addEventListener('mousemove', onDrag)
    window.addEventListener('mouseup', stopDrag)
    return () => {
      window.removeEventListener('mousemove', onDrag)
      window.removeEventListener('mouseup', stopDrag)
    }
  }, [onDrag, stopDrag])

  if (!visible) {
    return (
      <div className="flex w-9 shrink-0 flex-col items-center gap-2 border-l border-border bg-surface pt-3">
        <button
          onClick={() => setOpen(true)}
          aria-label="Show reasoning panel"
          title="Show reasoning"
          className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
        >
          <Lightbulb size={16} />
        </button>
        {sending && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-warning" />}
      </div>
    )
  }

  return (
    <div
      className={clsx(
        // `relative` anchors the drag handle; the maximised state escapes to
        // the nearest positioned ancestor, which App marks `relative`.
        'relative flex shrink-0 flex-col border-l border-border bg-surface',
        maximised && 'absolute inset-0 z-30 border-l-0',
      )}
      style={maximised ? undefined : { width }}
    >
      {!maximised && (
        <div
          role="separator"
          aria-label="Resize panel"
          aria-orientation="vertical"
          onMouseDown={() => {
            dragging.current = true
            // Without this a drag selects the text it passes over, which makes
            // the whole app flash blue while the user resizes.
            document.body.style.userSelect = 'none'
          }}
          className="absolute left-0 top-0 h-full w-1 cursor-col-resize hover:bg-accent/30"
          style={{ marginLeft: -2 }}
        />
      )}

      <div className="flex items-center justify-between border-b border-border pl-1 pr-1.5">
        <div className="flex overflow-x-auto" role="tablist" aria-label="Reasoning and observability">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={clsx(
                'flex shrink-0 items-center gap-1.5 border-b-2 px-2.5 py-2.5 text-[11px] font-semibold uppercase tracking-wide transition-colors',
                tab === key ? 'border-accent text-text' : 'border-transparent text-text-faint hover:text-text-muted',
              )}
            >
              <Icon size={13} />
              <span className={clsx(maximised || width > 460 ? 'inline' : 'hidden')}>{label}</span>
              {key === 'execution' && sending && (
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-warning" />
              )}
            </button>
          ))}
        </div>
        <div className="flex shrink-0 items-center">
          <button
            onClick={() => setMaximised((m) => !m)}
            aria-label={maximised ? 'Restore panel' : 'Maximise panel'}
            title={maximised ? 'Restore' : 'Maximise'}
            className="rounded-md p-1 text-text-faint transition-colors hover:bg-surface-hover hover:text-text"
          >
            {maximised ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button
            onClick={() => {
              setOpen(false)
              setMaximised(false)
              if (artifact) onCloseArtifact()
            }}
            aria-label="Hide reasoning panel"
            title="Hide panel"
            className="rounded-md p-1 text-text-faint transition-colors hover:bg-surface-hover hover:text-text"
          >
            <PanelRightClose size={14} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {tab === 'execution' && (
          <ExecutionView events={events} live={sending} startedAt={startedAt} />
        )}
        {tab === 'reasoning' && (
          <ReasoningRail trace={message?.trace} sending={sending} hasStarted={hasStarted} hideHeader />
        )}
        {tab === 'graph' && <GraphView message={message} events={events} />}
        {tab === 'trace' && <TraceView message={message} events={events} />}
        {tab === 'latency' && <LatencyView events={events} latency={message?.latency} />}
        {tab === 'data' &&
          (artifact ? (
            <ArtifactPanel
              table={artifact.table}
              plan={artifact.plan}
              negotiation={artifact.negotiation}
              tall={maximised}
              onClose={() => {
                onCloseArtifact()
                setTab('execution')
              }}
            />
          ) : (
            <div className="flex h-full items-center justify-center px-6 text-center">
              <p className="text-[12px] text-text-faint">
                Open a result table from the chat to inspect its data, data plan, the domain-expert /
                MCP-agent discussion, and its source here.
              </p>
            </div>
          ))}
      </div>
    </div>
  )
}
