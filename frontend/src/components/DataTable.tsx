import { useMemo, useState } from 'react'
import { Download, Search, ChevronLeft, ChevronRight } from 'lucide-react'
import type { Table, TableCell } from '../types/chat'

// A results table a quant can actually review.
//
// The old one rendered every row into the DOM inside a 420px box with no
// header pinning and no way to find anything — fine for the ten-row curve it
// was written for, unusable for the 250-row history the risk methodology
// actually reads.
//
// Four things fix that, and the third is the one that matters most:
//  - the header row stays put while the body scrolls (`sticky top-0`)
//  - the whole grid scrolls in both directions inside its own box, so a wide
//    table never pushes the page sideways
//  - only a page of rows is mounted. Paging rather than windowed virtualisation
//    because it is a fraction of the code, has no measurement to get wrong, and
//    for a reviewer "rows 251-500 of 2,410" is more useful than a scrollbar
//    position; the row cap that made virtualisation attractive is what makes
//    paging sufficient.
//  - a filter box, matching on any cell, because finding one date in 250 rows
//    by scrolling is not review
//
// CSV export covers the whole table, never just the visible page — exporting
// what happens to be on screen is how a filtered view becomes a wrong dataset
// in someone's spreadsheet.

const PAGE_SIZE = 100

function toCsv(columns: string[], rows: TableCell[][]): string {
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [columns.map(escape).join(','), ...rows.map((r) => r.map(escape).join(','))].join('\n')
}

function downloadCsv(table: Table) {
  const blob = new Blob([toCsv(table.columns, table.rows)], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'smcp-gateway-export.csv'
  a.click()
  URL.revokeObjectURL(url)
}

interface Props {
  table: Table
  /** Taller in the maximised panel, shorter in the docked rail. */
  maxHeightClass?: string
}

export function DataTable({ table, maxHeightClass = 'max-h-[420px]' }: Props) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return table.rows
    return table.rows.filter((row) =>
      row.some((cell) => cell != null && String(cell).toLowerCase().includes(needle)),
    )
  }, [table.rows, query])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  // A filter that shortens the result can leave the reader on a page that no
  // longer exists; clamping here rather than resetting keeps their position
  // when the filter only trims a few rows.
  const current = Math.min(page, pageCount - 1)
  const visible = filtered.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE)

  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-text-muted">
          {table.truncated
            ? `Showing ${table.rows.length.toLocaleString()} of ${table.row_count.toLocaleString()} rows. The calculation used all ${table.row_count.toLocaleString()}.`
            : `${table.row_count.toLocaleString()} row(s) × ${table.columns.length} column(s)`}
          {query && ` · ${filtered.length.toLocaleString()} match(es)`}
        </p>
        <button
          onClick={() => downloadCsv(table)}
          className="flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[11px] text-text-muted transition-colors hover:border-accent/40 hover:text-text"
          title="Export every row, not just this page"
        >
          <Download size={12} />
          CSV
        </button>
      </div>

      <label className="relative mb-2 block">
        <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-faint" />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(0)
          }}
          placeholder="Filter rows…"
          aria-label="Filter table rows"
          className="w-full rounded-md border border-border bg-surface-2 py-1 pl-7 pr-2 text-[12px] text-text placeholder:text-text-faint focus:border-accent focus:outline-none"
        />
      </label>

      <div className={`md-table-wrap min-h-0 overflow-auto ${maxHeightClass}`}>
        <table className="md-table">
          <thead className="sticky top-0 z-10 bg-surface-2">
            <tr>
              {table.columns.map((c) => (
                <th key={c} className="whitespace-nowrap">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => (
              <tr key={current * PAGE_SIZE + i}>
                {row.map((cell, j) => (
                  <td key={j} className="whitespace-nowrap">
                    {cell === null ? <span className="text-text-faint">—</span> : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={table.columns.length} className="py-4 text-center text-text-faint">
                  No rows match “{query}”.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="mt-2 flex items-center justify-between text-[11px] text-text-muted">
          <button
            onClick={() => setPage(Math.max(0, current - 1))}
            disabled={current === 0}
            className="flex items-center gap-1 rounded px-1.5 py-1 hover:bg-surface-hover disabled:opacity-40"
          >
            <ChevronLeft size={12} />
            Previous
          </button>
          <span className="font-mono">
            {(current * PAGE_SIZE + 1).toLocaleString()}–
            {Math.min((current + 1) * PAGE_SIZE, filtered.length).toLocaleString()} of{' '}
            {filtered.length.toLocaleString()}
          </span>
          <button
            onClick={() => setPage(Math.min(pageCount - 1, current + 1))}
            disabled={current >= pageCount - 1}
            className="flex items-center gap-1 rounded px-1.5 py-1 hover:bg-surface-hover disabled:opacity-40"
          >
            Next
            <ChevronRight size={12} />
          </button>
        </div>
      )}
    </div>
  )
}
