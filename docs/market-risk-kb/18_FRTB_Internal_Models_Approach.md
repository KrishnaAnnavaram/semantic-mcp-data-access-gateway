# 18 — FRTB Internal Models Approach

**Level:** 11 · **Prerequisites:** [12](12_Expected_Shortfall.md), [15](15_Backtesting.md), [16](16_FRTB_Overview.md) · **Feeds:** [19](19_Default_Risk_and_DRC.md), [20](20_NMRF_and_Modellability.md)

---

## 1. The idea, and the price of admission

The IMA lets a bank use **its own model** to set market risk capital — which is worth a great deal, because a model that genuinely describes a hedged portfolio will produce a lower number than the SA's prescribed correlations ever can.

**The price is continuous, granular, evidenced proof that the model works.** Under the pre-FRTB framework model approval was firm-wide and effectively permanent. Under FRTB it is granted **per trading desk**, tested **quarterly**, and withdrawn automatically on defined failures.

```
   Desk definition (MAR12)
        │
        ▼
   Supervisory approval  ──── requires a ONE-YEAR backtesting and PLA report (MAR32.3)
        │
        ▼
   ┌────────────────────── QUARTERLY RE-ASSESSMENT ──────────────────────┐
   │                                                                     │
   │   RFET          →  factors that fail become NMRFs → SES             │
   │   Backtesting   →  >12 @99% or >30 @97.5%  →  desk moves to SA      │
   │   PLA test      →  RED → SA;  AMBER → capital surcharge             │
   │   10% floor     →  IMA-qualifying desks must carry ≥10% of capital  │
   │                                                                     │
   └─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Desk-level eligibility

### 2.1 What a trading desk is (`MAR12`)

The trading desk is a **regulatory object**, not an org chart convenience. It must have a single head, a defined business strategy, a documented risk management structure and clear reporting lines. **Approval attaches to the desk**, so a bank cannot obtain one approval and shelter everything beneath it.

### 2.2 The 10% floor (`MAR32.2`)

> For a bank to **remain eligible** to use the IMA, a minimum of **10% of the bank's aggregated market risk capital requirement** must be based on positions held in trading desks that qualify for internal models by satisfying backtesting and the PLA test.

Assessed **quarterly**, when calculating aggregate capital per `MAR33.43`.

This is an anti-cherry-picking provision. Without it a bank could seek approval for one small, well-behaved desk, describe itself as an internal-models firm, and run everything material on the SA.

### 2.3 The two-stage rule for default risk

Footnote 1 to `MAR32.19`: desks with exposure to issuer default risk must pass a **two-stage approval process**:

1. The **market risk model** must pass backtesting and PLA.
2. **Conditional on that approval**, the desk may then apply separately for approval to model default risk.

**Desks that fail either test must be capitalised under the standardised approach.**

---

## 3. Expected Shortfall — the core measure

| Parameter | Value | Source |
|---|---|---|
| Confidence | **97.5th percentile, one-tailed** | `MAR33.3` |
| Frequency | **Daily**, bank-wide *and* per IMA desk | `MAR33.2` |
| Calibration | To a **period of stress** | `MAR33.5` |
| Base horizon | **10 days** | `MAR33.4(2)` |
| Model type | **Not prescribed** — historical simulation, Monte Carlo, or other appropriate analytical methods | `MAR33.12` |

`MAR33.12` conditions that freedom: any model is permitted *"provided that each model used captures all the material risks run by the bank, as confirmed through profit and loss (P&L) attribution (PLA) tests and backtesting."*

Full treatment of the ES measure, the liquidity-horizon scaling formula and the stress calibration: [12 §8](12_Expected_Shortfall.md).

### 3.1 Options modelling requirements (`MAR33.12`)

Explicit and worth quoting, because they are frequently under-implemented:

1. Models **must capture the non-linear price characteristics** of options positions.
2. Risk measurement systems must have a set of risk factors that captures the volatilities of the rates and prices underlying option positions — i.e. **vega risk**.
3. Banks with relatively large and/or complex options portfolios **must have detailed specifications of the relevant volatilities**, and must model the volatility surface **across both strike price and vertex (tenor)**.

---

## 4. Liquidity horizons

### 4.1 Why they exist

The pre-FRTB framework assumed every position could be exited in ten days. In 2008 much of the trading book could not be exited at all. Liquidity horizons internalise that: **the horizon over which a risk is measured should be the horizon over which it can actually be closed.**

### 4.2 The five horizons (`MAR33.4`, Table 1)

| j | LH_j (days) |
|---|---|
| 1 | **10** |
| 2 | **20** |
| 3 | **40** |
| 4 | **60** |
| 5 | **120** |

### 4.3 Assignment by risk factor category (`MAR33.12`, Table 2)

| Risk factor category | LH |
|---|---|
| Interest rate: **specified currencies** — EUR, USD, GBP, AUD, JPY, SEK, CAD and the bank's domestic currency | **10** |
| Interest rate: unspecified currencies | 20 |
| Interest rate: **volatility** | 60 |
| Interest rate: other types | 60 |
| Credit spread: sovereign (IG) | 20 |
| Credit spread: sovereign (HY) | 40 |
| Credit spread: corporate (IG) | 40 |
| Credit spread: corporate (HY) | 60 |
| Credit spread: **volatility** | **120** |
| Credit spread: other types | **120** |
| Equity price (large cap) | **10** |
| Equity price (small cap) | 20 |
| Equity price (large cap): **volatility** | 20 |
| Equity price (small cap): **volatility** | 60 |
| Equity: other types | 60 |
| FX rate: **specified currency pairs** | **10** |
| FX rate: other currency pairs | 20 |
| FX: **volatility** | 40 |
| FX: other types | 40 |
| Energy and carbon emissions trading price | 20 |
| Precious metals and non-ferrous metals price | 20 |
| Other commodities price | 60 |
| Energy and carbon emissions trading price: **volatility** | 60 |
| Precious metals and non-ferrous metals price: **volatility** | 60 |
| Other commodities price: **volatility** | **120** |
| Commodity: other types | **120** |

**The specified FX pair list for liquidity horizons** (footnote 1 to Table 2) is the `MAR21.88` SBM list **plus EUR/JPY, EUR/GBP, EUR/CHF and JPY/AUD**, together with first-order crosses. **The two lists are not identical** — using the SBM list here is a real and easily-made error.

### 4.4 Two structural patterns

1. **Volatility always carries a longer horizon than the price it is the volatility of.** Vol markets are thinner; unwinding vega takes longer than unwinding delta.
2. **"Other types" is always at or near the maximum.** Anything the framework cannot categorise is treated as the least liquid thing in its class.

### 4.5 The horizon is a floor, not a ceiling (`MAR33.12(3)`)

On a **desk-by-desk** basis, *n* may be increased relative to Table 2 — the table value is a **floor**. Where increased, the new horizon must be **20, 40, 60 or 120 days**, the rationale must be documented, and it is subject to supervisory approval. Liquidity horizons should be **capped at the maturity of the related instrument**.

The mapping of risk factors to categories must be (`MAR33.12(2)`): set out in writing, validated by the bank's risk management, made available to supervisors, and **subject to internal audit**.

---

## 5. Capital for modellable risk factors — IMCC

### 5.1 The two ES calculations (`MAR33.13`–`MAR33.14`)

**Unconstrained** — `IMCC(C)`: the bank-wide ES with **no supervisory constraints on cross-risk-class correlations**. This is the bank's own view of its diversification.

**Constrained** — `IMCC(C_i)`: a series of **partial ES** requirements, computed for each of the **five broad regulatory risk classes** — interest rate, equity, foreign exchange, commodity and credit spread — with all other risk factors held constant. These partial, non-diversifiable values are then **summed**.

### 5.2 The weighted average (`MAR33.15`)

```
                                              B
   IMCC  =  ρ · IMCC(C)   +   (1 − ρ) ·  [   Σ   IMCC(C_i)  ]
                                             i=1
