---
name: free-fundamentals-cannot-support-a-backtest
description: yfinance gives 5 years of restated fundamentals with no reporting lag and no ratios - four compounding biases, all upward.
metadata:
  type: finding
---
Checked directly before attempting any fundamental strategy.

    income_stmt            5 annual periods (2021-2025)
    quarterly_income_stmt  5 quarters
    trailingPE, priceToBook, returnOnEquity, debtToEquity   all None

Four problems, each of which inflates a backtest:

1. **Five years of history.** The price panel is 26 years.
   [[no-single-instrument-is-statistically-distinguishable]] establishes that
   distinguishing signal from luck needs decades. Five years cannot test
   anything.
2. **Not point-in-time.** Figures are as RESTATED today, not as reported
   then. A company that corrected its 2022 earnings shows the corrected
   number, which nobody had in 2022.
3. **No reporting lag.** The statement dated 2025-09-30 was not public until
   roughly November. Using it from 30 September is lookahead.
4. **Survivorship**, already present in the universe, stacks on top.

**Conclusion: fundamental strategies are not testable on free data.** Proper
point-in-time fundamentals (Compustat PIT, Sharadar SF1 and similar) are a
paid product. That makes this a purchase decision, not a coding one.

Filed so the idea is not re-attempted and quietly "validated" on
contaminated data - which, given
[[cost-assumptions-decided-every-conclusion-here]], is the failure mode this
project is most prone to.
