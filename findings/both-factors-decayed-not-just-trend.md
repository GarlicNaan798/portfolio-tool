---
name: both-factors-decayed-not-just-trend
description: Trend and value both work pre-2009 and both fade after; the combination is validated historically but has nothing left to blend in the live era.
metadata:
  type: finding
---
From `phase_f_value.py` on the 31-market futures book.

    era A 2001-2008        Sharpe   maxDD
      trend only            +0.90    -2.0%
      value only            +0.30    -3.1%
      blend inverse-vol     +0.92    -1.1%

    era B 2010-2026
      trend only            +0.41    -4.2%
      value only            -0.06   -11.1%
      blend inverse-vol     +0.26    -3.5%

**Era A reproduces [[asness-2013-value-momentum-everywhere]] closely.** The
sleeves are negatively correlated (-0.146), and the blend holds trend's
Sharpe while halving its drawdown. That is the diversification the paper
claims, visible in our own data.

**Era B has nothing to combine.** Value decayed from +0.30 to -0.06, so
blending drags trend from 0.41 down to 0.26. Negative correlation is
necessary but not sufficient - both legs must be positive.

The wider point: [[trend-following-decayed-after-2009]] documents decay in
trend. This shows **value decayed over the same period**, on the same book.
Whatever changed after 2009 was not specific to one factor.

**Construction matters.** A first pass defined value time-series - long if
this instrument fell over five years, judged alone - and scored -0.32. AMP
define it cross-sectionally, ranking assets against each other and holding a
cheap-minus-rich spread. That correction alone moved era A value from -0.32
to +0.30. Same data, same period, same costs.

Gate 1 (correlation < 0.3) passed at -0.081. Gate 2 (blend Sharpe > 0.42)
failed at 0.26. Stopped there rather than tuning further - the gates were
pre-registered in `PLAN.md` precisely so this decision was not made after
seeing results.
