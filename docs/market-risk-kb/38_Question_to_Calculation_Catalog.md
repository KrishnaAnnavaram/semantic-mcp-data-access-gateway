# 38 — Question-to-Calculation Catalog

**Level:** Reference / practical · **Companion to:** [31](31_Master_Calculation_Catalog.md), [37](37_Calculation_Dependency_Graph.md)

> **The practical index to this library.** Someone asks a question; this document says which calculation answers it, what data it needs, what it returns, and — often the most useful column — **what the answer does not tell you**.

**Columns:** *Question* → *Calculation* → *Required data* → *Output* → *The caveat*

---

## 1. Exposure — "how much do we have?"

| Question | Calculation | Required data | Output | The caveat |
|---|---|---|---|---|
| How much do we lose if rates rise 1bp? | **DV01** | Curve, positions | currency/bp | Assumes a **parallel** shift; conceals curve positions |
| Which part of the curve is driving it? | **Key-rate DV01 ladder** | Curve node set, positions | currency/bp per vertex | Depends on interpolation; compare **totals** across firms, not buckets |
| How much for a 1% move, in relative terms? | **Modified duration** | Price, yield, convention | % per 100bp | A percentage — **cannot be summed** across positions |
| Is that sensitivity itself stable? | **Convexity** | 3 revaluations | dimensionless | Only a second-order correction; breaks down at large shocks |
| Our bond is callable — is duration still valid? | **Effective duration** | Pricer + option model | years | It is a statement about the **option model**, not the bond |
| How much credit spread exposure? | **CS01** | Spread curve, positions | currency/bp | Says **nothing** about default; that is JTD |
| How much do we lose if this issuer defaults tomorrow? | **JTD** | Notional, MV, LGD | currency | Cannot be derived by bumping a spread |
| Where on the credit curve? | **Bucketed CS01** | Spread curve at 0.5/1/3/5/10y | currency/bp per tenor | |
| How concentrated is one name? | **Issuer CS01 + JTD** | Issuer mapping | currency/bp, currency | Proxy-mapped issuers show **no idiosyncratic risk** |
| How much currency exposure? | **Net open position** | Positions, spot | currency per ccy | Linear only — misses gamma; check structural exclusions |
| How exposed to an equity move? | **Equity delta / beta-adjusted exposure** | Spot, betas | currency | Beta misses **idiosyncratic** risk, which is usually larger |
| How leveraged is the equity book? | **Gross exposure** | Long + short MVs | currency | Net exposure will look far smaller and mean less |
| How exposed to implied volatility? | **Vega, bucketed by expiry** | Vol surface | currency/vol pt | **Total vega conceals term-structure positions** |
| How exposed to a large move either way? | **Gamma** | Vol surface, spot | delta/unit | Largest **at the money, near expiry** |
| How exposed to the volatility skew? | **Vanna** (+ RR quotes) | Surface by strike | mixed | First-class desk risk in FX |
| What is our commodity curve exposure? | **Delta by delivery month** | Full futures curve | currency | Location and grade basis are **separate** factors |
| How much do we hold against market capacity? | **Concentration: position / ADV** | Volume data | ratio, days | VaR is blind to this by construction |

---

## 2. Loss estimation — "how much could we lose?"

| Question | Calculation | Required data | Output | The caveat |
|---|---|---|---|---|
| What might we lose on a normal bad day? | **99% 1-day VaR** | 250 days factor history, positions | currency | **Not a maximum.** Exceeded ~2.5 days/year by design |
| And how bad are those bad days? | **97.5% ES** | Same scenario set | currency | Sensitive to a single outlier in the tail |
| What if the distribution is wrong? | **Stress testing** | Dated historical shock vectors | currency | **No probability attached** |
| What if 2008 happened again? | **Historical stress replay** | Observed 2008 factor changes | currency | Market structure has changed; instruments may not exist |
| What if rates and credit widen together? | **Multi-factor hypothetical (2022-style)** | Coherent shock vector | currency | Removes the flight-to-quality offset that flatters 2008 |
| What would it take to lose $500m? | **Reverse stress test** | Covariance, sensitivities | shock vector + σ distance | Limited by the portfolio, not by imagination — that is the point |
| What is the worst corner for our options book? | **Spot × vol grid** | Surface, full revaluation | currency matrix | One-dimensional grids miss short-gamma/short-vega corners |
| How much could we lose over 10 days? | **Direct 10-day ES**, or VaR × √10 | Overlapping 10-day changes | currency | **√T understates** under volatility clustering; `MAR33.4(5)` prohibits it for the ES base horizon |
| How much do we lose if the peg breaks? | **Scenario analysis** — *not* VaR | Judgemental shock | currency | A pegged currency's history shows **near-zero** volatility right up to the break |
| What if correlations go to 1? | **Correlation-breakdown stress**; SBM **high** scenario | Correlation matrix | currency | Diversification benefit evaporates exactly when needed |
| What if our hedges stop working? | **SBM low-correlation scenario**; basis stress | ρ, positions | currency | **Low correlation is the binding scenario for hedged books** |

