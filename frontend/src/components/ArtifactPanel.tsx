import { useState, type ReactNode } from 'react'
import clsx from 'clsx'
import { X, Download, CheckCircle2, AlertTriangle, XCircle, MinusCircle, Brain, Cable } from 'lucide-react'
import { Badge } from './Badge'
import { CurveChart } from './CurveChart'
import { tableToChartPoints } from '../lib/marketSnapshot'
import { classificationBadge } from '../lib/classification'
import { isMockMode } from '../api/client'
import type { DataPlan, Negotiation, Table } from '../types/chat'

type Tab = 'table' | 'plan' | 'discussion' | 'source'

const TABS: { key: Tab; label: string }[] = [
  { key: 'table', label: 'Table' },
  { key: 'plan', label: 'Data plan' },
  { key: 'discussion', label: 'Discussion' },
  { key: 'source', label: 'Source' },
]

interface Props {
  table: Table
  plan: DataPlan | null
  negotiation: Negotiation | null
  onClose: () => void
}

function toCsv(table: Table): string {
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [table.columns.map(escape).join(',')]
  for (const row of table.rows) lines.push(row.map(escape).join(','))
  return lines.join('\n')
}

function downloadCsv(table: Table) {
  const blob = new Blob([toCsv(table)], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'vantage-export.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export function ArtifactPanel({ table, plan, negotiation, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('table')
  const badge = classificationBadge(table.provenance?.classification, isMockMode())

  return (
    <div className="flex h-full flex-col border-l border-border bg-surface">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-text" title="Table">
            Data table
          </div>
          {badge && <Badge variant={badge.variant}>{badge.label}</Badge>}
        </div>
        <button
          onClick={onClose}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-surface-hover hover:text-text"
          aria-label="Close panel"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex shrink-0 gap-1 border-b border-border px-3 pt-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'rounded-t-md px-3 py-1.5 text-xs font-medium transition-colors',
              tab === t.key
                ? 'border-b-2 border-accent text-text'
                : 'text-text-muted hover:text-text',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'table' && <TableTab table={table} />}
        {tab === 'plan' && <PlanTab plan={plan} />}
        {tab === 'discussion' && <DiscussionTab negotiation={negotiation} />}
        {tab === 'source' && <SourceTab table={table} />}
      </div>
    </div>
  )
}

