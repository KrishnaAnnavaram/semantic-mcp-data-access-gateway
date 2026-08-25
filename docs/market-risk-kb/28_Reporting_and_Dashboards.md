# 28 — Market Risk Reporting and Dashboards

**Level:** 9 · **Prerequisites:** [21](21_Market_Risk_Limits.md), [24](24_Risk_Data_Model.md) · **Feeds:** [43](43_Daily_Workflow.md), [44](44_Roles_and_Responsibilities.md)

> **A report exists to cause a decision.** If nobody would act differently on any value the report could contain, it is not a report — it is a record. The distinction determines what belongs in it.

---

## 1. The reporting principle

Every report should answer, for its specific audience:

1. **What is our risk?**
2. **What changed?**
3. **What is outside appetite?**
4. **What do you need to decide?**

**Question 2 is the one most often missing and most often the reason a report is not read.** A risk number in isolation is a fact; a risk number against yesterday's, with the change attributed, is information.

BCBS 239 states the underlying expectations directly: risk reports should be **accurate, comprehensive, clear and useful**, produced with appropriate **frequency**, and **distributed** to the relevant parties.

---

## 2. The report family

| Report | Audience | Frequency | Purpose |
|---|---|---|---|
| **Desk risk report** | Trader, desk head | Daily (intraday view) | Manage the book |
| **Daily market risk report** | Business heads, market risk | Daily | Firm-wide risk position |
| **Limit utilisation and breach report** | Desk heads, risk, escalation chain | Daily | Compliance with appetite |
| **P&L and attribution report** | Desk, product control, risk | Daily | Explain the day |
| **Sensitivities report** | Desk, risk | Daily | Exposure detail |
| **VaR / ES report** | Risk, business heads | Daily | Statistical risk |
| **Stress report** | Risk, senior management, board | Daily/weekly | Crisis exposure |
| **Backtesting report** | Risk, validation, regulator | Daily / quarterly summary | Model performance |
| **PLA report** | Risk, validation, regulator | Quarterly | Model fit |
| **Senior management pack** | ExCo, CRO | Weekly/monthly | Firm risk posture |
| **Board risk report** | Board risk committee | Monthly/quarterly | Appetite, trend, escalations |
| **FRTB capital report** | Capital team, finance, regulator | Daily calc / monthly report | Regulatory capital |
| **Regulatory returns** | Supervisor | Per rulebook | Compliance |

---

## 3. The daily market risk report

### 3.1 Structure

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │  DAILY MARKET RISK REPORT              Business date: 2026-08-24      │
 │                                        Produced: 2026-08-24 21:00     │
 ├───────────────────────────────────────────────────────────────────────┤
 │  1. EXECUTIVE SUMMARY      3 bullets. Exceptions and decisions only.   │
 │  2. EXCEPTIONS             Breaches · backtest exceptions · data       │
 │                            issues · failed valuations. TOP of report.  │
 │  3. P&L                    Today · MTD · YTD, with attribution        │
 │  4. RISK MEASURES          VaR · ES · stress, with day-on-day change   │
 │  5. LIMIT UTILISATION      By desk, highest utilisation first          │
 │  6. SENSITIVITIES          DV01 ladder · CS01 · vega · FX NOP          │
 │  7. CONCENTRATIONS         Top issuers · tenors · countries · factors  │
 │  8. CAPITAL                SA and IMA, with movement                   │
 │  9. DATA QUALITY           Proxies · overrides · stale points          │
 │ 10. APPENDICES             Full detail                                 │
 └───────────────────────────────────────────────────────────────────────┘
