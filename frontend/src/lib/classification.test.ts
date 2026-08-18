import { describe, expect, it } from 'vitest'
import { classificationBadge } from './classification'

describe('classificationBadge', () => {
  it('never claims live/synthetic data in mock mode, regardless of the fixture label', () => {
    expect(classificationBadge('REAL_MARKET_DATA', true)).toEqual({ variant: 'neutral', label: 'Sample data (mock)' })
    expect(classificationBadge('SYNTHETIC_DEMO', true)).toEqual({ variant: 'neutral', label: 'Sample data (mock)' })
  })

  it('shows the real classification when connected to a real backend', () => {
    expect(classificationBadge('REAL_MARKET_DATA', false)).toEqual({ variant: 'success', label: 'Live market data' })
    expect(classificationBadge('SYNTHETIC_DEMO', false)).toEqual({ variant: 'warning', label: 'Synthetic' })
  })

  it('returns null when there is no classification to show', () => {
    expect(classificationBadge(null, false)).toBeNull()
    expect(classificationBadge(undefined, true)).toBeNull()
  })
})
