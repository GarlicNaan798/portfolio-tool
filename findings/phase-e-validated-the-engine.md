---
name: phase-e-validated-the-engine
description: On 31 futures the engine finds Sharpe ~1.0 pre-2009 and ~0.2 after, matching the literature - so the tooling works and the negative results stand.
metadata:
  type: finding
---
From `phase_e_futures.py`, the first positive control in the programme.

    era A 2001-2008   best Sharpe 0.99   mean 0.60
    era B 2010-2026                      mean 0.18
    long only         A 0.85   B 0.35
    long+short        A 0.36   B 0.01

Outcome 1 of three pre-registered in `PLAN.md`: the engine detects the effect
where [[moskowitz-2012-tsmom]] and [[hurst-2017-century-of-trend]] say it
existed, and finds it much weaker after the break documented in
[[trend-following-decayed-after-2009]].

**This is what licenses trusting the earlier negatives.** Without it,
[[paper-strategies-do-not-beat-buy-and-hold]] could have been a bug.

Two bugs were fixed to get here, both mine - see
[[futures-costs-decide-whether-trend-survives]] and the roll-artifact note in
`phase_d_trend.sleeve`.
