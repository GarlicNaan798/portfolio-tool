---
name: stockformer-cross-sectional-dl
description: Transformer-style models earn their edge ranking a large cross-section, not timing one instrument.
metadata:
  type: reference
---
StockFormer and the related deep-learning cross-sectional literature, added by
the user to the repo root.

Self-attention over many securities with rich inputs - price, fundamentals,
relational structure - to rank the cross-section. Reported edges come from
selection among hundreds or thousands of names.

**For us:** motivated Phase B. Two departures were deliberate: an ETF universe
instead of S&P constituents, because free point-in-time membership data does
not exist and today's members inject survivorship bias; and gradient boosting
before any transformer, because a model that cannot rank with GBM will not
rank with attention. See [[phase-b-had-skill-costs-ate-it]].
