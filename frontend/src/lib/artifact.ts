import type { DataPlan, Table } from '../types/chat'

// One-line card subtitle for an artifact. Never crashes on an empty table or
// a missing plan — both are real states (a table with 0 rows, or a table with
// no requirement attached to it at all).
export function artifactSummary(table: Table, plan: DataPlan | null): string {
  const parts = [`${table.row_count.toLocaleString()} rows × ${table.columns.length} cols`]

  if (plan) {
    if (plan.rows !== null && plan.rows !== undefined) {
      parts.push(plan.grounded ? 'window cited' : 'window NOT cited')
    }
    const unavailable = plan.field_notes.filter((f) => f.verdict === 'unavailable').length
    if (unavailable > 0) {
      parts.push(`${unavailable} field(s) unavailable`)
    }
  }

  return parts.join(' · ')
}
