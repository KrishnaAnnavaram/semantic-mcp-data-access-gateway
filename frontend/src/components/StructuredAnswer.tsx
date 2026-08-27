import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AnswerSection, StructuredAnswer as Structured } from '../types/execution'
import type { Table } from '../types/chat'
import { CurveChart } from './CurveChart'
import { tableToChartPoints } from '../lib/marketSnapshot'

// Renders the sectioned reply the orchestrator now produces.
//
// The backend decides which sections exist (agents/answer_builder.py) and drops
// any it has nothing to put in, so this component renders what it is given and
// never invents a heading. That is the point of moving the structure to the
// backend: a section only appears when there is material behind it, rather than
// the client guessing at headings by parsing arbitrary markdown.
//
// The executive answer is rendered on its own above the rest, because that is
// the sentence a reader wants first and the only one many turns need.

function Metrics({ section }: { section: AnswerSection }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {(section.metrics ?? []).map((metric) => (
        <div key={metric.label} className="rounded-lg border border-border bg-surface-2 p-2.5">
          <div className="truncate text-[10px] uppercase tracking-wide text-text-muted" title={metric.label}>
            {metric.label}
          </div>
          <div className="font-mono text-base font-semibold text-data">{metric.value}</div>
          {metric.unit && <div className="mt-0.5 text-[10px] text-text-faint">{metric.unit}</div>}
        </div>
      ))}
    </div>
  )
}

function KeyValues({ section }: { section: AnswerSection }) {
  const items = (section.items ?? []).filter(
    (i): i is { label: string; value: string } => typeof i === 'object' && i !== null,
  )
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto),1fr] gap-x-3 gap-y-1 text-[12px]">
      {items.map((item) => (
        <div key={item.label} className="contents">
          <dt className="text-text-muted">{item.label}</dt>
          <dd className="font-mono text-text">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function Bullets({ section }: { section: AnswerSection }) {
  const items = (section.items ?? []).map((i) => (typeof i === 'string' ? i : `${i.label}: ${i.value}`))
  return (
    <ul className="space-y-1 text-[12px] text-text-muted">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2">
          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent/60" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function Section({
  section,
  tables,
  onOpenTable,
}: {
  section: AnswerSection
  tables: Table[]
  onOpenTable?: (index: number) => void
}) {
  if (section.kind === 'chart') {
    const table = tables[section.chart?.table_index ?? 0]
    const points = table ? tableToChartPoints(table) : null
    // A chart is offered for every table but only drawn when the table is
    // actually curve-shaped. Rendering an empty axis would be worse than
    // showing nothing.
    if (!points) return null
    return (
      <section>
        <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
          {section.title}
        </h3>
        <div className="rounded-md border border-border bg-surface-2 p-3">
          <CurveChart points={points} />
        </div>
      </section>
    )
  }

  if (section.kind === 'table') {
    const index = section.table_index ?? 0
    if (!tables[index]) return null
    return (
      <section>
        <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
          {section.title}
        </h3>
        <button
          onClick={() => onOpenTable?.(index)}
          className="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-left text-[12px] text-text-muted transition-colors hover:border-accent/40 hover:text-text"
        >
          {section.body ?? 'Open the table'} — open in the review panel
        </button>
      </section>
    )
  }

  return (
    <section>
      <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
        {section.title}
      </h3>
      {section.kind === 'metrics' && <Metrics section={section} />}
      {section.kind === 'keyvalue' && <KeyValues section={section} />}
      {section.kind === 'list' && <Bullets section={section} />}
      {section.kind === 'text' && (
        <div className="md-content text-[13px] leading-relaxed text-text-muted">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{section.body ?? ''}</ReactMarkdown>
        </div>
      )}
    </section>
  )
}

interface Props {
  structured: Structured
  tables: Table[]
  onOpenTable?: (index: number) => void
}

export function StructuredAnswerView({ structured, tables, onOpenTable }: Props) {
  const [headline, ...rest] = structured.sections
  const isAnswer = headline?.id === 'answer'

  return (
    <div className="space-y-4">
      {isAnswer && (
        <div className="md-content text-[14px] leading-relaxed text-text">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{headline.body ?? ''}</ReactMarkdown>
        </div>
      )}
      {(isAnswer ? rest : structured.sections).map((section) => (
        <Section key={section.id} section={section} tables={tables} onOpenTable={onOpenTable} />
      ))}
    </div>
  )
}
