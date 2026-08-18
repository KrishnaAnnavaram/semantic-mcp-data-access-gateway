import { Radio } from 'lucide-react'
import { isMockMode } from '../api/client'
import { getSettings } from '../config'
import { useChatStore } from '../store/chatStore'
import { findLatestProvenance } from '../lib/marketSnapshot'

// A slim, always-present footer — connection detail on the left, data
// freshness on the right. Distinct from the header's compact Live/Mock pill:
// this is where the detail lives (which URL, which snapshot date).
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
        {provenance?.curve_date ? `Data as of ${provenance.curve_date}` : 'No data fetched yet'}
      </span>
    </footer>
  )
}
