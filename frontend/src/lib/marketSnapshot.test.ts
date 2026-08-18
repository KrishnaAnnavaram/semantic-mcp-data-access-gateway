import { describe, expect, it } from 'vitest'
import { findLatestCurveTable, findLatestProvenance, tableToChartPoints, toSnapshot } from './marketSnapshot'
import type { ChatMessage, Table } from '../types/chat'

const curveTable: Table = {
  columns: ['tenor', 'rate_pct'],
  rows: [
    ['1 Mo', 5.28],
    ['2 Yr', 4.55],
    ['10 Yr', 4.35],
    ['30 Yr', 4.48],
  ],
  row_count: 4,
  provenance: { curve_date: '2026-08-17', classification: 'REAL_MARKET_DATA' },
}

const dv01Table: Table = {
  columns: ['tenor', 'dv01_usd'],
  rows: [
    ['2 Yr', -1250],
    ['10 Yr', 5200],
  ],
  row_count: 2,
  provenance: { curve_date: '2026-08-17', classification: 'SYNTHETIC_DEMO' },
}

function assistantMessage(tables: Table[]): ChatMessage {
  return { role: 'assistant', content: 'answer', tables }
}

describe('findLatestCurveTable', () => {
  it('finds a curve-shaped table and ignores non-curve tables', () => {
    const messages = [assistantMessage([dv01Table]), assistantMessage([curveTable])]
    expect(findLatestCurveTable(messages)).toBe(curveTable)
  })

  it('never matches a DV01 table (no tenor+rate column pair)', () => {
    expect(findLatestCurveTable([assistantMessage([dv01Table])])).toBeNull()
  })

  it('returns null with no messages', () => {
    expect(findLatestCurveTable([])).toBeNull()
  })
})

describe('toSnapshot', () => {
  it('extracts 2Y/10Y/30Y and computes the spread in bps', () => {
    const snapshot = toSnapshot(curveTable)
    expect(snapshot.twoYear).toBe(4.55)
    expect(snapshot.tenYear).toBe(4.35)
    expect(snapshot.thirtyYear).toBe(4.48)
    expect(snapshot.spreadBps).toBe(-20)
    expect(snapshot.asOf).toBe('2026-08-17')
    expect(snapshot.classification).toBe('REAL_MARKET_DATA')
  })
})

describe('tableToChartPoints', () => {
  it('returns points for a curve table', () => {
    expect(tableToChartPoints(curveTable)).toEqual([
      { label: '1 Mo', value: 5.28 },
      { label: '2 Yr', value: 4.55 },
      { label: '10 Yr', value: 4.35 },
      { label: '30 Yr', value: 4.48 },
    ])
  })

  it('returns null for a non-curve table', () => {
    expect(tableToChartPoints(dv01Table)).toBeNull()
  })
})

describe('findLatestProvenance', () => {
  it('finds provenance on any table, not just a curve', () => {
    expect(findLatestProvenance([assistantMessage([dv01Table])])?.classification).toBe('SYNTHETIC_DEMO')
  })
})
