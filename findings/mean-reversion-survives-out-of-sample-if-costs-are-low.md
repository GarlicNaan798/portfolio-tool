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


## Extended to the ETF universe

`recheck_costs.py`, 22 ETFs, out-of-sample from 2020-01-01:

    fee     best variant   beats B&H   mean SR   B&H mean SR
    0bps    dv2 J=63         11/22       0.65       0.45
    2bps    dv2 J=63         10/22       0.55       0.45
    5bps    dip J=63          6/22       0.26       0.45
    25bps   dip J=63          6/22       0.23       0.45

DV2 is the best variant tested at low cost and the only one that ever clears
double digits. Two restraints:

1. **10/22 is 45% - under half the universe.** By the standard already used
   in this repo, that is consistent with noise, not an established edge.
2. **2bps is realistic for SPY and optimistic for the rest.** UNG, CPER,
   FXY and DBA are thin; 5-20bps is plausible there, and at 5bps DV2 drops
   out of the lead entirely. A uniform fee flatters the illiquid half.

So the honest reading: short-horizon mean reversion is the most promising
family found in this project, it is cost-sensitive to the point of fragility,
and it has not cleared the bar the repo sets for calling something real.
