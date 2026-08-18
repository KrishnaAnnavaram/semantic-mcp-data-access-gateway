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

// One persistent rail, always visible: the reasoning trail by default, or the
// artifact panel while a table is open (closing it returns to the trail).
export function RightRail({ artifact, onCloseArtifact, trace, sending, hasStarted }: Props) {
  return (
    <div className="w-[380px] shrink-0">
      {artifact ? (
        <ArtifactPanel table={artifact.table} plan={artifact.plan} negotiation={artifact.negotiation} onClose={onCloseArtifact} />
      ) : (
        <ReasoningRail trace={trace} sending={sending} hasStarted={hasStarted} />
      )}
    </div>
  )
}
