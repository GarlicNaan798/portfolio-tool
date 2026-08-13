---
name: levered-blend-does-not-close-a-sharpe-gap
description: Levering a low-Sharpe blend to match SPY's volatility gives half the return at the same drawdown.
metadata:
  type: finding
---
From `diagnostics.py` part 1, testing the hypothesis that Phase A simply
took too little risk.

    SPY                  CAGR 15.87%   maxDD -33.7%   Sharpe 0.83
    blend 1.00x          CAGR  6.51%   maxDD -17.2%   Sharpe 0.68
    blend 2.03x levered  CAGR  7.93%   maxDD -33.0%   Sharpe 0.48

Leverage is Sharpe-neutral gross and slightly Sharpe-negative net, because
financing is charged on the borrowed portion. A Sharpe gap cannot be closed
by sizing; it has to be closed by a better signal or better diversification.

Refutes the "under-risked" reading of
[[phase-a-blend-failed-on-correlation]].