```

| Term | Value |
|---|---|
| **ρ** | **0.5** — *"the relative weight assigned to the firm's internal model"* |
| **B** | The broad regulatory risk classes of `MAR33.14` |

`MAR33.15(1)`: the stress period used in the risk-class-level `ES_{R,S,i}` **must be the same** as that used for the portfolio-wide `ES_{R,S}`.

> **ρ = 0.5 means the framework takes the bank's cross-asset diversification claim at exactly half face value.** Half the capital is computed as the bank's model says; half as though no cross-class diversification existed at all. This is a deliberate, quantified expression of scepticism about the correlations that historically converge in a crisis.

---

## 6. Capital for non-modellable risk factors — SES

Summarised here; full treatment in [20](20_NMRF_and_Modellability.md).

### 6.1 The stress scenario (`MAR33.16`)

Capital for each NMRF is determined using a **stress scenario calibrated to be at least as prudent as the ES calibration used for modelled risks** — that is, a loss calibrated to a **97.5% confidence threshold over a period of stress**. The bank must determine a **common 12-month period of stress across all NMRFs in the same risk class**.

**Liquidity horizon (`MAR33.16(1)`):** the greater of the factor's `MAR33.12` horizon **and 20 days**. The supervisor may require higher.

**Idiosyncratic concessions (`MAR33.16(2)`):** for NMRFs arising from idiosyncratic credit spread risk, and separately for idiosyncratic equity risk (spot, futures and forward prices, equity repo rates, dividends and volatilities), a **common 12-month stress period** may be applied, and a **zero correlation assumption** may be used when aggregating gains and losses — provided the bank demonstrates to its supervisor that this is appropriate.

**The backstop (`MAR33.16(3)`):** if a bank cannot provide a stress scenario acceptable to the supervisor, **it must use the maximum possible loss**.

### 6.2 The aggregation formula (`MAR33.17`)

```
              ┌                                                                    ┐ ½
              │   I               J                ⎛     K          ⎞²      K      │
   SES  =     │   Σ ISES²_NM,i +  Σ ISES²_NM,j  +  ⎜ ρ · Σ SES_NM,k ⎟  + (1−ρ²)·Σ SES²_NM,k │
              │  i=1             j=1              ⎝    k=1          ⎠     k=1      │
              └                                                                    ┘
