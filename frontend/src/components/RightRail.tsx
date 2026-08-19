import { useState } from 'react'
import { Lightbulb, PanelRightClose } from 'lucide-react'
import { ArtifactPanel } from './ArtifactPanel'
import { ReasoningRail } from './ReasoningRail'
import type { DataPlan, Negotiation, Table, TraceStep } from '../types/chat'

interface ResolvedArtifact {
  table: Table
  plan: DataPlan | null
  negotiation: Negotiation | null
}

interface Props {
  artifact: ResolvedArtifact | null
  onCloseArtifact: () => void
  trace: TraceStep[] | undefined
  sending: boolean
  hasStarted: boolean
}

// Closed by default so the chat window gets the full width. Opening an
// artifact always shows the rail regardless of the toggle; closing that
// artifact drops back to whatever the toggle was set to.
export function RightRail({ artifact, onCloseArtifact, trace, sending, hasStarted }: Props) {
  const [open, setOpen] = useState(false)
  const visible = open || artifact != null

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
    <div className="relative w-[380px] shrink-0">
      {artifact ? (
        <ArtifactPanel table={artifact.table} plan={artifact.plan} negotiation={artifact.negotiation} onClose={onCloseArtifact} />
      ) : (
        <>
          <ReasoningRail trace={trace} sending={sending} hasStarted={hasStarted} />
          <button
            onClick={() => setOpen(false)}
            aria-label="Hide reasoning panel"
            title="Hide reasoning"
            className="absolute right-3 top-3 rounded-md p-1 text-text-faint transition-colors hover:bg-surface-hover hover:text-text"
          >
            <PanelRightClose size={14} />
          </button>
        </>
      )}
    </div>
  )
}
