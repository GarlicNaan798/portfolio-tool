---
name: futures-costs-decide-whether-trend-survives
description: Charging ETF-rate costs to futures turns a Sharpe 0.99 strategy into 0.22; cost assumptions dominate the result.
metadata:
  type: finding
---
From the Phase E correction in `phase_e_futures.py`.

    1.5bps/side   era A Sharpe +0.99   era B +0.26
    5.0bps/side   era A Sharpe +0.87   era B +0.13
     10bps/side   era A Sharpe +0.71   era B -0.04
     25bps/side   era A Sharpe +0.22   era B -0.57

Futures cost roughly 1-2bps all-in; equity ETFs cost about 25bps. Charging the
ETF rate to futures is a 25x overcharge and on its own flips the verdict. This
was an actual error in the first Phase E run, and the conclusion reported to
the user was wrong until it was fixed.

**Consequence for the ETF work:** 25bps is correct there, so
[[paper-strategies-do-not-beat-buy-and-hold]] stands. Trend survives on
futures largely *because futures are cheap to trade*, not because the signal
is better.

Predicted by [[baltas-kosowski-tsmom-implementation]], which argues the
implementation layer moves results as much as the signal does.