```

> **Exceptions go at the top, not in an appendix.** The purpose of the report is the exceptions; everything else is context for them. A report that opens with three pages of aggregate VaR history and buries a limit breach on page eleven has inverted its own purpose.

### 3.2 Worked example

```
 ═══════════════════════════════════════════════════════════════════════
  DAILY MARKET RISK REPORT — GLOBAL MARKETS          2026-08-24
 ═══════════════════════════════════════════════════════════════════════

  EXECUTIVE SUMMARY
  • Firm 99% VaR $18.4m (+$2.1m, +13%): rates vol up; USD Rates added risk
  • ONE limit breach: USD Rates vega, 124% — ACTIVE, remediation by 25 Aug
  • ONE backtest exception: Credit Flow, loss $3.9m vs VaR $3.4m (7th in 12m)

 ───────────────────────────────────────────────────────────────────────
  EXCEPTIONS                                                    Owner
 ───────────────────────────────────────────────────────────────────────
  BREACH   USD Rates · Vega · 124% · ACTIVE                     J. Okafor
           Sold 3m-into-5y straddles pre-CPI. Reduce by 25 Aug EOD.
  BACKTEST Credit Flow · APL −$3.9m vs 99% VaR $3.4m            R. Silva
           Idiosyncratic: single-name gapped 85bp on downgrade.
           7 exceptions in 12m (99%) — AMBER approaching (>12 → SA).
  DATA     3 EM curve points proxied (BRL 20y/25y/30y)          Data Ops
           Broker feed outage. Proxy from 15y + historical slope.
           Expires 26 Aug.
 ───────────────────────────────────────────────────────────────────────
  P&L ($m)                     Today      MTD       YTD
 ───────────────────────────────────────────────────────────────────────
  Rates                        +2.14    +18.7    +142.3
  Credit                       −3.90     +4.2     +88.6
  FX                           +0.85     +6.1     +51.2
  Equity                       +1.22     −2.4     +33.9
  Commodities                  +0.31     +1.8     +12.4
  ─────────────────────────────────────────────────────────────
  TOTAL                        +0.62    +28.4    +328.4
  Unexplained residual         +0.03  (2.4% of gross)     ✓ within threshold

 ───────────────────────────────────────────────────────────────────────
  RISK MEASURES ($m)          Today   Prev    Chg     Limit    Util
 ───────────────────────────────────────────────────────────────────────
  99% 1-day VaR                18.4   16.3   +2.1      25.0     74%
  97.5% ES                     22.7   20.1   +2.6      30.0     76%
  Stress: 2022 rate shock      88.2   79.4   +8.8     120.0     74%
  Stress: 2008 credit          71.5   70.9   +0.6     120.0     60%
  Stress: reverse (to −$150m)   —      —      —         —      d=6.8σ

 ───────────────────────────────────────────────────────────────────────
  LIMIT UTILISATION — top 5 by utilisation
 ───────────────────────────────────────────────────────────────────────
  USD Rates      Vega            124%  🔴 BREACH
  USD Rates      2–10y DV01       89%  🟠
  Credit Flow    CS01 (HY)        86%  🟠
  USD Rates      Total DV01       84%  🟡
  EM Rates       VaR              81%  🟡

 ───────────────────────────────────────────────────────────────────────
  CONCENTRATIONS — top 3 by risk contribution
 ───────────────────────────────────────────────────────────────────────
  Factor   USD 10y zero rate            31% of firm VaR
  Issuer   [single HY name]             $2.8m CS01 · $41m JTD
  Country  Brazil                       $6.1m stressed loss

 ───────────────────────────────────────────────────────────────────────
  CAPITAL ($m)                Today    Prev     Chg
 ───────────────────────────────────────────────────────────────────────
  FRTB SA total               412.6   408.1    +4.5
    SBM (binding: LOW)        318.4   315.2    +3.2
    DRC                        82.1    81.7    +0.4
    RRAO                       12.1    11.2    +0.9
  FRTB IMA (approved desks)   241.8   236.3    +5.5
    IMCC                      168.2   164.9    +3.3
    SES (NMRF)                 41.4    40.8    +0.6
    DRC (IMA)                  32.2    30.6    +1.6
  Desks on SA (C_U)            94.3    94.3      —
 ═══════════════════════════════════════════════════════════════════════
