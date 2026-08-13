---
name: baltas-kosowski-tsmom-implementation
description: Time-series momentum results depend heavily on rebalancing frequency, turnover and capacity, not only on the signal.
metadata:
  type: reference
---
Baltas & Kosowski, "Demystifying Time-Series Momentum Strategies: Volatility
Estimators, Trading Rules and Pairwise Correlations".

Examines the implementation layer most papers gloss over: volatility estimator
choice, trading-rule form, rebalancing frequency and the pairwise correlation
structure of the book. Measured performance moves a great deal with these, and
capacity constraints bind hardest for faster signals.

**For us:** the reason `phase_e_futures.py` now reports cost sensitivity
explicitly. Our own 25bps-versus-1.5bps error moved era A Sharpe from 0.22 to
0.99 - this paper's point, learned the hard way.
