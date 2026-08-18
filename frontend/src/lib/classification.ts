// A single place deciding what a table's provenance.classification badge
// says. In mock mode, SYNTHETIC_DEMO/REAL_MARKET_DATA labels are both
// misleading — those claim something specific actually happened (a real
// fetch, a real demo-book calculation) that mock mode never does. Mock data
// always reads as "Sample data," regardless of what the fixture's
// classification field says, so a client demo never shows "Live market
// data" while disconnected from any backend.

export type BadgeVariant = 'neutral' | 'success' | 'warning' | 'danger' | 'accent' | 'data'

export interface ClassificationBadge {
  variant: BadgeVariant
  label: string
}

export function classificationBadge(
  classification: string | null | undefined,
  isMock: boolean,
): ClassificationBadge | null {
  if (!classification) return null
  if (isMock) return { variant: 'neutral', label: 'Sample data (mock)' }
  if (classification === 'SYNTHETIC_DEMO') return { variant: 'warning', label: 'Synthetic' }
  if (classification === 'REAL_MARKET_DATA') return { variant: 'success', label: 'Live market data' }
  return null
}
