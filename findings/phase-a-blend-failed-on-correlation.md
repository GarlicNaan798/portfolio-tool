---
name: phase-a-blend-failed-on-correlation
description: Combining our three strategies failed because they were 0.67-0.69 correlated to SPY, not genuinely diversifying.
metadata:
  type: finding
---
From `phase_a_combine.py`, against pre-registered gates in `PLAN.md`.

    blend equal-weight   Sharpe 0.68   CAGR  6.51%   maxDD -17.2%
    blend inverse-vol    Sharpe 0.56   CAGR  2.36%   maxDD -10.2%
    SPY                  Sharpe 0.83   CAGR 15.87%   maxDD -33.7%

Both blends cleared the drawdown gate and failed Sharpe and CAGR.

Cause is in the correlation matrix: tsmom/SPY 0.67, rotation/SPY 0.69. The
components were the same long-equity trade in different costumes, so there
was no diversification to harvest.

The fix is named in [[asness-2013-value-momentum-everywhere]]: value and
momentum are *negatively* correlated with each other. Value is the ingredient
we never had. See also [[levered-blend-does-not-close-a-sharpe-gap]].
