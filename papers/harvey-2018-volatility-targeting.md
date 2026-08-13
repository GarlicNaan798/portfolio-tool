---
name: harvey-2018-volatility-targeting
description: Vol targeting lifts Sharpe for equities and credit but is negligible for bonds, FX and commodities; it cuts tail risk everywhere.
metadata:
  type: reference
---
Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & Van Hemert (2018), "The
Impact of Volatility Targeting", *Journal of Portfolio Management*.

Volatility scaling at asset and portfolio level improves Sharpe for **risk
assets** - equity and credit - via the leverage effect. For **bonds,
currencies and commodities the Sharpe impact is negligible**. Across all
classes, however, it reduces the likelihood of extreme returns, because
left-tail events arrive when volatility is already elevated and a target-vol
book is therefore already small.

**For us:** corrects an assumption baked into `phase_d_trend.py`. Our futures
book is mostly rates, FX and commodities, so vol targeting should not be
expected to raise Sharpe there - only to shrink the tails. Keep it for the
tail benefit, not for the ratio.

https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf
