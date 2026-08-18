// Canned demo data for VITE_AGENT_BACKEND=mock. Shaped exactly like a real
// /chat response — including `trace`, whose step shape mirrors
// agents/pipeline.py's `trace.append({"kind", "label", "detail"})` calls
// exactly — so the reasoning rail, artifact panel, and market snapshot strip
// can all be explored with no backend, database, or API key running.

import type { AnswerResult } from './client'
import type { ElicitationPayload, Table, DataPlan, Negotiation, TraceStep } from '../types/chat'

const CURVE_TABLE: Table = {
  columns: ['tenor', 'rate_pct'],
  rows: [
    ['1 Mo', 5.28],
    ['3 Mo', 5.24],
    ['6 Mo', 5.11],
    ['1 Yr', 4.82],
    ['2 Yr', 4.55],
    ['3 Yr', 4.41],
    ['5 Yr', 4.28],
    ['7 Yr', 4.31],
    ['10 Yr', 4.35],
    ['20 Yr', 4.52],
    ['30 Yr', 4.48],
  ],
  row_count: 11,
  truncated: false,
  provenance: {
    dataset_snapshot_id: 'demo-2026-08-17',
    source_file: 'daily_treasury_yield_curve/2026/par_yield_curve.csv',
    curve_date: '2026-08-17',
    quote_basis: 'par_coupon_semiannual',
    classification: 'REAL_MARKET_DATA',
  },
}

const CURVE_PLAN: DataPlan = {
  rows: 11,
  grounded: true,
  row_quote:
    'The par yield curve reports one observation per business day across the full published maturity set.',
  row_reason:
    'A curve snapshot needs every published tenor, not a subset — one row per maturity as of the requested date.',
  fields: ['tenor', 'rate_pct'],
  field_notes: [
    { name: 'tenor', verdict: 'required' },
    { name: 'rate_pct', verdict: 'required' },
    { name: 'cusip', verdict: 'not_needed', reason: 'not requested and not part of a curve snapshot' },
  ],
  citations: [
    { domain: 'market_risk', source: 'curve_construction', heading: 'Par yield curve construction', distance: 0.091 },
  ],
  warnings: [],
  answerable: true,
}

const CURVE_NEGOTIATION: Negotiation = {
  rounds_used: 1,
  converged: true,
  outcome: 'MCP agent confirmed the full published tenor set is available for the requested date; no reduction needed.',
  turns: [
    {
      speaker: 'domain_expert',
      round: 1,
      message: 'I need one row per published tenor for the requested date — tenor label and par yield, nothing else.',
    },
    {
      speaker: 'mcp_agent',
      round: 1,
      message:
        'Confirmed: get_curve returns all 11 currently published tenors for that date, quoted on a semiannual coupon-equivalent basis. Serving it as requested.',
    },
  ],
}

const CURVE_TRACE: TraceStep[] = [
  { kind: 'intent', label: 'Route: data_request', detail: 'Requires current market data — not answerable from conversation alone.' },
  {
    kind: 'tool_call',
    label: 'MCP agent advertised 14 tool(s)',
    detail: { tools: ['get_curve', 'get_rate_history', 'export_curve_csv'], can_calculate: true },
  },
  {
    kind: 'knowledge',
    label: 'Domain expert retrieved 2 chunk(s) from Qdrant',
    detail: ['market_risk/curve_construction', 'market_risk/par_yield_definitions'],
  },
  { kind: 'decision', label: 'Requirement: 2 field(s), 11 row(s)', detail: null },
  { kind: 'decision', label: 'Discussion: 1 round(s), converged', detail: null },
  { kind: 'tool_call', label: 'Fetched 11 row(s)', detail: { title: 'Par yield curve' } },
  { kind: 'answer', label: 'Composed reply', detail: null },
]

const DV01_TABLE: Table = {
  columns: ['tenor', 'dv01_usd'],
  rows: [
    ['2 Yr', -1250],
    ['5 Yr', -3400],
    ['10 Yr', 5200],
    ['30 Yr', 8100],
  ],
  row_count: 4,
  truncated: false,
  provenance: {
    dataset_snapshot_id: 'demo-book-2026-08-17',
    source_file: 'risk-engine-mcp/compute_key_rate_dv01',
    curve_date: '2026-08-17',
    quote_basis: null,
    classification: 'SYNTHETIC_DEMO',
  },
}

