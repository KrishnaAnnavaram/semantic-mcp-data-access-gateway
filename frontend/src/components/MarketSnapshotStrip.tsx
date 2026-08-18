import { useChatStore } from '../store/chatStore'
import { findLatestCurveTable, toSnapshot } from '../lib/marketSnapshot'
import { classificationBadge } from '../lib/classification'
import { isMockMode } from '../api/client'
import { Badge } from './Badge'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[11px] uppercase tracking-wide text-text-faint">{label}</span>
      <span className="font-mono text-[13px] font-semibold tabular-nums text-text">{value}</span>
    </div>
  )
}

// A thin, always-present strip that reflects the most recent curve-shaped
// table actually returned by a query — real or mock. The classification
// badge is what keeps this honest: mock-mode numbers are never badged as
// "Live market data," no matter what the fixture's own label says.
export function MarketSnapshotStrip() {
  const messages = useChatStore((s) => s.chats[s.activeChatId]?.messages ?? [])
  const table = findLatestCurveTable(messages)

  if (!table) {
    return (
      <div className="flex h-9 shrink-0 items-center border-b border-border bg-surface px-4 text-[12px] text-text-faint">
        No market snapshot yet — ask a curve question to populate this.
      </div>
    )
  }

  const snapshot = toSnapshot(table)
  const badge = classificationBadge(snapshot.classification, isMockMode())
  const spreadLabel =
    snapshot.spreadBps === null ? '—' : `${snapshot.spreadBps > 0 ? '+' : ''}${snapshot.spreadBps}bps`

  return (
    <div className="flex h-9 shrink-0 items-center gap-5 overflow-x-auto border-b border-border bg-surface px-4">
      {snapshot.twoYear !== null && <Stat label="2Y" value={`${snapshot.twoYear.toFixed(2)}%`} />}
      {snapshot.tenYear !== null && <Stat label="10Y" value={`${snapshot.tenYear.toFixed(2)}%`} />}
      {snapshot.thirtyYear !== null && <Stat label="30Y" value={`${snapshot.thirtyYear.toFixed(2)}%`} />}
      <Stat label="10Y–2Y" value={spreadLabel} />
      {badge && (
        <span className="ml-auto shrink-0">
          <Badge variant={badge.variant}>{badge.label}</Badge>
        </span>
      )}
    </div>
  )
}
