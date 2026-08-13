---
name: trend-following-decayed-after-2009
description: Trend returns roughly halved post-2009 and fast signals went flat; the break is abrupt.
metadata:
  type: reference
---
"Is Trend Still Your Friend? A Microstructural Account of the Demise of
Short-Term Trend-Following" (2026), arXiv; with Carver's decomposition of the
decay into cohort, instrument and environment effects.

The post-2008/09 break is abrupt. Returns since are roughly half those of each
of the three prior decades. **Fast signals are worst affected** - cumulative
P&L of a fast trend portfolio is essentially flat from 2009. Weakening may be
detectable from around 2000.

**For us:** the single most important context in this repo. Every backtest we
ran sits inside the decayed era, and our own measurement agrees - era A mean
Sharpe 0.60 against era B 0.18 in [[phase-e-validated-the-engine]]. It also
means switching instruments cannot restore what faded everywhere at once.

https://arxiv.org/pdf/2607.01550
https://qoppac.blogspot.com/2025/10/is-degradation-of-trend-following.html