```

### 3.3 What makes this report work

| Feature | Why |
|---|---|
| **Exceptions first, with named owners and dates** | The reader knows immediately what requires action and from whom |
| **Change column on every risk measure** | Answers "what changed?" without arithmetic |
| **Breach classified ACTIVE with a cause** | Distinguishes a control failure from a market move ([21 §8.2](21_Market_Risk_Limits.md)) |
| **Backtest exception in context** | "7 in 12m" against the >12 threshold is decision-relevant; "1 exception" is not |
| **Residual on a gross basis** | Stable denominator ([14 §3.2](14_PnL_and_PnL_Explain.md)) |
| **Binding SBM scenario shown** | "LOW" tells the reader this is a hedge-heavy book ([17 §6.5](17_FRTB_Standardised_Approach.md)) |
| **Data proxies visible, with expiry** | Silence about data quality is not the same as good data quality |
| **Reverse stress as a distance** | 6.8σ is interpretable; a scenario narrative alone is not |
| **Limits sorted by utilisation** | The binding constraints are at the top, always |

---

## 4. Tailoring by audience

| Audience | Wants | Does **not** want |
|---|---|---|
| **Trader** | Real-time position, Greeks by bucket, P&L, limit headroom | Firm aggregates, capital |
| **Desk head** | Desk risk, utilisation, P&L attribution, exceptions | Position-level detail |
| **Business head** | Cross-desk aggregation, concentrations, capital consumption, trend | Greeks |
| **CRO / ExCo** | Firm risk vs appetite, exceptions, stress, emerging concerns | Anything routine |
| **Board** | Appetite adherence, trend, material exceptions, forward-looking concerns | Detail of any kind |
| **Regulator** | Prescribed content, in the prescribed format, on the prescribed date | Anything not asked for |

> **The board report is the hardest to write well.** It must be short enough to be read, specific enough to be actionable, and honest enough to include what is *not* known. **A board report with no uncertainty in it is not a description of a trading business.**

---

## 5. The dashboard

### 5.1 Layout

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │  MARKET RISK DASHBOARD          2026-08-24        [Firm ▾] [Daily ▾] │
 ├──────────────┬──────────────┬──────────────┬─────────────────────────┤
 │  DAILY P&L   │   99% VaR    │  97.5% ES    │   BREACHES              │
 │   +$0.62m    │   $18.4m     │   $22.7m     │      1 🔴               │
 │   ▲ vs prev  │   ▲ +13%     │   ▲ +13%     │   USD Rates vega        │
 ├──────────────┼──────────────┼──────────────┼─────────────────────────┤
 │  MTD P&L     │  WORST STRESS│  FRTB SA     │   BACKTEST (12m)        │
 │   +$28.4m    │   $88.2m     │   $412.6m    │      7 @99%             │
 │              │  2022 rates  │   ▲ +$4.5m   │   limit 12 → SA         │
 ├──────────────┴──────────────┴──────────────┴─────────────────────────┤
 │  RISK TREND (60d)          P&L VS VaR (250d)                         │
 │   ╭─╮      ╭──╮             ·  ·   ·· ·  ·  ·                        │
 │  ─╯ ╰──╮ ╭─╯  ╰──── VaR    ─────────────────── +VaR                  │
 │        ╰─╯                  ·· · ··· ·· ····· ·                      │
 │                            ─────────────────── −VaR                  │
 │                             ✗        ✗    ✗   ← exceptions           │
 ├──────────────────────────────────────────────────────────────────────┤
 │  DESK RANKING — by VaR          │  TOP RISK FACTORS — by contribution │
 │  USD Rates      $8.2m   74% ███ │  USD 10y zero          31% ██████   │
 │  Credit Flow    $4.9m   86% ███ │  USD 5y zero           14% ███      │
 │  EM Rates       $3.1m   81% ███ │  IG credit spread      11% ██       │
 │  FX             $2.4m   52% ██  │  EUR/USD spot           8% ██       │
 │  Equity         $1.8m   41% █   │  S&P 500 spot           6% █        │
 ├──────────────────────────────────────────────────────────────────────┤
 │  TOP MOVERS (day-on-day risk change)                                 │
 │  USD Rates    VaR +$1.9m   ← vega added pre-CPI                      │
 │  EM Rates     VaR +$0.4m   ← BRL curve proxied (data)                │
 │  Equity       VaR −$0.2m   ← index hedge added                       │
 └──────────────────────────────────────────────────────────────────────┘
```

### 5.2 Drilldown hierarchy

```
   FIRM
    └─► DIVISION            Global Markets / Treasury
         └─► BUSINESS       Fixed Income / Equities / FX
              └─► DESK      USD Rates                     ◄── MAR12 unit
                   └─► BOOK
                        └─► RISK FACTOR   USD 10y zero rate
                             └─► POSITION
                                  └─► TRADE
```

**Every number on the dashboard must be drillable to position level.** A figure that cannot be decomposed cannot be investigated, and a risk manager who has to raise a ticket to find out why VaR moved will stop asking.

