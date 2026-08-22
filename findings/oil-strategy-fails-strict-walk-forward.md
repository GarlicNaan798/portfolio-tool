---
name: oil-strategy-fails-strict-walk-forward
description: Under walk-forward with parameters chosen only from the past, WTI mean reversion scores 0.17 and loses to random config selection.
metadata:
  type: finding
---
From `walkforward.py`, WTI, anchored 6y train / 2y test / 30d embargo,
36 configs searched per fold, 9 folds, 1.5bps/side.

    walk-forward     CAGR  0.26%   maxDD -79.8%   SR 0.17
    random config    CAGR  2.80%   maxDD -75.7%   SR 0.24
    buy and hold     CAGR -1.32%   maxDD -91.5%   SR 0.18

**Selection loses to a coin flip (-0.07 Sharpe).** Picking the best config on
training data performed WORSE out-of-sample than picking one at random from
the same grid. The optimisation is not finding signal; it is finding noise
that happens to fit the training window.

That random-selection null is the single most useful check in the harness.
A plain walk-forward would have reported 0.17 and left it ambiguous.

**Full sample 0.41 -> walk-forward 0.17.** Some of the gap is structural: the
walk-forward window ends 2025-09 and cannot include 2026, the largest
contributor. But
[[oil-mean-reversion-edge-is-three-years]] records 0.33 excluding 2026, so
roughly half the gap is fitting premium - the price of having chosen the
instrument, the rule and the thresholds with hindsight.

**The crash-recovery hypothesis got a fair test and failed.** `dd_min=0.25`
was in the grid. Folds 8 and 9 selected it and scored +0.84 then -1.15.
Consistent with [[crash-recovery-is-suggestive-not-significant]].

**Parameter stability was not the problem** - only 4 distinct configs across
9 folds, one chosen 5 times. The rule is stable and stably worthless, which
is a useful thing to be able to distinguish.

**Verdict: the full-sample result was fitted, not validated.** Walk-forward
0.17 against buy and hold 0.18 is a dead heat in a market that itself lost
money over the window.
