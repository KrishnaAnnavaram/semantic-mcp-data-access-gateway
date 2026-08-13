---
paths:
  - "data/acquisition/**/*.py"
  - "data/**"
---

# Rules for the acquisition stage and everything under data/

These load only when working on the files above.

- **`data/raw/` is immutable.** Once a raw Treasury XML file is written it is
  never edited, patched, reformatted or partially rewritten. `--refresh`
  replaces a whole file with a freshly downloaded one; that is the only way its
  bytes may change. Every downstream artifact is reproducible from these files,
  and their SHA-256 is recorded in `download_manifest.json`.

- **A missing observation is NULL. Never zero.** Not zero, not the previous
  day's rate, not an interpolation, not a column mean. If Treasury published
  nothing, the pipeline says nothing. This is the rule the whole project rests
  on — see CLAUDE.md.

- **An exact `0` is not automatically missing, either.** Short tenors genuinely
  printed 0.00% in 2008-12, 2011, 2015 and 2020-21. Only a leading unbroken run
  of zeros at the very start of a column's history is a placeholder, and that
  judgement is recorded in `treasury.series.placeholder_zero_before` — not
  hardcoded in a script.

- **Never hardcode the field list.** Treasury has added six par maturities since
  1990 and will add more. Parse whatever the feed returns and preserve every
  field under its original name. A fixed list silently discards the next one.

- **Preserve Treasury's terminology exactly.** `BC_1MONTH` stays `BC_1MONTH`.
  Renaming a field to something friendlier is how a discount rate ends up
  labelled as a yield.

- **Never fabricate, and never substitute a source.** No Kaggle, no FRED, no
  Yahoo, no GitHub mirror, no synthetic fill. If `home.treasury.gov` is
  unavailable, the run fails and says so.

- **Flag, do not clean.** Suspicious values are reported for review. Nothing is
  clipped, winsorised, smoothed or dropped as an outlier. Negative rates are
  legitimate — real/TIPS yields are routinely negative.

After any change here, re-run acquisition and confirm the reports still
reconcile:

```bash
python -m acquisition.download_us_treasury
python tools/verify_load.py --self-test
```