```

| Term | Meaning |
|---|---|
| `ISES_NM,i` | Stress scenario capital for idiosyncratic **credit spread** NMRF *i*, from the *I* factors aggregated with **zero correlation** |
| `ISES_NM,j` | Stress scenario capital for idiosyncratic **equity** NMRF *j*, from the *J* factors aggregated with zero correlation |
| `SES_NM,k` | Stress scenario capital for the remaining *K* non-modellable factors |
| **ρ** | **0.6** |

**Read the structure.** The two idiosyncratic groups enter as sums of *squares* — full diversification, because idiosyncratic risks genuinely are independent. The remaining factors enter through the `ρ = 0.6` term, which sits between full diversification and none. **There is no scenario in which NMRFs receive the same offset as modellable factors.** That asymmetry is the point of the regime.

---

## 7. Default Risk Capital under the IMA

The IMA DRC is a **separate model** from the ES model, with its own requirements (`MAR33.18`–`MAR33.39`).

| Requirement | Specification | Source |
|---|---|---|
| Model type | **VaR model** | `MAR33.20` |
| Confidence and horizon | **One-tail, 99.9th percentile, one-year time horizon** | `MAR33.20(5)` |
| Frequency | **Weekly** | `MAR33.20(5)` |
| Systematic factors | Default simulation model with **two types** of systematic risk factor | `MAR33.20(1)` |
| Correlation basis | Credit spreads **or** listed equity prices | `MAR33.20(2)` |
| Correlation data | **At least 10 years**, including a period of stress, at a **one-year liquidity horizon** | `MAR33.20(2)`, `MAR33.27(3)`–`(4)` |
| Equity sub-portfolios | Discretion to apply a **minimum 60-day** liquidity horizon | `MAR33.20(4)` |
| Positions | **Constant** over the one-year horizon (or 60 days for designated equity sub-portfolios) | `MAR33.22` |
| Capital measure | **Greater of** the 12-week average and the most recent measure | `MAR33.21`/`MAR33.22` |
| PD floor | **0.03%** | `MAR33.24(2)` |
| Market-implied PDs | **Not acceptable** unless corrected to an objective PD | `MAR33.24(1)`, footnote 3 |
| Equity default | Modelled as the **equity price dropping to zero** | `MAR33.21(2)` |
| Scope | Sovereign exposures (**including domestic-currency**), equity positions and **defaulted debt** must be included | `MAR33.21(1)` |

### 7.1 The netting and basis rules (`MAR33.25`–`MAR33.26`)

- Netting of long and short exposures to the **same obligor** may be reflected; where exposures span different instruments, the netting **must account for different losses in different instruments** (e.g. differences in seniority).
- **Basis risk between long and short exposures of different obligors must be modelled explicitly.** Offsetting across different obligors is recognised only **through the modelling of defaults**.
- **Pre-netting of positions before model input, other than same-obligor netting, is not allowed.**

### 7.2 The anti-gaming provision (`MAR33.27(1)`)

> Correlations *"must be based on objective data and not chosen in an opportunistic way where a higher correlation is used for portfolios with a mix of long and short positions and a low correlation used for portfolios with long only exposures."*

This is unusually direct drafting, and it names precisely the behaviour it forbids: selecting the correlation that minimises capital for whichever portfolio shape the desk happens to hold.

---

## 8. Capital aggregation

### 8.1 The non-DRC IMA charge (`MAR33.41`)

```
   C_A  =  max(  IMCC_{t−1}  +  SES_{t−1}  ,
                 m_c · IMCC_avg60  +  SES_avg60  )
