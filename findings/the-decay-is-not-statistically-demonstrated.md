---
name: the-decay-is-not-statistically-demonstrated
description: Era A Sharpe 0.90 vs era B 0.41 looks like decay but the difference is t=0.99, p=0.32 - and era A's 8-year window caps t at ~1.13 no matter how much future data arrives.
metadata:
  type: finding
---
Raised by the LLM council peer-review round, then verified.

    era A (2001-2008, 8y)   SR 0.90   SE 0.419   t 2.15   p 0.032
    era B (2010-2026, 16y)  SR 0.41   SE 0.260   t 1.58   p 0.115
    DIFFERENCE              0.49      SE 0.493   t 0.99   p 0.321

**Correction.** `phase_e_futures.py` prints "OUTCOME 1 - engine validated,
decay confirmed", and that second clause was reported to the user as
established. It is not. Our data cannot distinguish the two eras.

Worse, it never will. The standard error is dominated by era A's 8-year
window (SE 0.419). Extending era B changes almost nothing:

    era B = 20y -> t 1.02
    era B = 40y -> t 1.09
    era B = 80y -> t 1.13

**What still stands:** era A on its own is nominally significant (p=0.032),
so the engine does detect the effect where the literature says it existed -
the positive-control purpose of Phase E is intact. And era B on its own
fails to reject zero (p=0.115), so there is no demonstrated live edge.

**What does not stand:** any claim that *we measured* the decay. The decay
is documented in [[trend-following-decayed-after-2009]] on far larger
samples. Our point estimates are consistent with it. That is all.

Related: [[no-single-instrument-is-statistically-distinguishable]]. A
reviewer also noted Bonferroni across 31 sector-clustered futures is
over-conservative, since effective independent bets are nearer 6-8 - which
means the instrument-level test was harsher than warranted. The
portfolio-level test is the correct unit regardless, and it gives p=0.115.
