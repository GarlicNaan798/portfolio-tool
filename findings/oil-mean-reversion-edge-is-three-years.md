---
name: oil-mean-reversion-edge-is-three-years
description: WTI mean reversion beats buy and hold over 25 years, but removing its three best years erases the entire advantage.
metadata:
  type: finding
---
From `backtest.py` and the exclusion test, WTI crude, DV2 mean reversion,
1.5bps/side, 2000-2026.

**What survives scrutiny:**

    split half      first 0.37, second 0.49 - no decay, and the second half
                    improves while buy and hold collapses (0.43 -> 0.18)
    bootstrap       2000 reshuffles in 20-day blocks, 95% CI [0.01, 0.81],
                    2.1% of resamples at or below zero

**What does not:**

    full                 SR 0.41  t 1.98   B&H 0.30
    excl 2026            SR 0.33  t 1.56   B&H 0.26
    excl 2016+2021+2026  SR 0.26  t 1.22   B&H 0.27   <- edge gone

Three years out of 25 carry the whole advantage: 2016 (+41%), 2021 (+55%)
and 2026 (+60%, an INCOMPLETE year - data ends 12 August). Strip them and
the strategy is marginally worse than holding oil, measured over the same
reduced sample so the comparison is fair.

**Year by year it does not look like an edge either:**

    positive years        15/25
    years beating B&H     10/25
    rolling 1y Sharpe     positive 58% of windows, 25th pct -0.58

And six of the ten winning years are years oil FELL - 2008 (+18% vs -54%),
2014 (+3% vs -46%), 2015 (0% vs -30%), 2018 (+8% vs -25%), 2020 (+2% vs
-21%), 2025 (-14% vs -20%). In rising years it lags badly: 2007 +7% against
+57%, 2009 +21% against +78%, 2019 -15% against +34%.

**This is the same shape as every other result in this repo.** It wins by
being absent during crashes, not by generating return - see
[[paper-strategies-do-not-beat-buy-and-hold]]. Oil is simply a market where
absence is worth more, because buy and hold there returned 3.77% a year with
a 91% drawdown.

**Verdict: not robust enough to act on.** A Sharpe advantage that lives in
three years, one of them unfinished, is concentration risk wearing an edge
as a costume. The bootstrap barely clearing zero on the FULL sample is not
reassurance when the full sample is what contains those three years.