function TableTab({ table }: { table: Table }) {
  const displayed = table.rows.length
  const total = table.row_count
  const points = tableToChartPoints(table)
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs text-text-muted">
          {table.truncated
            ? `Showing ${displayed.toLocaleString()} of ${total.toLocaleString()} rows. The calculation used all ${total.toLocaleString()}.`
            : `${total.toLocaleString()} row(s) × ${table.columns.length} column(s).`}
        </p>
        <button
          onClick={() => downloadCsv(table)}
          className="flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs text-text-muted transition-colors hover:border-accent/40 hover:text-text"
        >
          <Download size={12} />
          Download CSV
        </button>
      </div>
      {points && (
        <div className="mb-4 rounded-md border border-border bg-surface-2 p-3">
          <CurveChart points={points} />
        </div>
      )}
      <div className="md-table-wrap max-h-[420px] overflow-y-auto">
        <table className="md-table">
          <thead>
            <tr>
              {table.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell === null ? <span className="text-text-faint">—</span> : String(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const VERDICT_ICON: Record<string, ReactNode> = {
  required: <CheckCircle2 size={13} className="text-success" />,
  not_needed: <MinusCircle size={13} className="text-text-faint" />,
  unavailable: <AlertTriangle size={13} className="text-warning" />,
}

function PlanTab({ plan }: { plan: DataPlan | null }) {
  if (!plan) {
    return <p className="text-sm text-text-muted">No data plan was recorded for this answer.</p>
  }

  return (
    <div className="space-y-4">
      {plan.warnings.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          {plan.warnings.map((w, i) => (
            <div key={i}>{w}</div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Metric label="Rows returned" value={plan.rows === null ? '—' : plan.rows.toLocaleString()} />
        <Metric label="Fields granted" value={String(plan.fields.length)} />
      </div>

      {plan.rows !== null ? (
        plan.grounded ? (
          <div className="rounded-lg border border-success/30 bg-success/10 p-3">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-success">
              <CheckCircle2 size={13} />
              Grounded in retrieved knowledge
            </div>
            {plan.row_quote && (
              <blockquote className="border-l-2 border-success/40 pl-2.5 text-sm italic text-text-muted">
                “{plan.row_quote}”
              </blockquote>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 rounded-lg border border-danger/30 bg-danger/10 p-3 text-xs font-medium uppercase tracking-wide text-danger">
            <XCircle size={13} />
            Row window stated but not grounded in a citation
          </div>
        )
      ) : (
        <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm text-text-muted">
          No row window was stated for this answer.
        </div>
      )}

      {plan.row_reason && <p className="text-sm text-text-muted">{plan.row_reason}</p>}

      {plan.answerable === false && plan.unanswerable_reason && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
          {plan.unanswerable_reason}
        </div>
      )}

      {plan.field_notes.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
            Field decisions
          </div>
          <ul className="space-y-1">
            {plan.field_notes.map((f) => (
              <li key={f.name} className="flex items-start gap-2 text-sm">
                {VERDICT_ICON[f.verdict]}
                <span className="text-text">
                  <span className="font-mono">{f.name}</span>
                  {f.reason && <span className="text-text-muted"> — {f.reason}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {plan.citations.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">Citations</div>
          <ul className="space-y-1.5">
            {plan.citations.map((c, i) => (
              <li key={i} className="text-sm text-text-muted">
                <span className="text-text">
                  {c.domain}/{c.source}
                </span>{' '}
                — {c.heading} <span className="text-text-faint">· distance {c.distance.toFixed(3)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3">
      <div className="text-xs text-text-muted">{label}</div>
      <div className="font-mono text-lg font-semibold text-data">{value}</div>
    </div>
  )
}

const SPEAKER_LABEL: Record<string, { label: string; icon: ReactNode }> = {
  domain_expert: { label: 'Domain expert', icon: <Brain size={13} /> },
  mcp_agent: { label: 'MCP agent', icon: <Cable size={13} /> },
}

function DiscussionTab({ negotiation }: { negotiation: Negotiation | null }) {
  if (!negotiation) {
    return <p className="text-sm text-text-muted">No negotiation was recorded for this answer.</p>
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Badge variant={negotiation.converged ? 'success' : 'warning'}>
          {negotiation.converged ? 'Converged' : 'Did not converge'}
        </Badge>
        <span className="text-xs text-text-muted">{negotiation.rounds_used} round(s) used</span>
      </div>
      <p className="text-xs text-text-faint">{negotiation.outcome}</p>
      <div className="space-y-2.5">
        {negotiation.turns.map((turn, i) => {
          const speaker = SPEAKER_LABEL[turn.speaker] ?? { label: turn.speaker, icon: null }
          return (
            <div key={i} className="rounded-lg border border-border bg-surface-2 p-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-text">
                {speaker.icon}
                {speaker.label}
                <span className="font-normal text-text-faint">· round {turn.round}</span>
              </div>
              <blockquote className="border-l-2 border-border-strong pl-2.5 text-sm text-text-muted">
                {turn.message}
              </blockquote>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const PROVENANCE_LABELS: Record<string, string> = {
  dataset_snapshot_id: 'Snapshot id',
  source_file: 'Source file',
  curve_date: 'Observation date',
  quote_basis: 'Quoting basis',
  classification: 'Classification',
}

function SourceTab({ table }: { table: Table }) {
  const provenance = table.provenance
  const entries = provenance
    ? (Object.entries(provenance).filter(([, v]) => v != null && v !== '') as [string, string][])
    : []

  if (entries.length === 0) {
    return <p className="text-sm text-text-muted">No provenance was recorded for this table.</p>
  }

  return (
    <div className="space-y-3">
      <dl className="space-y-2">
        {entries.map(([key, value]) => (
          <div key={key} className="flex justify-between gap-3 border-b border-border pb-2 text-sm">
            <dt className="text-text-muted">{PROVENANCE_LABELS[key] ?? key}</dt>
            <dd className="text-right font-mono text-text">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-text-faint">
        For the exact source URL and file hash behind a specific figure, ask the agent to explain that number.
      </p>
    </div>
  )
}
