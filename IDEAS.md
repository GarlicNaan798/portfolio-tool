# What has been tried, and why it failed

Read this before proposing anything. Every row cost real work and produced a
real answer. Re-running any of them without changing the *mechanism* will
reproduce the same result.

Detail and evidence live in `findings/`. Sources live in `papers/`.

## The scoreboard

| # | Idea | Result | Detail |
|---|---|---|---|
| 1 | TSMOM / trend on equity ETFs | 0/480 configs beat B&H on VOO | [findings](findings/paper-strategies-do-not-beat-buy-and-hold.md) |
| 2 | RSI dip-buying (thesis rule) | 6/22 instruments, at any cost | same |
| 3 | SMA50/200 crossover | 5/22 | same |
| 4 | Cross-sectional rotation | 38/96 beat equal-weight, 8/96 beat SPY | same |
| 5 | Combining strategies | Sharpe 0.68 vs SPY 0.83 | [findings](findings/phase-a-blend-failed-on-correlation.md) |
| 6 | Levering the blend to SPY risk | Half the return, same drawdown | [findings](findings/levered-blend-does-not-close-a-sharpe-gap.md) |
| 7 | ML cross-sectional ranker (GBM) | Real skill, costs ate 90% of it | [findings](findings/phase-b-had-skill-costs-ate-it.md) |
| 8 | Widening 22 ETFs -> 188 stocks | Breadth x8.5, IC /5, net negative | [findings](findings/phase-c-breadth-was-not-the-constraint.md) |
| 9 | Trend following on 31 futures | 0.90 pre-2009, 0.41 after, n.s. | [findings](findings/phase-e-validated-the-engine.md) |
| 10 | Adding a value factor | Works pre-2009, value decayed too | [findings](findings/both-factors-decayed-not-just-trend.md) |
| 11 | Shorting anything | Hurt in 4 independent tests | [findings](findings/shorting-hurts-trend-following.md) |
| 12 | Per-instrument significance | 0 of 83 survive Bonferroni | [findings](findings/no-single-instrument-is-statistically-distinguishable.md) |
| 13 | MR Swing regime switching | Bear claim replicates, filter doesn't help | [findings](findings/mean-reversion-survives-out-of-sample-if-costs-are-low.md) |
| 14 | DV2 mean reversion on oil | 0.41 full sample, **0.17 walk-forward** | [findings](findings/oil-strategy-fails-strict-walk-forward.md) |
| 15 | Crash-recovery filter | 64% of P&L in deep bucket, t=1.15 | [findings](findings/crash-recovery-is-suggestive-not-significant.md) |

## The five recurring failure modes

Every dead end above is one of these. Check a new idea against them first.

**1. Absence is not alpha.**
The rules win by being out of the market during declines, not by generating
return. Measured directly: they beat buy & hold on 3/18 instruments that rose
and 3/4 that fell. In a rising asset, being out is the expensive mistake.

**2. Cost decides more often than signal.**
Three separate times a cost misspecification flipped a conclusion - futures
charged at ETF rates (Sharpe 0.99 -> 0.22), the ML ranker's spread, and the
oil result across 0/5/25bps.
[findings](findings/cost-assumptions-decided-every-conclusion-here.md)
**State the cost assumption before the result, and check it against the
actual instrument.**

**3. There is not enough data to prove a single instrument.**
SE(Sharpe) ~ 0.20-0.25 over 25 years. One instrument needs Sharpe > 0.8 to
clear significance after correcting for how many were examined. This is a
power ceiling, not a data-collection problem - roughly 40 years would be
needed at Sharpe 0.5.

**4. The edge is usually three years.**
Strip the best 3 years of 25 from the oil result and it goes from beating
buy & hold to losing to it. Concentration in a few periods is the default
finding, not the exception. Always run the exclusion test.

**5. Full-sample results are fitted, not validated.**
Oil scored 0.41 seeing all the data and 0.17 under strict walk-forward -
and lost to *random parameter selection*. Any number produced without
out-of-sample discipline should be assumed inflated by roughly half.

## Two things that did survive

- **The engine is correct.** A positive control on futures found Sharpe 0.90
  pre-2009 and 0.41 after, matching the published decay. Negative results
  here are about markets, not bugs.
  [findings](findings/phase-e-validated-the-engine.md)
- **Drawdown reduction is real.** 460/480 configs cut drawdown. It is also
  trivially achievable by holding cash, so it only counts if Sharpe improves
  with it - which it did not.

## Mistakes made in the process

Recorded because they were caught late and would otherwise repeat.

- **Cartesian join on a non-unique index** inflated an ML result to a false
  positive (2.4M rows from a 116k panel). Caught by an implausible row count.
- **25bps charged to futures** turned a working strategy into a failing one.
  Caught by a positive control returning the wrong sign.
- **A hardcoded pessimistic conclusion** in output text that contradicted the
  computed statistic. Now always computed.
- **Goalpost-moving.** After seven negatives, proposing to redefine success as
  "reduce drawdown" - killed by the council, correctly, since holding cash
  reduces drawdown.

Both data bugs flattered the result. **Assume the third one does too, and
that it lives in whichever result currently looks best.**

## Standing rules

- Buy & hold is the benchmark. "Profitable" is not the bar.
- Signals read bar t, fills happen at bar t+1 open.
- Pre-register pass/fail criteria before running.
- Report the census, never select on the holdout.
- Rank by breadth of agreement, not by the best single result.
