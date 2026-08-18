import { describe, expect, it } from 'vitest'
import { artifactSummary } from './artifact'
import type { DataPlan, Table } from '../types/chat'

const table = (overrides: Partial<Table> = {}): Table => ({
  columns: ['tenor', 'rate'],
  rows: [['1M', 5.1]],
  row_count: 1,
  ...overrides,
})

const plan = (overrides: Partial<DataPlan> = {}): DataPlan => ({
  rows: 30,
  grounded: true,
  row_quote: 'reads 30 trading days',
  fields: ['tenor', 'rate'],
  field_notes: [],
  citations: [],
  warnings: [],
  answerable: true,
  ...overrides,
})

describe('artifactSummary', () => {
  it('formats row/col counts', () => {
    expect(artifactSummary(table({ row_count: 1234, columns: ['a', 'b', 'c'] }), null)).toBe(
      '1,234 rows × 3 cols',
    )
  })

  it('reports "window cited" when the plan is grounded', () => {
    expect(artifactSummary(table(), plan({ grounded: true }))).toContain('window cited')
  })

  it('reports "window NOT cited" when the plan is ungrounded', () => {
    expect(artifactSummary(table(), plan({ grounded: false }))).toContain('window NOT cited')
  })

  it('omits the window clause when the plan states no row count', () => {
    expect(artifactSummary(table(), plan({ rows: null }))).not.toMatch(/window/)
  })

  it('counts unavailable fields', () => {
    const p = plan({
      field_notes: [
        { name: 'cusip', verdict: 'unavailable' },
        { name: 'rate', verdict: 'required' },
        { name: 'issuer', verdict: 'unavailable' },
      ],
    })
    expect(artifactSummary(table(), p)).toContain('2 field(s) unavailable')
  })

  it('omits the unavailable clause when nothing is unavailable', () => {
    const p = plan({ field_notes: [{ name: 'rate', verdict: 'required' }] })
    expect(artifactSummary(table(), p)).not.toMatch(/unavailable/)
  })

  it('works with a null plan', () => {
    expect(artifactSummary(table(), null)).toBe('1 rows × 2 cols')
  })

  it('does not crash on an empty table', () => {
    expect(artifactSummary(table({ row_count: 0, columns: [], rows: [] }), null)).toBe('0 rows × 0 cols')
  })
})
