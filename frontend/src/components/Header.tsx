import clsx from 'clsx'
import { Radio, Activity } from 'lucide-react'
import { isMockMode } from '../api/client'
import { useHealth } from '../hooks/useHealth'
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

// A small status pill. The colour and text come from real state, not from the
// frontend's own mode: "API" reflects whether /health answered, "LangSmith"
// reflects the backend's reported tracing status. No secret is shown.
function StatusPill({
  label,
  ok,
  tone,
  title,
  icon: Icon,
}: {
  label: string
  ok: boolean
  tone: 'success' | 'warning' | 'neutral'
  title: string
  icon: typeof Radio
}) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide',
        tone === 'success' && 'border-success/30 bg-success/10 text-success',
        tone === 'warning' && 'border-warning/30 bg-warning/10 text-warning',
        tone === 'neutral' && 'border-border bg-surface-2 text-text-muted',
      )}
    >
      <span className={clsx('h-1.5 w-1.5 rounded-full', ok ? 'bg-current' : 'bg-current opacity-40')} />
      <Icon size={11} />
      {label}
    </span>
  )
}

export function Header() {
  const mock = isMockMode()
  const { loading, reachable, health } = useHealth()
  const ls = health?.langsmith

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
        {mock ? (
          <StatusPill
            label="Mock backend"
            ok={false}
            tone="warning"
            icon={Radio}
            title="VITE_AGENT_BACKEND=mock — answers are canned, not from the live agent"
          />
        ) : (
          <>
            <StatusPill
              label={loading ? 'API…' : reachable ? 'API' : 'API offline'}
              ok={reachable}
              tone={reachable ? 'success' : 'warning'}
              icon={Radio}
              title={
                reachable
                  ? `Connected to the agent service${health?.llm_backend ? ` — ${health.llm_backend}` : ''}`
                  : 'The agent service at the configured URL did not respond to /health'
              }
            />
            <StatusPill
              label={ls?.enabled ? 'LangSmith' : 'LangSmith off'}
              ok={Boolean(ls?.enabled)}
              tone={ls?.enabled ? 'success' : 'neutral'}
              icon={Activity}
              title={
                ls
                  ? `${ls.reason ?? ''}${ls.project ? ` — project ${ls.project}` : ''}`
                  : reachable
                    ? 'Tracing status unavailable'
                    : 'Backend unreachable — tracing status unknown'
              }
            />
          </>
        )}
        <ThemeToggle />
      </div>
    </header>
  )
}
