import { describe, expect, it } from 'vitest'
import { describeCoverage } from './StatusBar'

// The footer is the only place a reader is told which data they are looking
// at. It used to read `curve_date` for every table, so a table of 2008
// observations was captioned "Data as of 2026-08-11" — the rows were right and
// the caption was wrong, which is the harder failure to catch because nothing
// about the table itself looked off.
describe('describeCoverage', () => {
  it('names the observed window for a history table', () => {
    expect(describeCoverage({ observed_from: '2008-01-02', observed_to: '2008-12-31' }))
      .toBe('Data 2008-01-02 → 2008-12-31')
  })

  it('names the single date when a window covers one day', () => {
    expect(describeCoverage({ observed_from: '2020-03-17', observed_to: '2020-03-17' }))
      .toBe('Data for 2020-03-17')
  })

  it('still reads a curve date for a snapshot', () => {
    expect(describeCoverage({ curve_date: '2026-08-11' })).toBe('Data as of 2026-08-11')
  })

  it('prefers the observed window over a curve date that disagrees with it', () => {
    expect(describeCoverage({
      curve_date: '2026-08-11',
      observed_from: '2008-01-02',
      observed_to: '2008-12-31',
    })).toBe('Data 2008-01-02 → 2008-12-31')
  })

  it('says nothing rather than guessing when there is no provenance', () => {
    expect(describeCoverage(null)).toBe('No data fetched yet')
    expect(describeCoverage({})).toBe('No data fetched yet')
  })
})
