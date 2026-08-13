# Research base

Papers in `papers/` (type: reference), our own results in
`findings/` (type: finding). Findings cite the papers; papers point
back at the findings they explain. Links go both ways here because
neither side is immutable - unlike `notes/`, which is.

## Papers

- [aqr-demystifying-managed-futures](aqr-demystifying-managed-futures.md) - Managed futures industry returns are largely replicable with simple trend rules across four asset classes.
- [aqr-trends-everywhere](aqr-trends-everywhere.md) - Trend signals extend beyond the classic futures book into less liquid and alternative markets; market breadth drives the result.
- [asness-2013-value-momentum-everywhere](asness-2013-value-momentum-everywhere.md) - Value and momentum are negatively correlated with each other across eight markets, so the combination beats either alone.
- [baltas-kosowski-tsmom-implementation](baltas-kosowski-tsmom-implementation.md) - Time-series momentum results depend heavily on rebalancing frequency, turnover and capacity, not only on the signal.
- [bird-gao-yeung-ts-vs-cs](bird-gao-yeung-ts-vs-cs.md) - Across 24 markets and 768 implementations, time-series momentum beats cross-sectional, but neither works well in the US.
- [crypto-momentum-still-live](crypto-momentum-still-live.md) - Momentum still pays in crypto and concentrates in smaller, less liquid tokens - excluded here by user direction.
- [grinold-fundamental-law](grinold-fundamental-law.md) - IR = IC x sqrt(breadth) - a small edge needs many independent bets to become a large one.
- [harvey-2018-volatility-targeting](harvey-2018-volatility-targeting.md) - Vol targeting lifts Sharpe for equities and credit but is negligible for bonds, FX and commodities; it cuts tail risk everywhere.
- [hurst-2017-century-of-trend](hurst-2017-century-of-trend.md) - Trend following was positive in every decade from 1880 to 2016, strongest during equity drawdowns.
- [jegadeesh-1993-winners-losers](jegadeesh-1993-winners-losers.md) - Buying 3-12 month winners and shorting losers earns abnormal returns; the origin of cross-sectional momentum.
- [koijen-2018-carry](koijen-2018-carry.md) - Carry predicts returns in cross-section and time series across every major asset class, unexplained by known predictors.
- [lemperiere-2014-two-centuries](lemperiere-2014-two-centuries.md) - Trend holds on futures from 1960 and spot series from 1800; among the most statistically significant anomalies known.
- [mittal-2022-stock-health-index](mittal-2022-stock-health-index.md) - Fuzzy rule base over fundamentals produces a stock health index for mid/long-term selection - not applicable to single-instrument timing.
- [moskowitz-2012-tsmom](moskowitz-2012-tsmom.md) - 12-month time-series momentum is positive on all 58 futures across four asset classes, 1985-2009.
- [sarainmaa-2024-sp500-ml](sarainmaa-2024-sp500-ml.md) - Random-forest swing trading on the S&P500 shows no significant edge over buy and hold, p = 0.83.
- [stockformer-cross-sectional-dl](stockformer-cross-sectional-dl.md) - Transformer-style models earn their edge ranking a large cross-section, not timing one instrument.
- [trend-following-decayed-after-2009](trend-following-decayed-after-2009.md) - Trend returns roughly halved post-2009 and fast signals went flat; the break is abrupt.

## Findings

- [futures-costs-decide-whether-trend-survives](../findings/futures-costs-decide-whether-trend-survives.md) - Charging ETF-rate costs to futures turns a Sharpe 0.99 strategy into 0.22; cost assumptions dominate the result.
- [h4-does-not-divide-us-equity-session](../findings/h4-does-not-divide-us-equity-session.md) - US-listed ETFs produce 1.99 H4 bars/day, so a 4-hour chart on them is an artifact, not a timeframe.
- [levered-blend-does-not-close-a-sharpe-gap](../findings/levered-blend-does-not-close-a-sharpe-gap.md) - Levering a low-Sharpe blend to match SPY's volatility gives half the return at the same drawdown.
- [paper-strategies-do-not-beat-buy-and-hold](../findings/paper-strategies-do-not-beat-buy-and-hold.md) - Across ~1000 configs, 29 instruments and two timeframes, no paper-derived strategy beat buy and hold out-of-sample on ETFs.
- [phase-a-blend-failed-on-correlation](../findings/phase-a-blend-failed-on-correlation.md) - Combining our three strategies failed because they were 0.67-0.69 correlated to SPY, not genuinely diversifying.
- [phase-b-had-skill-costs-ate-it](../findings/phase-b-had-skill-costs-ate-it.md) - The learned ranker did have real cross-sectional skill; trading costs consumed nearly all of it.
- [phase-c-breadth-was-not-the-constraint](../findings/phase-c-breadth-was-not-the-constraint.md) - Widening from 22 ETFs to 188 stocks raised breadth 8.5x but cut signal quality 5x; net of costs no size was positive.
- [phase-e-validated-the-engine](../findings/phase-e-validated-the-engine.md) - On 31 futures the engine finds Sharpe ~1.0 pre-2009 and ~0.2 after, matching the literature - so the tooling works and the negative results stand.
- [shorting-hurts-trend-following](../findings/shorting-hurts-trend-following.md) - Adding the short leg reduced returns in every test run, across both ETFs and futures and both eras.

## What the base says to do next

Trend on futures works but is weak post-2009 ([[phase-e-validated-the-engine]]).
Phase A failed for a diagnosed reason - correlated components
([[phase-a-blend-failed-on-correlation]]) - and
[[asness-2013-value-momentum-everywhere]] names the missing
ingredient. [[koijen-2018-carry]] supplies a second uncorrelated
factor computable from the futures curve. That is the one
well-motivated build left.
