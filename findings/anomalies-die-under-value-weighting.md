---
name: anomalies-die-under-value-weighting
description: Across 212 published anomalies, value-weighting halves the survival rate at t>2.78 (67% to 31%) and drops the median |t| to 1.81 - below significance.
metadata:
  type: finding
---
From `lab/cz.py` on Chen & Zimmermann's Open Source Cross-Sectional Asset
Pricing data: 212 published anomalies, monthly long-short portfolio returns,
1926-2024, built by the authors to each original paper's methodology.

    portfolio set                    t>1.96   t>2.78   median |t|   median ann
    original (as published)            79%      67%       3.44        +5.2%
    value-weighted                     48%      31%       1.81        +3.4%
    microcaps excluded (NYSE p20)      67%      50%       2.74        +3.6%
    price > $5                         75%      59%       3.16        +4.0%

**Value-weighting alone halves survival at the multiple-testing hurdle** and
pushes the median anomaly below significance. Microcap exclusion costs a
further chunk. Applying both, as Hou/Xue/Zhang (2020) do, lands near their
reported ~18% survival.

This resolves an apparent contradiction in the literature. Chen & Zimmermann
report ~98% replication; HXZ report 82% failure. Both are correct: the
anomalies are real where they were measured (equal-weighted, microcaps
included) and largely absent where a large account would have to trade them.
HXZ state the mechanism directly - *"because of high costs in trading these
stocks, anomalies in microcaps are more apparent than real."*

**Independently validates this project's earlier negative results.** The
previous ten-phase effort tested US large caps and found a selection edge of
0.28% over 21 days at t = 1.53. That is not a failure of method; it is what a
large-cap anomaly is supposed to look like. An external dataset of 212
published anomalies now says the same thing.

**Also worth holding onto:** the median value-weighted anomaly returns +3.4%
a year, and that figure is gross of all costs. The top of the table is
dominated by high-turnover effects - short-term reversal at t = 13.95 and a
nominal 34%/yr - which is precisely the profile that does not survive
spreads.

The remaining open question, and the only one worth spending on, is whether
the effects that persist in small illiquid names survive **retail** costs at
**retail** size, where capacity is not the binding constraint. That is
pre-registered as steps 3-6 in PLAN.md.
