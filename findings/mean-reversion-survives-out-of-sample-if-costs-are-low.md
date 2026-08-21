---
name: mean-reversion-survives-out-of-sample-if-costs-are-low
description: Unfiltered DV2 mean reversion on SPY beats buy & hold on Sharpe out-of-sample at low cost, but dies at 25bps; the paper's regime filter does not help.
metadata:
  type: finding
---
From `mr_regime.py`, testing the foundational claim of
[[abrams-2010-mr-swing]] on SPY. Long-only DV2, buy below 40, sell above 70.

**Their window, 2000-2010 (zero costs, as the paper assumes):**

    buy & hold      -0.90% CAGR   Sharpe 0.07
    MR in bear      10.59%        Sharpe 0.74     <- paper claims 0.72
    MR in bull       2.31%        Sharpe 0.34     <- paper claims -0.09
    MR unfiltered   12.79%        Sharpe 0.80

The bear-regime number replicates almost exactly. The bull-regime number
does not, and the discrepancy is explainable: their MR goes long AND short,
so bull-regime losses come from shorting a rising market. Long-only is
positive. That is [[shorting-hurts-trend-following]] appearing a fourth time.

**But the regime filter itself does not earn its place.** Unfiltered MR
(0.80) beats bear-only (0.74) in their own window, and beats it again out of
sample. The paper's central design principle does not survive replication.

**Out of sample, 2010-2026 - data the paper never saw:**

    cost/side   MR unfiltered           buy & hold
    0bps        14.20% CAGR, SR 1.09    14.63% CAGR, SR 0.88
    5bps        10.81% CAGR, SR 0.86
    25bps       -1.76% CAGR, SR -0.07

At zero cost this is the best out-of-sample result in the project: near-equal
return, **half the drawdown (-17.7% vs -33.7%)**, higher Sharpe, 56% of days
in market. At 5bps it is a Sharpe tie with much lower drawdown. At 25bps it
is destroyed.

**The whole result is a cost question**, which makes
[[cost-assumptions-decided-every-conclusion-here]] the governing issue.