---

## 3. Explanation — "why did that happen?"

| Question | Calculation | Required data | Output | The caveat |
|---|---|---|---|---|
| Why did we make/lose money today? | **P&L attribution** | Sensitivities, market moves, trade activity | currency by component | Decomposition is **path-dependent**; fix and version the order |
| How much of it was just time passing? | **Carry + roll + theta** | Curve, schedules | currency | Negative roll on an inverted curve |
| How much was new trading? | **APL − HPL** | Both P&L measures | currency | |
| Is our risk model missing something? | **HPL − RTPL** (the PLA divergence) | Both measures, 250 days | currency; Spearman + KS | Can also fail for benign systems reasons — hence `MAR32.30` |
| Why did VaR jump with no market move? | **Ghost feature check** | Scenario window entry/exit | date attribution | A large observation left the lookback window |
| Why did VaR jump today? | **Risk change attribution** | Position deltas vs market moves | decomposition | Distinguish new trades from market moves from **data changes** |
| Why does our number differ from the counterparty's? | **Convention reconciliation** | Method, bump size, sign, quantile convention | difference explained | Roughly half of all breaks resolve here |
| Why is our VaR so much lower than the historical figure? | **Parametric vs historical comparison** | Both | ratio | The gap **is** the fat tail — a diagnostic, not an error |
| Why is the residual small but always the same sign? | **Sign-persistence test** | Residual series | run analysis | **Worse than a larger random residual** — something is structurally missing |

---

## 4. Capital — "what does this cost?"

| Question | Calculation | Required data | Output | The caveat |
|---|---|---|---|---|
| What is our standardised capital? | **SBM + DRC + RRAO** | Sensitivities, JTD, notionals, buckets | currency | A **simple sum** — no diversification between the three |
| Which correlation scenario binds? | **All three SBM scenarios** | ρ, γ, WS | scenario + amount | **Which one binds tells you the book's character** |
| What does default risk cost? | **DRC** | Net JTD, risk weights, HBR | currency | No offset across buckets |
| What do our exotics cost? | **RRAO** | Gross notional, classification | currency | Listed/cleared and matched back-to-back are **excluded** |
| What is our internal-models capital? | **IMCC + SES + DRC** | ES, NMRF stress, default model | currency | ρ = 0.5 (IMCC) and ρ = 0.6 (SES) are **different parameters** |
| Why is our NMRF capital so high? | **RFET assessment** | Real price observations by factor | pass/fail per factor | Often a **record-keeping** failure, not genuine illiquidity |
| Would this new product be capital-efficient? | **Pre-trade SA + RFET assessment** | Product terms, factor mapping | currency, pass/fail | Ask the **RFET question at new-product approval**, not a quarter later |
| Can this desk keep using its model? | **Backtesting + PLA** | 250 days VaR, APL, HPL, RTPL | pass/fail, zone | >12 @99% or >30 @97.5% → **standardised approach** |
| Why did capital rise with no new risk? | **Bucket/classification review** | Reference data changes | attribution | A sector or rating change moves the risk weight |
| What is our RWA? | **Capital × 12.5** | Capital | currency | `MAR20.1`, `MAR33.46` |

---

## 5. Limits and appetite — "are we allowed?"

| Question | Calculation | Required data | Output | The caveat |
|---|---|---|---|---|
| Can I do this trade? | **Pre-trade limit check** | Proposed trade, current book, limits | allow/deny | The conversation must happen **before** execution |
| How close are we? | **Limit utilisation** | Measure, limit | % | Sort by utilisation — the binding constraint is what matters |
| Are we within appetite firm-wide? | **Aggregate limit check at every level** | Full hierarchy | status by level | **A parent can breach with no child in breach** |
| Was this breach our fault? | **Breach classification** | Prior/current position and market | active/passive/technical | Conflating them destroys the diagnostic value |
| Is our limit set coherent? | **Sensitivity ⟷ stress cross-check** | DV01 limit × stress shock vs stress limit | consistency | A $500k/bp DV01 limit implies $100m at 200bp |
| Where should we allocate more limit? | **Component contribution to risk** | Σ, positions | % of total risk | **Component**, not marginal — only CCR sums to the total |

