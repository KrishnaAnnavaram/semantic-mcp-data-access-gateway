import { Radio } from 'lucide-react'
import { isMockMode } from '../api/client'
import { getSettings } from '../config'
import { useChatStore } from '../store/chatStore'
import { findLatestProvenance } from '../lib/marketSnapshot'
import type { Provenance } from '../types/chat'

// A slim, always-present footer — connection detail on the left, data
// freshness on the right. Distinct from the header's compact Live/Mock pill:
// this is where the detail lives (which URL, which snapshot date).

// A snapshot sits on one date; a history spans a window. Reading `curve_date`
// for both put "Data as of 2026-08-11" under a table of 2008 observations —
// the rows were right and the footer was wrong, which is the harder failure to
// notice because nothing about the table looked off.
export function describeCoverage(provenance: Provenance | null | undefined): string {
  if (!provenance) return 'No data fetched yet'
  const { observed_from: from, observed_to: to, curve_date: on } = provenance
  if (from && to) return from === to ? `Data for ${from}` : `Data ${from} → ${to}`
  if (on) return `Data as of ${on}`
  return 'No data fetched yet'
}

export function StatusBar() {
  const mock = isMockMode()
  const settings = getSettings()
  const messages = useChatStore((s) => s.chats[s.activeChatId]?.messages ?? [])
  const provenance = findLatestProvenance(messages)

  return (
    <footer className="flex h-7 shrink-0 items-center justify-between border-t border-border bg-surface px-4 text-[11px] text-text-faint">
      <span className="flex items-center gap-1.5">
        <Radio size={10} className={mock ? 'text-warning' : 'text-success'} />
        {mock ? 'Mock backend — canned answers' : `Connected — ${settings.agentApiUrl}`}
      </span>
      <span>
        {describeCoverage(provenance)}
      </span>
    </footer>
  )
}