const DV01_PLAN: DataPlan = {
  rows: 4,
  grounded: true,
  row_quote: 'Key-rate DV01 is reported per key tenor on the curve — one row per bucket, not an aggregate figure.',
  row_reason: 'The demo book has four key-rate buckets; a portfolio-level DV01 would hide offsetting positions.',
  fields: ['tenor', 'dv01_usd'],
  field_notes: [
    { name: 'tenor', verdict: 'required' },
    { name: 'dv01_usd', verdict: 'required' },
  ],
  citations: [{ domain: 'market_risk', source: 'sensitivities_greeks', heading: 'DV01 and key-rate duration', distance: 0.076 }],
  warnings: [],
  answerable: true,
}

const DV01_NEGOTIATION: Negotiation = {
  rounds_used: 1,
  converged: true,
  outcome: 'MCP agent confirmed the risk engine can compute key-rate DV01 for the demo book directly.',
  turns: [
    { speaker: 'domain_expert', round: 1, message: 'I need key-rate DV01 per tenor bucket for SYNTHETIC_DEMO — the demo book only, nothing implying a real position.' },
    { speaker: 'mcp_agent', round: 1, message: 'Confirmed: compute_key_rate_dv01_tool runs against TREASURY_DEMO_001 and returns four buckets. Labelled SYNTHETIC_DEMO throughout.' },
  ],
}

const DV01_TRACE: TraceStep[] = [
  { kind: 'intent', label: 'Route: data_request', detail: 'Requires a risk-engine calculation on the demo book.' },
  { kind: 'tool_call', label: 'MCP agent advertised 5 risk tool(s)', detail: { tools: ['compute_dv01_tool', 'compute_key_rate_dv01_tool'], can_calculate: true } },
  { kind: 'knowledge', label: 'Domain expert retrieved 1 chunk(s) from Qdrant', detail: ['market_risk/sensitivities_greeks'] },
  { kind: 'decision', label: 'Requirement: 2 field(s), 4 row(s)', detail: null },
  { kind: 'decision', label: 'Discussion: 1 round(s), converged', detail: null },
  { kind: 'tool_call', label: 'Fetched 4 row(s)', detail: { title: 'Key-rate DV01 — demo book' } },
  { kind: 'answer', label: 'Composed reply', detail: null },
]

const VAR_TABLE: Table = {
  columns: ['metric', 'value'],
  rows: [
    ['99% 10-day Historical VaR', '$482,000'],
    ['Expected Shortfall (97.5%)', '$561,000'],
    ['Observations used', 250],
  ],
  row_count: 3,
  truncated: false,
  provenance: {
    dataset_snapshot_id: 'demo-book-2026-08-17',
    source_file: 'risk-engine-mcp/compute_historical_risk',
    curve_date: '2026-08-17',
    quote_basis: null,
    classification: 'SYNTHETIC_DEMO',
  },
}

const VAR_PLAN: DataPlan = {
  rows: 250,
  grounded: true,
  row_quote: 'Historical VaR at the 99% confidence level over a 10-day horizon reads 250 trading days of history.',
  row_reason: 'The methodology fixes the lookback window — 250 observations is the documented minimum, not a choice made per query.',
  fields: ['metric', 'value'],
  field_notes: [
    { name: 'metric', verdict: 'required' },
    { name: 'value', verdict: 'required' },
    { name: 'counterparty_id', verdict: 'unavailable', reason: 'no counterparty-level data in this system — scope is interest-rate market risk only' },
  ],
  citations: [{ domain: 'market_risk', source: 'var_methodology', heading: 'Historical VaR and Expected Shortfall', distance: 0.083 }],
  warnings: ['This is an analytical demonstration on the synthetic demo book, not a regulatory VaR figure.'],
  answerable: true,
}

const VAR_NEGOTIATION: Negotiation = {
  rounds_used: 1,
  converged: true,
  outcome: 'MCP agent confirmed 250 daily observations are available and sufficient for the historical simulation.',
  turns: [
    { speaker: 'domain_expert', round: 1, message: 'Historical VaR needs 250 trading days of curve history to build the P&L distribution — confirm availability before I finalize the requirement.' },
    { speaker: 'mcp_agent', round: 1, message: 'Confirmed: get_rate_history has an unbroken 250-day window ending on the requested date. Running compute_historical_risk_tool now.' },
  ],
}