---

## 6. Model quality — "should we believe this?"

| Question | Calculation | Required data | Output | The caveat |
|---|---|---|---|---|
| Is our VaR model calibrated correctly? | **Backtesting exception count** | VaR, APL, HPL, 250 days | count vs expectation | **Zero exceptions is also a finding** |
| Are the exceptions clustered? | **Christoffersen independence test** | Exception series | statistic | Three consecutive is worse than three spread out |
| Does the model describe this portfolio? | **PLA: Spearman + KS** | 250 days RTPL, HPL | metrics, zone | Green needs **both**; red triggers on **either** |
| Is our pricing model right? | **Benchmark / challenger model** | Independent implementation | divergence | The **gap is the finding**, regardless of which is right |
| Is the volatility surface valid? | **Calendar + butterfly arbitrage tests** | Fitted surface | pass/fail | Arbitrage-free ≠ correct |
| Is the curve build sound? | **Input repricing + forward sanity** | Curve, inputs | error, forward plot | **Always plot the implied forwards** |
| Are our sensitivities right? | **Analytic vs bumped comparison** | Both methods | difference | Also test bump-size stability |
| Is the ladder complete? | **`Σ KRD01 = parallel DV01`** | Both | difference | Failure means a gap or overlap in the tents |
| Is the covariance matrix valid? | **PSD check / Cholesky** | Σ | pass/fail | A failure means a portfolio with negative variance |
| Is our data clean? | **Staleness, outlier, completeness checks** | Feeds vs history | exception list | **A stale price makes risk look better** |

---

## 7. Governance and reporting — "what do I tell them?"

| Question | Calculation / artefact | Output | The caveat |
|---|---|---|---|
| What should the board see? | Appetite adherence, trend, material exceptions, **and what we don't know** | Board pack | A board report with no uncertainty is not describing a trading business |
| What changed since yesterday? | Risk change with **attribution** | Movers table | A delta without attribution is not information |
| Which desks are riskiest? | Desk ranking by VaR **and** utilisation | Ranking | Absolute size and constraint tightness are different questions |
| What is concentrated? | Top-N by risk contribution, issuer, factor, country | Concentration report | Aggregates hide distributions — drilldown is not optional |
| Are we ready for the supervisor? | Reproducibility test on a historical date | Match / mismatch | Reports that can be produced but not *re-produced* fail the real test |
| What are our data quality issues? | Proxy, override and stale-point register | Exception list | **Silence about data quality implies clean data** |

---

## 8. Instrument-specific questions

| Question | Calculation | The caveat |
|---|---|---|
| Why does our FRN show almost no rate risk? | **DV01 to next reset only** | Correct — but it has **full CS01** |
| Why did our "hedged" bond/CDS package lose money? | **CDS-bond basis** | Basis positions are large in notional relative to apparent risk |
| Why did our bond future hedge underperform? | **CTD switch analysis** | `DV01_CTD/CF` is unstable near the switch |
| Why is our MBS duration falling as rates fall? | **Effective duration + prepayment model** | Negative convexity; you must sell duration into a rally |
| Why did our forward move with no spot move? | **Rate leg DV01s** (and dividend for equity) | A forward is not one risk |
| Why did our swap book gain XCCY basis risk? | **CSA discount-curve selection** | A foreign-currency CSA introduces it |
| Why did our equity forward jump? | **Dividend sensitivity** | Dividends are forecast, not contracted |
| Why did our short position cost more? | **Borrow / repo rate sensitivity** | Hard-to-borrow names reprice every derivative on them |
| Why did our commodity index lose in a flat market? | **Roll yield** | Contango costs money on every roll |
| Why did our barrier hedge fail? | **Full revaluation near the barrier** | Delta and gamma are **discontinuous** there |
| Why is our convertible behaving like equity? | **Cross-gamma (equity × credit)** | A distressed convertible is nearly all equity |
| Why did our power position not net? | **Peak vs off-peak as distinct commodities** | `MAR21.84` treats each delivery interval separately |

---

## 9. The questions with no calculation

**Some of the most important questions in market risk are not answered by any metric.** Recording them here is deliberate.

