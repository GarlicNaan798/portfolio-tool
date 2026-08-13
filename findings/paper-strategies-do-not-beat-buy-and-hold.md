---
name: paper-strategies-do-not-beat-buy-and-hold
description: Across ~1000 configs, 29 instruments and two timeframes, no paper-derived strategy beat buy and hold out-of-sample on ETFs.
metadata:
  type: finding
---
Established across `strategy_search.py`, `swing_lab.py` and
`cross_sectional.py`.

    VOO daily, 480 configs        0/480 beat B&H on CAGR
    22 instruments daily          best beat B&H on  6/22
    7 instruments 4H              best beat B&H on  3/7
    cross-sectional, 96 configs   8/96 beat SPY

Wins concentrate where buy and hold lost money: 3/4 on instruments that fell
against 3/18 on instruments that rose. These signals do not generate return,
they reduce exposure - valuable only when the asset declines.

Reproduces both source papers independently: [[sarainmaa-2024-sp500-ml]]
reports p = 0.83 against B&H, and [[bird-gao-yeung-ts-vs-cs]] finds US
momentum weak.

**Do not re-run expecting otherwise.** The result is robust and, per
[[phase-e-validated-the-engine]], not a tooling artifact.
