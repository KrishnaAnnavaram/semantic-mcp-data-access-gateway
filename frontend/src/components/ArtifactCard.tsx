import { ChevronRight, Table2 } from 'lucide-react'
import { artifactSummary } from '../lib/artifact'
import { classificationBadge } from '../lib/classification'
import { isMockMode } from '../api/client'
import { Badge } from './Badge'
import type { DataPlan, Negotiation, Table } from '../types/chat'

interface Props {
  table: Table
  plan: DataPlan | null
  index: number
  onOpen: () => void
}

export function ArtifactCard({ table, plan, index, onOpen }: Props) {
  const badge = classificationBadge(table.provenance?.classification, isMockMode())
  return (
    <button
      onClick={onOpen}
      className="group mt-2 flex w-full items-center justify-between gap-3 rounded-md border border-border bg-surface px-3.5 py-3 text-left transition-colors hover:border-accent/40 hover:bg-surface-2"
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-2 text-text-muted">
          <Table2 size={15} />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-text">Data table {index + 1}</span>
            {badge && <Badge variant={badge.variant}>{badge.label}</Badge>}
          </div>
          <div className="truncate font-mono text-xs text-text-muted">{artifactSummary(table, plan)}</div>
        </div>
      </div>
      <ChevronRight size={16} className="shrink-0 text-text-faint transition-transform group-hover:translate-x-0.5" />
    </button>
  )
}

export function ArtifactCardList({
  tables,
  plan,
  negotiation: _negotiation,
  onOpen,
}: {
  tables: Table[]
  plan: DataPlan | null
  negotiation: Negotiation | null
  onOpen: (artifactIndex: number) => void
}) {
  if (tables.length === 0) return null
  return (
    <div className="max-w-[85%] pl-3.5">
      {tables.map((table, i) => (
        <ArtifactCard key={i} table={table} plan={plan} index={i} onOpen={() => onOpen(i)} />
      ))}
    </div>
  )
}
