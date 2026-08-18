import type { ChatMessage, Provenance, Table } from '../types/chat'

// A table "looks like a curve" if it has a tenor-like column and a rate-like
// column — narrow enough that DV01 (dv01_usd), VaR (metric/value), and stress
// (scenario/pnl_usd) tables never match this by accident.
function curveColumns(table: Table): { tenorIdx: number; rateIdx: number } | null {
  const tenorIdx = table.columns.findIndex((c) => /tenor/i.test(c))
  const rateIdx = table.columns.findIndex((c) => /rate/i.test(c))
  if (tenorIdx === -1 || rateIdx === -1) return null
  return { tenorIdx, rateIdx }
}

function normalizeTenor(label: string): string {
  return label.toLowerCase().replace(/\s+/g, '')
}

function rateAt(table: Table, tenorIdx: number, rateIdx: number, prefix: string): number | null {
  const row = table.rows.find((r) => normalizeTenor(String(r[tenorIdx])).startsWith(prefix))
  if (!row) return null
  const value = row[rateIdx]
  return typeof value === 'number' ? value : null
}

export interface CurveSnapshot {
  table: Table
  twoYear: number | null
  tenYear: number | null
  thirtyYear: number | null
  spreadBps: number | null
  asOf: string | null
  classification: string | null
}

export function findLatestCurveTable(messages: ChatMessage[]): Table | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i]
    if (message.role !== 'assistant' || !message.tables) continue
    for (const table of message.tables) {
      if (curveColumns(table)) return table
    }
  }
  return null
}

// Any table's provenance, not just a curve — the status bar's "as of" should
// reflect the most recent data fetched at all (DV01/VaR/stress included).
export function findLatestProvenance(messages: ChatMessage[]): Provenance | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i]
    if (message.role !== 'assistant' || !message.tables) continue
    for (const table of message.tables) {
      if (table.provenance) return table.provenance
    }
  }
  return null
}

export interface ChartPoint {
  label: string
  value: number
}

// Points for CurveChart, or null when the table isn't curve-shaped (DV01,
// VaR, and stress tables all return null here — same heuristic as above).
export function tableToChartPoints(table: Table): ChartPoint[] | null {
  const cols = curveColumns(table)
  if (!cols) return null
  const points = table.rows
    .map((row) => ({ label: String(row[cols.tenorIdx]), value: row[cols.rateIdx] }))
    .filter((p): p is ChartPoint => typeof p.value === 'number')
  return points.length >= 2 ? points : null
}

export function toSnapshot(table: Table): CurveSnapshot {
  const cols = curveColumns(table)
  const twoYear = cols ? rateAt(table, cols.tenorIdx, cols.rateIdx, '2y') : null
  const tenYear = cols ? rateAt(table, cols.tenorIdx, cols.rateIdx, '10y') : null
  const thirtyYear = cols ? rateAt(table, cols.tenorIdx, cols.rateIdx, '30y') : null
  return {
    table,
    twoYear,
    tenYear,
    thirtyYear,
    spreadBps: twoYear !== null && tenYear !== null ? Math.round((tenYear - twoYear) * 100) : null,
    asOf: table.provenance?.curve_date ?? null,
    classification: table.provenance?.classification ?? null,
  }
}
