# Phase 1: does aggregate state predict when factors pay?

Written **before any data is pulled**. The council's condition for this being
worth building at all was that the sign, threshold, and the action taken
under *every* outcome — including success — are fixed in advance.

## The question

Five papers (see `Research Papers/`) argue the same thing from different
angles: anomaly returns are **time-varying and conditional**, not constant.
Papamichalis & Ryu (2025) predict returns fall on both the long and short
side as sentiment rises. Chen (2015) finds flow-driven mispricing is
strongest when funding costs are high. Hollstein et al. (2026) find most
explanatory power lives in the **time-series** dimension, not the
cross-section.

Every strategy in the previous project was unconditional. That is the gap.

## Two changes the council forced, and why

**Real-time state variables, not Baker-Wurgler sentiment.**
BW is built by PCA over the full sample, orthogonalised ex post, revised, and
published with a lag. The look-ahead is in the *loadings*, not the dates, so
a backtest using it will not look wrong. The previous project shipped two
data bugs that were caught only because a number looked implausible; this one
would not have been. Using VIX, the BAA–AAA credit spread and the term spread
removes the objection entirely: each is published once, never revised, and
was observable on the day.

**Tradeable factor ETFs, not AQR paper series.**
AQR factor returns are gross of financing, borrow and rebalancing. Cost
misspecification flipped three conclusions in the previous project, once
producing a false negative. MTUM/VLUE/QUAL/USMV have real prices and real
spreads. AQR series are a cross-check on sign, never the dependent variable.

## Pre-registered hypothesis

**H:** factor excess returns over the next month are predictable from the
level of aggregate stress observable today. Specifically, factor returns are
**higher** following high-stress readings (high VIX, wide credit spreads) and
**lower** following calm ones — the limits-to-arbitrage story, where mispricing
is largest when arbitrage capital is most constrained.

## Pre-registered thresholds

Judged on the **out-of-sample** half only, with the split fixed at 2015-01-01
before looking at anything.

**CONFIRMED** requires all three:
1. Coefficient sign matches H for at least 3 of the 4 factor ETFs
2. Pooled t-statistic > 2.5 on Newey-West standard errors with 12 lags
   (the higher bar is deliberate: the regressor is persistent, and Stambaugh
   bias pushes t toward the hypothesis)
3. A conditional strategy — size up in high stress, down in low — beats
   the same factor held constantly, **after 5bps/side**, on the OOS half

**REJECTED** if any of the three fails.

## Pre-registered actions

- **If REJECTED:** the conditioning thesis is dead for retail-accessible
  data. Record it and stop. Do not substitute a different state variable and
  re-run; that is "change the input, keep the premise", which the previous
  council flagged and which produced ten phases of nothing.
- **If CONFIRMED:** do NOT trade it. Next step is a third holdout on
  non-US factor ETFs (IMTM, IVLU) and a cost-sensitivity sweep to 25bps.
  Confirmation here buys one more test, not a position.
- **If MIXED** (sign holds, t fails): treat as rejected. Report the sign as
  an observation, not a finding.

## Known limitations, stated now rather than discovered later

- Factor ETFs start ~2013 (MTUM April 2013), so the sample is ~13 years.
  SE(Sharpe) over 13 years is roughly 0.28 — this cannot establish a small
  effect, and is not expected to.
- The OOS half is ~11 years of monthly data: about 130 observations, and
  fewer effective ones because VIX is persistent.
- **A confirmed result at this sample size is weak evidence, not a strategy.**
  That is why the action under confirmation is another test.

## Standing rules carried forward

- Benchmark is the thing you would otherwise hold, never SPY by default.
- Controls run every time, not when someone is suspicious.
- State the cost assumption before the result and check it against the
  instrument.
- Report the census, never select on the holdout.