```

The greater of the **most recent observation** and a **multiplied 60-day weighted average**. This floor-plus-average structure prevents a bank from benefiting from a single quiet day, while also ensuring a sharp deterioration is recognised immediately.

Applies to desks that pass backtesting **and** are in the PLA green **or amber** zone.

### 8.2 The multiplier (`MAR33.42`)

**`m_c` is fixed at 1.5** unless the supervisor sets it higher, to reflect:

- a **qualitative add-on**, where the bank does not meet the `MAR30.5`–`MAR30.16` qualitative standards; and/or
- a **backtesting add-on**, ranging from **0 to 0.5**, based on backtesting the bank's daily VaR at the 99th percentile on current observations across the full set of risk factors (VaR_FC).

The add-on is determined from **the maximum of the exceptions generated against actual P&L and hypothetical P&L**, producing the `MAR32.9` Table 1 schedule of 1.50 → 2.00. See [15 §4.3](15_Backtesting.md).

### 8.3 The total (`MAR33.43`)

```
   IMA_{G,A}  =  C_A  +  DRC

   Total market risk capital
        =  max[  IMA_{G,A} + capital surcharge  +  C_U  ,
                 SA_all-desks  ]      ← subject to the MAR33.43 formulation
```

where `C_U` (`MAR33.40`) is the SA capital for trading desks that are **out of scope for model approval or deemed ineligible** to use an internal model.

**If at least one eligible trading desk is in the PLA amber zone, a capital surcharge is added**, and `MAR33.43` limits its impact by formula.

### 8.4 RWA

`MAR33.46`: risk-weighted assets for market risk under the IMA are the capital requirement **multiplied by 12.5**.

---

## 9. The quarterly cycle (`MAR33.44`)

The following are applied and updated on a **quarterly** basis:

- the **risk factor eligibility test**
- the **PLA test**
- **trading desk-level backtesting**
- the **stressed period**
- the **reduced set of risk factors** (`ES_{R,C}` and `ES_{R,S}`)

*"The reference dates to perform the tests and to update the stress period and selection of the reduced set of risk factors should be consistent."* Banks must reflect the updates in capital **in a timely manner**.

The 60-day averages (IMCC, SES) and the 12-week average (DRC) **only have to be calculated at quarter end** for the purpose of the capital requirement.

`MAR32.7`: the scope of the portfolio subject to bank-wide backtesting is likewise updated quarterly.

---

## 10. Qualitative standards (`MAR30`)

The IMA is not only a quantitative permission. `MAR30.5`–`MAR30.16` impose qualitative standards, and failure to meet them feeds the multiplier add-on.

| Requirement | Substance |
|---|---|
| **Independent risk control unit** | `MAR30.8`: a distinct unit, **separate from the unit that designs and implements the internal model** |
| **Board and senior management involvement** | `MAR30.12`: actively involved in the risk control process |
| **Model validation standards** | `MAR30`: initial and ongoing validation |
| **External validation** | `MAR30`: independent review |
| **Stress testing programme** | `MAR30`: a rigorous programme, run regularly |
| **Documentation** | Policies, controls, and the model itself |

> **The separation requirement in `MAR30.8` is the structural one.** A model validated by the people who built it is not validated. See [26](26_Model_Risk_and_Validation.md).

---

## 11. IMA versus SA — the comparison

| | **Standardised Approach** | **Internal Models Approach** |
|---|---|---|
| Who computes it | **Every bank** | Approved desks only |
| Approval | None needed | Per desk, supervisory |
| Risk measure | Sensitivities + prescribed weights | **97.5% ES**, stress-calibrated |
| Correlations | **Prescribed**, three scenarios | Bank's own, **constrained cross-class at ρ = 0.5** |
| Liquidity | Embedded in vega LH per class | **Explicit 10–120 day horizons** by factor |
| Illiquid factors | Not distinguished | **NMRF → SES** |
| Default risk | DRC, prescribed weights | DRC VaR, **99.9% / 1 year / weekly** |
| Residual risks | **RRAO** | Not separately charged (but RRAO still applies as an SA component) |
| Multiplier | None | **m_c = 1.5** + add-on 0–0.5 |
| Ongoing tests | None | Backtesting, PLA, RFET — **quarterly** |
| Failure consequence | n/a | **Desk moves to the SA** |
| Typical capital outcome | Higher for well-hedged books | Lower **if** the model genuinely describes the book |
| Reporting | **Monthly** (`MAR20.2`) | Daily ES (`MAR33.2`) |

---

## 12. Pseudocode

```
FUNCTION ima_capital(bank, quarter):
    eligible, ineligible = [], []

    FOR desk IN bank.desks:
        bt  = desk_backtest(desk)                 # MAR32.18-19
        pla = pla_test(desk.rtpl, desk.hpl)       # MAR32.42

        IF bt.exc_99 > 12 OR bt.exc_975 > 30 OR pla.zone == "RED":
            ineligible.append(desk)
        ELSE:
            eligible.append((desk, pla.zone))

    # MAR32.2 — the 10% floor, assessed quarterly
    IF capital_share(eligible) < 0.10:
        RETURN "IMA INELIGIBLE bank-wide — SA applies to everything"

    # --- modellable factors ---
    imcc_unconstrained = es_97_5(eligible, constrain_cross_class = FALSE)
    imcc_constrained   = sum( es_97_5(eligible, risk_class = rc)
                              for rc in FIVE_BROAD_RISK_CLASSES )
    rho_imcc = 0.5                                              # MAR33.15(2)
    IMCC = rho_imcc*imcc_unconstrained + (1-rho_imcc)*imcc_constrained

    # --- non-modellable factors ---
    SES = ses_aggregate(nmrfs(eligible), rho = 0.6)             # MAR33.17

    # --- MAR33.41 ---
    m_c = 1.5 + backtest_addon(bank) + qualitative_addon(bank)  # MAR33.42
    C_A = max( IMCC_latest + SES_latest,
               m_c * avg60(IMCC) + avg60(SES) )

    # --- DRC: requires SECOND-STAGE approval (MAR32.19 fn 1) ---
    DRC = drc_ima(eligible_for_default_modelling(eligible))

    C_U = sa_capital(ineligible + bank.out_of_scope_desks)      # MAR33.40

    surcharge = pla_amber_surcharge(eligible)                   # MAR33.43

    RETURN { "IMA_GA": C_A + DRC, "C_U": C_U, "surcharge": surcharge,
             "RWA": (C_A + DRC + C_U + surcharge) * 12.5 }      # MAR33.46