| Question | Why no calculation answers it | What to do instead |
|---|---|---|
| What are we exposed to that we have not modelled? | An unmapped factor has no representation by construction | New-product approval; factor mapping review; unexplained P&L trend |
| What happens if the exchange cancels our trades? | No price series contains that event (LME nickel, March 2022) | Scenario analysis and governance |
| What happens if a peg breaks? | History shows near-zero volatility until the moment it doesn't | Scenario analysis, never historical simulation |
| Is our proxy mapping still appropriate? | The proxy performs fine until the issuer moves idiosyncratically | Periodic mapping review; NMRF assessment |
| Would our hedges be executable in a crisis? | Historical volumes reflect normal-size trading | Concentration analysis; liquidity horizons; days-to-liquidate |
| Are our deposit behaviour assumptions right? | Behaviour is an assumption, not a contract term | Back-testing NMD behaviour; supervisory challenge |
| Is the model still describing this desk's strategy? | Statistics compare the model to itself | Conceptual soundness review ([26 §2](26_Model_Risk_and_Validation.md)) |

> **This table is the practical form of [01 §13](01_Market_Risk_Fundamentals.md)'s tenth question — *what do we not know?* — and of the "knowing where the silence is" point in [35](35_Beginner_to_Expert_Learning_Path.md).** A risk function that can only answer questions that have a metric is answering the easy half.

---

## 10. Question → document index

| If the question is about… | Start at |
|---|---|
| What market risk *is* | [01](01_Market_Risk_Fundamentals.md) |
| How risks classify | [01A](01A_Master_Market_Risk_Taxonomy.md) |
| A specific instrument | [02](02_Financial_Instruments.md) |
| Valuation | [03](03_Pricing_Fundamentals.md), [23](23_Market_Data_and_Curves.md) |
| Rate sensitivity | [04](04_Interest_Rate_Risk.md) |
| Credit spread | [05](05_Credit_Spread_Risk.md) |
| FX | [06](06_FX_Risk.md) |
| Equity | [07](07_Equity_Risk.md) |
| Commodity | [08](08_Commodity_Risk.md) |
| Options | [09](09_Options_and_Greeks.md) |
| Portfolio statistics | [10](10_Portfolio_Risk_Mathematics.md) |
| VaR | [11](11_VaR.md) |
| Expected Shortfall | [12](12_Expected_Shortfall.md) |
| Stress | [13](13_Stress_Testing.md) |
| P&L | [14](14_PnL_and_PnL_Explain.md) |
| Backtesting / PLA | [15](15_Backtesting.md) |
| FRTB generally | [16](16_FRTB_Overview.md) |
| SA capital | [17](17_FRTB_Standardised_Approach.md) |
| IMA capital | [18](18_FRTB_Internal_Models_Approach.md) |
| Default risk | [19](19_Default_Risk_and_DRC.md) |
| Modellability | [20](20_NMRF_and_Modellability.md) |
| Book boundary / IRRBB | [20A](20A_Trading_Book_Boundary_and_IRRBB.md) |
| Limits | [21](21_Market_Risk_Limits.md) |
| CVA / counterparty / SIMM | [22](22_Counterparty_CVA_and_SIMM.md) |
| Data and curves | [23](23_Market_Data_and_Curves.md) |
| Data model | [24](24_Risk_Data_Model.md) |
| Architecture | [25](25_Risk_System_Architecture.md) |
| Model validation | [26](26_Model_Risk_and_Validation.md) |
| Controls | [27](27_Controls_and_Governance.md) |
| Reporting | [28](28_Reporting_and_Dashboards.md) |
| Regulatory status | [29](29_Regulatory_Framework.md) |
| A worked number | [30](30_Worked_Examples.md) |
| A formula | [32](32_Master_Formula_Handbook.md) |
| A term | [34](34_Glossary.md) |
| The daily process | [43](43_Daily_Workflow.md) |
| Who does what | [44](44_Roles_and_Responsibilities.md) |

---

## Related Concepts

- [31 — Master Calculation Catalog](31_Master_Calculation_Catalog.md) · [37 — Calculation Dependency Graph](37_Calculation_Dependency_Graph.md)
- [39 — Agent Knowledge Model](39_Agent_Knowledge_Model.md) — the same mappings, formalised for automated reasoning
- [35 — Learning Path](35_Beginner_to_Expert_Learning_Path.md)

---

*Accessed 25 August 2026.*
