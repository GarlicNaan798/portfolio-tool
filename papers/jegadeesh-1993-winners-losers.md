---
name: jegadeesh-1993-winners-losers
description: Buying 3-12 month winners and shorting losers earns abnormal returns; the origin of cross-sectional momentum.
metadata:
  type: reference
---
Jegadeesh & Titman (1993), "Returns to Buying Winners and Selling Losers",
*Journal of Finance* 48(1).

Ranks stocks on 3-12 month past returns, longs the top decile, shorts the
bottom, holds 3-12 months. Significant abnormal returns not explained by risk.
The 12-1 convention - skip the most recent month to avoid short-term reversal
- originates here.

**For us:** source of the rotation arm in `cross_sectional.py` and of the
gap=1 parameter. Note it is a **long-short** result, which is precisely the
distinction that made our long-only comparison unfair in
[[phase-b-had-skill-costs-ate-it]].

https://www.jstor.org/stable/2328882
