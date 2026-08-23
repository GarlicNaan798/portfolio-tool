---
name: the-failure-is-selection-not-exit-timing
description: Excess return peaks at exactly the 21-day holding period, so exits are optimally timed; the edge is 0.28% at t=1.53 and never significant at any horizon.
metadata:
  type: finding
---
From `run.py holding`. Three hypotheses for why the model underperforms -
sold too early, held too long, or cannot pick winners - each predict a
different shape for the same curve. The shape decides, so no argument is
needed.

    days held     picks  universe    excess      t  ann. excess
            5     0.29%     0.25%    +0.04%   0.39       +2.03%
           10     0.70%     0.61%    +0.09%   0.72       +2.29%
           21     1.63%     1.35%    +0.28%   1.53       +3.37%   <- we hold here
           42     2.92%     2.69%    +0.23%   0.95       +1.36%
           63     4.29%     4.01%    +0.27%   1.01       +1.10%
          126     8.59%     8.05%    +0.54%   1.31       +1.08%
          252    16.30%    16.58%    -0.28%  -0.46       -0.28%

**The holding period is already optimal.** Annualised excess peaks at 21
days, which is exactly the rebalance interval. Selling sooner captures less;
holding longer decays. Neither exit hypothesis survives - there is nothing to
fix there.

**The edge is 0.28% over 21 days at t = 1.53**, and 1.53 is the BEST t at any
horizon on the curve. The picks are not reliably distinguishable from the
universe anywhere.

**The excess turns negative by 252 days** (-0.28%). Over a full year the
picks slightly underperform. That reversal is the signature of short-term
reversal, which decays quickly and then mean-reverts - consistent with
reversal being the only component carrying real content, per
[[ic-does-not-predict-long-only-portfolio-value]].

**Consequence for any future work here.** Effort spent on exit rules, stop
placement, holding periods or trailing logic is misdirected: those were all
tested and the answer was already optimal. The binding constraint is the
0.28% - the model cannot identify winners strongly enough for any exit
policy to matter. See also [[support-breaks-more-often-than-it-holds]],
where a level-based exit scheme was built and lost to the calendar it
replaced.
