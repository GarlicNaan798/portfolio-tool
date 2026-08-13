---
name: phase-b-had-skill-costs-ate-it
description: The learned ranker did have real cross-sectional skill; trading costs consumed nearly all of it.
metadata:
  type: finding
---
From `phase_b_ranker.py` and `diagnostics.py` part 2.

Measured as a long-only portfolio against SPY, the model lost 0/3 folds. That
framing was wrong - it carries full market beta, so selection skill is
invisible beneath it. Measured as the literature measures it, a long-short
spread against zero:

    fold 1 (2018-19)  IC +0.026  p=0.610   spread +0.58%
    fold 2 (2020-22)  IC +0.041  p=0.345   spread +0.72%
    fold 3 (2023-26)  IC +0.109  p=0.007   spread +1.14%  Sharpe 1.03

Fold 3 is significant and survives Bonferroni across three folds. But costs
take about 1% per rebalance from a 1.14% gross spread, leaving roughly
1.7%/yr - real, and not a business.

The long-short/long-only distinction traces to
[[jegadeesh-1993-winners-losers]]. Motivation was
[[stockformer-cross-sectional-dl]].

**Correction recorded:** an earlier run reported 1/3 folds won and was
invalid - `panel.join()` on a non-unique (date, ticker) index produced a
cartesian product, 2.4M rows for a 116k-row panel, pairing rows with other
tickers' rank features. Fixed by positional assignment; the spurious win
disappeared.
