---
name: bird-gao-yeung-ts-vs-cs
description: Across 24 markets and 768 implementations, time-series momentum beats cross-sectional, but neither works well in the US.
metadata:
  type: reference
---
Bird, Gao & Yeung, "Time-series and cross-sectional momentum strategies under
alternative implementation strategies". In the repo root as
`Research paper 2.pdf`.

Compares both momentum forms like-for-like across 24 developed markets and 768
implementations: J = 3/6/9/12 months, holding periods 3/6/9/12, cut-offs at
50/30/16%, equal/market/inverse-vol weights, CAR against BHAR rebalancing.
Time-series wins overall because it times market exposure, while
cross-sectional always holds the same number of names regardless of market
state.

**For us:** source of our parameter grid, and the explicit warning about
implementation sensitivity - 768 variants gave wildly different answers. It
also flags US momentum as weak, which our own data reproduced independently.
