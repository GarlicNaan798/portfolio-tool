---
name: paper-strategies-do-not-beat-buy-and-hold
description: Across 22 instruments and 336 configs, the best paper-derived rule beat buy & hold on only 6 of 22 out-of-sample
metadata:
  type: finding
---

The full 1d sweep on 2026-08-10 ([[2026-08-10-2013-1d]]) settled the headline
question. The best configuration — `dip_free`, ATR stop 3.0 — beat buy & hold
out-of-sample on **6 of 22 instruments by CAGR and 7 of 22 by Sharpe**. Its
average OOS CAGR was 3.86% against a universe where B&H returned 10–26% on
most equity and commodity holdings.

By the project's own bar (see the ranking rule in CLAUDE.md), under half the
universe is consistent with noise, not an edge. It stays ~50% in cash, which
is most of the explanation: the strategy is out of the market during the
compounding it needs to capture.

**How to apply:** treat time-series momentum on this universe as tested and
negative. Do not re-run the 1d sweep expecting a different answer, and do not
respond to it by widening the parameter grid — the no-open-ended-search rule
in [[CLAUDE]] exists for exactly this moment. The open direction is
cross-sectional rotation (`cross_sectional.py`), which keeps capital deployed
rather than sitting in cash, and which this sweep does not cover.
