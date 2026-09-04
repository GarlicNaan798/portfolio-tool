---
name: stress-predicts-factor-returns-but-not-tradeably
description: VIX predicts next-month factor returns out-of-sample at pooled NW t=4.01, 4/4 factors - but scaling exposure on it lowers Sharpe on all four, because stress predicts volatility as well as return.
metadata:
  type: finding
---
From `lab/conditioning.py`, run against the pre-registration in `PLAN.md`.
Factor ETFs (MTUM, VLUE, QUAL, USMV) in excess of BIL, monthly, OOS from
2015-01 (split fixed before any data was pulled), 5bps/side.

**The economic prediction is confirmed, and not weakly:**

    OUT OF SAMPLE, state = VIX (expanding-window z-score)
      factor      beta    NW t     n
        MTUM   +0.0083    2.02   140
        VLUE   +0.0102    1.75   140
        QUAL   +0.0097    2.68   140
        USMV   +0.0066    2.32   140
      pooled   +0.0087    4.01   560     sign matches 4/4

    credit spread: sign matches 4/4, pooled t = 2.29

High stress today predicts higher factor returns next month. That is the
limits-to-arbitrage story in Papamichalis & Ryu (2025) and Chen (2015), and
it survives an honest out-of-sample test on real-time, never-revised data.

**It is not tradeable by the obvious mechanism.**

    factor   cond SR  const SR   cond ret  const ret
      MTUM      0.64      0.78    +14.62%    +13.45%
      VLUE      0.59      0.65    +15.44%    +12.14%
      QUAL      0.66      0.78    +14.04%    +11.74%
      USMV      0.60      0.72     +9.98%     +8.51%

Sizing up in high stress raised returns on all four factors and lowered
Sharpe on all four. **The same variable that predicts return predicts
volatility.** You are paid more per unit of exposure, but only for holding
exposure exactly when risk is highest, and the second effect dominates.

This is the mirror image of volatility targeting, which sizes DOWN when
volatility is high. The papers predict returns; they are silent on whether
the risk taken to harvest them is worth it. Measured here, it is not.

**Verdict per PLAN.md: REJECTED.** Two of three pre-registered gates failed
for VIX (conditional beat constant on 0/4) and two of three for credit
spread. The registered action on rejection is to record it and stop, and
specifically NOT to substitute another state variable and re-run.

**What would change the answer** - and none of it is a re-run of this test:
a mechanism that harvests the predicted return without scaling exposure
proportionally to the thing that also predicts volatility. Options-based
expressions and cross-sectional (long-short) versions both do that; both
need data or shorting capability this project does not have.