const VAR_TRACE: TraceStep[] = [
  { kind: 'intent', label: 'Route: data_request', detail: 'Requires a historical simulation on the demo book.' },
  { kind: 'tool_call', label: 'MCP agent advertised 5 risk tool(s)', detail: { tools: ['compute_historical_risk_tool'], can_calculate: true } },
  { kind: 'knowledge', label: 'Domain expert retrieved 2 chunk(s) from Qdrant', detail: ['market_risk/var_methodology', 'market_risk/sensitivities_greeks'] },
  { kind: 'decision', label: 'Requirement: 2 field(s), 250 row(s)', detail: null },
  { kind: 'decision', label: 'Discussion: 1 round(s), converged', detail: null },
  { kind: 'tool_call', label: 'Fetched 3 row(s)', detail: { title: 'Historical VaR — demo book' } },
  { kind: 'answer', label: 'Composed reply', detail: null },
]

const STRESS_TABLE: Table = {
  columns: ['scenario', 'pnl_usd'],
  rows: [
    ['Parallel +100bp', -812000],
    ['Parallel -100bp', 798000],
    ['2s10s steepener (+50bp long end)', -244000],
  ],
  row_count: 3,
  truncated: false,
  provenance: {
    dataset_snapshot_id: 'demo-book-2026-08-17',
    source_file: 'risk-engine-mcp/run_stress',
    curve_date: '2026-08-17',
    quote_basis: null,
    classification: 'SYNTHETIC_DEMO',
  },
}

const STRESS_PLAN: DataPlan = {
  rows: 3,
  grounded: true,
  row_quote: 'A stress scenario reports one row of portfolio P&L per shock applied — not decomposed per position.',
  row_reason: 'Three scenarios were run to show both a parallel shock and a curve-shape shock side by side.',
  fields: ['scenario', 'pnl_usd'],
  field_notes: [
    { name: 'scenario', verdict: 'required' },
    { name: 'pnl_usd', verdict: 'required' },
  ],
  citations: [{ domain: 'market_risk', source: 'sensitivities_greeks', heading: 'Scenario and stress construction', distance: 0.101 }],
  warnings: [],
  answerable: true,
}

const STRESS_NEGOTIATION: Negotiation = {
  rounds_used: 1,
  converged: true,
  outcome: 'MCP agent confirmed the requested scenarios are all registered and re-priceable against the demo book.',
  turns: [
    { speaker: 'domain_expert', round: 1, message: 'I need portfolio-level P&L under a parallel +100bp shock, plus the mirror and one curve-shape scenario for contrast.' },
    { speaker: 'mcp_agent', round: 1, message: 'Confirmed: run_stress_tool has all three scenarios registered against TREASURY_DEMO_001. Bond values are model-implied from the par curve, not executable prices.' },
  ],
}

const STRESS_TRACE: TraceStep[] = [
  { kind: 'intent', label: 'Route: data_request', detail: 'Requires re-pricing the demo book under shocked curves.' },
  { kind: 'tool_call', label: 'MCP agent advertised 5 risk tool(s)', detail: { tools: ['run_stress_tool', 'price_portfolio_tool'], can_calculate: true } },
  { kind: 'knowledge', label: 'Domain expert retrieved 1 chunk(s) from Qdrant', detail: ['market_risk/sensitivities_greeks'] },
  { kind: 'decision', label: 'Requirement: 2 field(s), 3 row(s)', detail: null },
  { kind: 'decision', label: 'Discussion: 1 round(s), converged', detail: null },
  { kind: 'tool_call', label: 'Fetched 3 row(s)', detail: { title: 'Stress scenarios — demo book' } },
  { kind: 'answer', label: 'Composed reply', detail: null },
]

const THIRTY_YEAR_ELICITATION: ElicitationPayload = {
  question: "'30 year' matches more than one series — which did you mean?",
  options: [
    { label: '30-Year Treasury Bond (BC_30YEAR)', value: '30-Year Treasury Bond (BC_30YEAR)' },
    { label: 'Extrapolation factor series (BC_30YEARDISPLAY)', value: 'Extrapolation factor series (BC_30YEARDISPLAY)' },
  ],
}

