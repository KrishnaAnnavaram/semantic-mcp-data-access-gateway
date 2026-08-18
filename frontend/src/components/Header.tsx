import { Radio } from 'lucide-react'
import { isMockMode } from '../api/client'
import { ThemeToggle } from './ThemeToggle'

function Logomark() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect width="24" height="24" rx="5" fill="rgb(var(--color-accent))" />
      <path
        d="M5 16C6.8 16 6.8 8 9 8C11.2 8 11.2 13.5 13.4 13.5C15.6 13.5 15.6 8 19 8"
        stroke="white"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
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
            VANTAGE
          </span>
          <span className="hidden text-xs text-text-muted md:inline">
            Semantic Financial Data &amp; Risk Intelligence
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