### 5.3 Design rules that matter

| Rule | Reason |
|---|---|
| **Change, not just level** | The level is context; the change is the news |
| **Exceptions visually dominant** | The eye must land on the breach first |
| **Utilisation, not absolutes, for limits** | 84% is interpretable; $420,000/bp is not, without the limit |
| **Rank by what binds** | Sort by utilisation, not by alphabet or by size |
| **Show data quality** | A dashboard silent about proxies implies data is clean |
| **Attribute the movers** | "VaR +$1.9m" is a fact; "+$1.9m, vega added pre-CPI" is information |
| **One screen for the summary** | Scrolling past the fold is where attention ends |

---

## 6. Regulatory reporting

| Requirement | Frequency | Source |
|---|---|---|
| Standardised approach calculated and reported | **Monthly** (quarterly for non-banking subsidiaries, with approval) | `MAR20.2` |
| SA on supervisory demand | On demand | `MAR20.3` |
| ES computed | **Daily**, bank-wide and per IMA desk | `MAR33.2` |
| DRC under IMA | **Weekly** | `MAR33.20(5)` |
| Desk-level backtesting | **Daily**, assessed over 12 months | `MAR32.16`, `MAR32.19` |
| Bank-wide backtesting | Daily, zones on 250 observations | `MAR32.5`, `MAR32.9` |
| Every backtesting exception documented with an explanation | Per exception | `MAR32.12` |
| RFET | **Quarterly**, 24/4 criterion monitored **monthly** | `MAR31.13` |
| PLA test | **Quarterly**, on 250 days of RTPL/HPL | `MAR32.35`, `MAR33.44` |
| 10% IMA-qualifying capital floor | **Quarterly** | `MAR32.2` |
| One-year backtesting and PLA report for model approval | At application | `MAR32.3` |
| Book designation internal audit | **At least yearly** | `RBC25.13` |

> **Regulatory reporting is a *reproducibility* obligation as much as a submission obligation.** A supervisor asking why a figure moved between two quarters needs the bank to reconstruct both — which requires the bi-temporal storage and version pinning of [24 §10](24_Risk_Data_Model.md). Reports that can be produced but not *re-produced* fail the real test.

---

## 7. Report quality controls

| Control | Requirement |
|---|---|
| **Reconciliation** | Report figures tie to the risk system and to each other |
| **Completeness** | Every in-scope desk present; omissions explicit |
| **Timeliness** | Published by an agreed deadline; late publication is an exception |
| **Accuracy attestation** | A named owner attests |
| **Version control** | Restatements marked as restatements, with the reason |
| **Distribution list** | Reviewed; access appropriate to content |
| **Retention** | Reports retained as issued |
| **Consumption** | **Access logged** — an unread report is a finding |

> **Tracking whether reports are actually opened is unusual and worth doing.** BCBS 239 asks that reports be *useful*; a report nobody reads is evidence that it is not, and either the content or the audience is wrong.

---

## 8. Pseudocode

```
FUNCTION generate_daily_report(business_date, scope, audience):
    d = load_all(business_date, scope)          # from immutable storage

    # --- Exceptions first: they are the point of the report ---
    exceptions = []
    exceptions += [e for e in d.breaches]                  # with classification
    exceptions += [e for e in d.backtest.exceptions_today]
    exceptions += [e for e in d.data_quality.proxies_and_overrides]
    exceptions += [e for e in d.valuations.failed]
    exceptions += ([d.attribution] if d.attribution.threshold_breached else [])

    FOR e IN exceptions:
        ASSERT e.owner IS NOT NULL              # every exception has a name
        ASSERT e.due_date IS NOT NULL           # and a date

    # --- Every measure carries its change ---
    measures = {}
    FOR m IN ["VAR_99","ES_975","STRESS_WORST","SA_CAPITAL","IMA_CAPITAL"]:
        cur  = d.get(m)
        prev = load(business_date - 1_business_day, scope).get(m)
        measures[m] = { "value": cur, "prev": prev,
                        "change": cur - prev,
                        "pct": (cur - prev)/prev if prev else None,
                        "limit": d.limits.get(m),
                        "utilisation": cur/d.limits.get(m) if d.limits.get(m) else None }

    # --- Movers, with attribution, not just deltas ---
    movers = rank_by_abs_change(measures_by_desk(d), n = 5)
    FOR mv IN movers:
        mv.attribution = attribute_risk_change(mv.desk, business_date)
                         # new trades vs market moves vs data changes

    RETURN render(template_for(audience),
                  exceptions = sort_by_severity(exceptions),
                  measures   = measures,
                  limits     = sort_by_utilisation_desc(d.limit_utilisation),
                  movers     = movers,
                  concentrations = top_n_contributions(d, n = 3),
                  data_quality   = d.data_quality.summary())
```

