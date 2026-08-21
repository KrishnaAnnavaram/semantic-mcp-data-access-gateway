import { Radio } from 'lucide-react'
import { isMockMode } from '../api/client'
import { ThemeToggle } from './ThemeToggle'

// Two brackets closing on a single point: a gateway, and the one road through
// it. The mark this replaces was a yield curve, which described the demo
// domain rather than the system — the subject is Treasury rates today and
// something else tomorrow, while the gateway is the part that stays.
function Logomark() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect width="24" height="24" rx="5" fill="rgb(var(--color-accent))" />
      <path
        d="M9.5 7L6 12L9.5 17"
        stroke="white"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M14.5 7L18 12L14.5 17"
        stroke="white"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="1.4" fill="white" />
    </svg>
  )
}

export function Header() {
  const mock = isMockMode()
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-4">
      <div className="flex items-center gap-2.5">
        <Logomark />
        <div className="flex items-baseline gap-2.5">
          <span className="font-serif text-[16px] font-semibold tracking-tight text-text">
            SMCP GATEWAY
          </span>
          <span className="hidden font-mono text-xs text-text-muted md:inline">
            semantic-mcp-data-access-gateway
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span
          className={
            'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide ' +
            (mock ? 'border-warning/30 bg-warning/10 text-warning' : 'border-success/30 bg-success/10 text-success')
          }
          title={mock ? 'VITE_AGENT_BACKEND=mock — answers are canned, not from the live agent' : 'Connected to the live agent service'}
        >
          <Radio size={11} />
          {mock ? 'Mock backend' : 'Live'}
        </span>
        <ThemeToggle />
      </div>
    </header>
  )
}