FUNCTION ses_aggregate(nmrfs, rho = 0.6):
    idio_credit = [n for n in nmrfs if n.is_idiosyncratic_credit_spread]
    idio_equity = [n for n in nmrfs if n.is_idiosyncratic_equity]
    rest        = [n for n in nmrfs if n not in idio_credit + idio_equity]

    term1 = sum(n.ses**2 for n in idio_credit)      # zero correlation
    term2 = sum(n.ses**2 for n in idio_equity)      # zero correlation
    s     = sum(n.ses for n in rest)
    term3 = (rho * s)**2 + (1 - rho**2) * sum(n.ses**2 for n in rest)

    RETURN sqrt(term1 + term2 + term3)              # MAR33.17
```

---

## 13. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Desk definitions** | Meet `MAR12`; head, strategy, structure, reporting lines documented |
| 2 | **10% floor** | Computed quarterly (`MAR32.2`) |
| 3 | **ES confidence** | 97.5th percentile, one-tailed (`MAR33.3`) |
| 4 | **ES frequency** | Daily, bank-wide **and** per desk (`MAR33.2`) |
| 5 | **No shorter-horizon scaling** | `ES_T` computed directly at T = 10 days (`MAR33.4(5)`) |
| 6 | **Nested subsets** | `Q(pᵢ,j) ⊆ Q(pᵢ,j−1)` verified |
| 7 | **LH assignment** | Documented, validated, **audited** (`MAR33.12(2)`) |
| 8 | **LH increases** | Only to 20/40/60/120; documented; supervisor-approved |
| 9 | **LH capped at maturity** | Verified per instrument |
| 10 | **Specified FX list** | `MAR33.12` list used for horizons, **not** the `MAR21.88` SBM list |
| 11 | **IMCC ρ** | 0.5 (`MAR33.15(2)`) |
| 12 | **Same stress period** | Risk-class ES uses the portfolio-wide stress period (`MAR33.15(1)`) |
| 13 | **SES ρ** | 0.6 (`MAR33.17(4)`) |
| 14 | **NMRF LH floor** | max(Table 2 horizon, **20 days**) (`MAR33.16(1)`) |
| 15 | **Idiosyncratic zero-correlation** | Demonstrated to the supervisor, not assumed |
| 16 | **DRC parameters** | 99.9%, one year, **weekly**, PD floor 0.03% |
| 17 | **No market-implied PDs** | Unless corrected to objective PDs |
| 18 | **No pre-netting** | Beyond same-obligor netting (`MAR33.26`) |
| 19 | **Correlation opportunism** | Documented method, not portfolio-shape-dependent (`MAR33.27(1)`) |
| 20 | **Multiplier** | 1.5 base, add-on 0–0.5 |
| 21 | **Independent risk control unit** | Separate from model design and implementation (`MAR30.8`) |
| 22 | **Quarterly cycle** | RFET, PLA, backtesting, stress period, reduced set — consistent reference dates |

---

## 14. Common implementation errors

| Error | Consequence |
|---|---|
| Firm-wide model approval assumed | Desk-level failures invisible |
| Scaling a 1-day ES to 10 days | Contradicts `MAR33.4(5)` |
| Treating `Q(pᵢ,j)` as exactly-LH_j factors | Nesting broken; ES materially wrong |
| SBM specified-FX list used for liquidity horizons | Wrong horizon on EUR/JPY, EUR/GBP, EUR/CHF, JPY/AUD |
| IMCC ρ and SES ρ confused | **0.5 and 0.6 are different parameters for different formulas** |
| Full diversification across NMRFs | Contradicts `MAR33.17` |
| NMRF horizon below 20 days | Contradicts `MAR33.16(1)` |
| DRC at 99% or daily | Wrong parameters — it is 99.9%, weekly, one-year |
| Market-implied PDs used raw | Explicitly not acceptable |
| Pre-netting across obligors | Explicitly not allowed |
| Missing the DRC second-stage approval | Desk models default risk without permission |
| Applying only the most recent IMCC + SES | Ignores the `MAR33.41` 60-day average leg |
| Validation by the model builders | Contradicts `MAR30.8` |

---

## 15. Limitations

1. **The IMA is expensive to run and expensive to lose.** Building the data infrastructure for the RFET alone is a major undertaking, and a desk that fails backtesting moves to the SA with a step change in capital.
2. **Capital becomes volatile.** Quarterly re-assessment means a desk's capital treatment can change discontinuously.
3. **The RFET is a data problem, not a modelling problem.** Passing it depends on real price observations the bank can evidence — which is a sourcing and record-keeping capability.
4. **Cross-class diversification is halved by construction** (ρ = 0.5), so a genuinely well-diversified multi-asset book cannot obtain full recognition.
5. **The ES model is validated only indirectly**, through VaR backtesting and PLA ([12 §9.1](12_Expected_Shortfall.md)).
6. **Jurisdictional divergence is material.** The UK has deferred the market risk IMA to **1 January 2028**, a year after the rest of its Basel 3.1 package, and consulted separately on IMA adjustments in CP9/26. See [29](29_Regulatory_Framework.md).

---

## 16. Related Concepts

- [12 — Expected Shortfall](12_Expected_Shortfall.md) · [15 — Backtesting](15_Backtesting.md)
- [16 — FRTB Overview](16_FRTB_Overview.md) · [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md)
- [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md) · [20 — NMRF and Modellability](20_NMRF_and_Modellability.md)
- [26 — Model Risk and Validation](26_Model_Risk_and_Validation.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR30`–`MAR33` in full; `MAR12`, `MAR32` |
| BCBS | *Explanatory note on the minimum capital requirements for market risk* | Jan 2019 | https://www.bis.org/bcbs/publ/d457_note.pdf | Rationale for ES, liquidity horizons, NMRF regime |
| Bank of England / PRA | CP9/26 – Basel 3.1: Adjustments to the IMA for market risk | Jun 2026 | https://www.bankofengland.co.uk/prudential-regulation/publication/2026/june/basel-3-1-adjustments-to-the-internal-model-approach-for-market-risk-consultation-paper | UK IMA timing and adjustments |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR30–MAR33 text |

*Accessed 25 August 2026.*