---

## 9. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Exceptions first** | Not in an appendix |
| 2 | **Every exception owned** | Named owner and due date |
| 3 | **Change shown** | Day-on-day movement on every measure |
| 4 | **Movers attributed** | New trades vs market vs data distinguished |
| 5 | **Breaches classified** | Active / passive / technical |
| 6 | **Backtest exceptions in context** | Count against the `MAR32.19` thresholds |
| 7 | **Residual on gross basis** | Not net P&L |
| 8 | **Binding SBM scenario shown** | Which of medium/high/low binds |
| 9 | **Data quality visible** | Proxies, overrides and stale points reported |
| 10 | **Limits sorted by utilisation** | Binding constraints at the top |
| 11 | **Drilldown to position** | Every figure decomposable |
| 12 | **Reconciles to source** | Report ties to the risk system |
| 13 | **Timeliness tracked** | Late publication is an exception |
| 14 | **Attestation** | Named owner |
| 15 | **Restatements marked** | With reason and date |
| 16 | **Reproducibility** | Historical reports regenerable from stored inputs |
| 17 | **Consumption logged** | Unread reports investigated |
| 18 | **Regulatory frequencies met** | §6 table satisfied |

---

## 10. Common implementation errors

| Error | Consequence |
|---|---|
| Exceptions buried in appendices | The reason for the report goes unread |
| Levels without changes | Reader must compute the news themselves |
| Movers listed without attribution | "Why did VaR move?" remains unanswered |
| Breaches unclassified | Control failures indistinguishable from market moves |
| Backtest exception reported as a single event | Loses the trajectory toward the SA threshold |
| Silence about data quality | Implies clean data; proxies invisible |
| Limits sorted by size or name | Binding constraints not surfaced |
| No drilldown | Investigation requires a ticket; questions stop being asked |
| Reports that cannot be regenerated | Supervisory reconstruction requests fail |
| Board pack with no uncertainty | Not a description of a trading business |
| Same content for every audience | Nobody's needs met precisely |
| Distribution never reviewed | Content reaching the wrong people, or nobody |

---

## 11. Limitations

- **Reports compress.** Every aggregate hides a distribution, and the compression is where a concentration disappears — which is why the drilldown is not optional.
- **Daily reporting is backward-looking.** It describes the position taken, not the position about to be taken; pre-trade controls do that ([21 §10](21_Market_Risk_Limits.md)).
- **Dashboards encourage anchoring on what is displayed.** A risk not on the dashboard is a risk not discussed, which makes the choice of what to show a risk decision in itself.
- **Report content is institution-specific.** BCBS 239 sets principles for accuracy, comprehensiveness, clarity, usefulness, frequency and distribution; the specific layouts here are industry practice, not a standard.

---

## 12. Related Concepts

- [21 — Market Risk Limits](21_Market_Risk_Limits.md) · [24 — Risk Data Model](24_Risk_Data_Model.md)
- [27 — Controls and Governance](27_Controls_and_Governance.md) · [43 — The Daily Workflow](43_Daily_Workflow.md)
- [44 — Roles and Responsibilities](44_Roles_and_Responsibilities.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Principles for effective risk data aggregation and risk reporting* (BCBS 239) | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Reporting accuracy, comprehensiveness, clarity, usefulness, frequency, distribution |
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | Calculation and reporting frequencies; `MAR20.2`, `MAR32`, `MAR33.44` |

> **Note on sourcing.** Report layouts and dashboard designs are institution-specific. The structures here are a design reference derived from BCBS 239's principles and common practice, not a regulatory template. The frequencies in §6 **are** regulatory and are cited to paragraph.

*Accessed 25 August 2026.*