const THIRTY_YEAR_TRACE: TraceStep[] = [
  { kind: 'intent', label: 'Route: clarify', detail: "'30 year' matches more than one registered series." },
  { kind: 'clarification', label: 'Asked for a missing detail', detail: { question: THIRTY_YEAR_ELICITATION.question, options: THIRTY_YEAR_ELICITATION.options } },
]

function demoAnswer(opts: {
  answer: string
  sources: string[]
  table: Table
  plan: DataPlan
  negotiation: Negotiation
  trace: TraceStep[]
  latencyMs: number
}): AnswerResult {
  return {
    answer: opts.answer,
    sources: opts.sources,
    latencyMs: opts.latencyMs,
    elicitation: null,
    route: 'quant',
    tables: [opts.table],
    dataPlan: opts.plan,
    negotiation: opts.negotiation,
    awaitingClarification: false,
    trace: opts.trace,
  }
}

export function mockDemoAnswer(query: string, latencyMs: number): AnswerResult {
  if (/30[- ]?year/i.test(query)) {
    return {
      answer: THIRTY_YEAR_ELICITATION.question,
      sources: [],
      latencyMs,
      elicitation: THIRTY_YEAR_ELICITATION,
      route: 'clarify',
      tables: [],
      dataPlan: null,
      negotiation: null,
      awaitingClarification: true,
      trace: THIRTY_YEAR_TRACE,
    }
  }

  if (/dv01|key.?rate|duration/i.test(query)) {
    return demoAnswer({
      answer:
        `Key-rate DV01 for the demo book (SYNTHETIC_DEMO) as of 2026-08-17: the 2-year and 5-year buckets carry ` +
        `negative DV01 (short front-end exposure), while 10-year and 30-year are long. A 1bp parallel move nets to ` +
        `roughly +$8,650 for the book. See the table below, and the Data plan tab for the citation behind the methodology.`,
      sources: ['market_risk/sensitivities_greeks'],
      table: DV01_TABLE,
      plan: DV01_PLAN,
      negotiation: DV01_NEGOTIATION,
      trace: DV01_TRACE,
      latencyMs,
    })
  }

  if (/\bvar\b|value.?at.?risk|expected shortfall/i.test(query)) {
    return demoAnswer({
      answer:
        `99% 10-day Historical VaR on the demo book (SYNTHETIC_DEMO) is $482,000, with Expected Shortfall at the ` +
        `97.5% level of $561,000, computed from 250 trading days of curve history. This is an analytical ` +
        `demonstration, not a regulatory VaR figure — see the Data plan tab for the full caveat.`,
      sources: ['market_risk/var_methodology'],
      table: VAR_TABLE,
      plan: VAR_PLAN,
      negotiation: VAR_NEGOTIATION,
      trace: VAR_TRACE,
      latencyMs,
    })
  }

  if (/stress|shock|scenario/i.test(query)) {
    return demoAnswer({
      answer:
        `Stress results for the demo book (SYNTHETIC_DEMO) as of 2026-08-17: a parallel +100bp shock costs the book ` +
        `roughly $812,000, the mirrored -100bp shock gains $798,000, and a 2s10s steepener costs $244,000. Bond ` +
        `values are model-implied from the par curve, not executable prices.`,
      sources: ['market_risk/sensitivities_greeks'],
      table: STRESS_TABLE,
      plan: STRESS_PLAN,
      negotiation: STRESS_NEGOTIATION,
      trace: STRESS_TRACE,
      latencyMs,
    })
  }

  return demoAnswer({
    answer:
      `Here's the par yield curve as of 2026-08-17 (demo data). The 10-year sits at 4.35%, with the curve mildly ` +
      `inverted from 1 month out to about 2 years before sloping back up. See the table below for the full ` +
      `published tenor set, with the domain expert's requirement and its citation in the Data plan tab.`,
    sources: ['market_risk/curve_construction'],
    table: CURVE_TABLE,
    plan: CURVE_PLAN,
    negotiation: CURVE_NEGOTIATION,
    trace: CURVE_TRACE,
    latencyMs,
  })
}
