---
name: ic-does-not-predict-long-only-portfolio-value
description: Reversal had the best IC (t=2.83) and produced the worst portfolio (0.72 vs the blend's 0.91); quintile analysis shows why IC is the wrong screen for a long-only book.
metadata:
  type: finding
---
From `run_portfolio.py --signal reversal` versus the default blend, 141 US
large caps, strict walk-forward, 5bps/side.

    signal only      walk-forward SR    excess over equal-weight
    reversal              0.72               -0.74% a year
    blend (all four)      0.91               +2.72% a year
    equal-weight univ     0.83                    -

**The signal with the best IC produced the worse portfolio.** Acting on the
IC table alone was wrong, and this was predicted by nothing in the IC table
itself - which is the point.

**Forward return by quintile explains it:**

        signal       q1       q2       q3       q4       q5    q5-q1      t
      mom_12_1    1.54%    1.16%    1.23%    1.26%    1.56%    0.02%   0.04
      reversal    1.04%    1.19%    1.27%    1.54%    1.70%    0.66%   2.28
       low_vol    2.01%    1.38%    1.19%    1.10%    0.96%   -1.05%  -2.46
         trend    1.63%    1.34%    1.16%    1.10%    1.37%   -0.26%  -0.73

Three things IC could not have told us:

1. **`mom_12_1` is U-shaped.** Both tails beat the middle (1.54% and 1.56%
   against ~1.2%). IC measures monotonic rank correlation, so it reads ~0
   and calls a structured signal useless. A long-only top-N book sits in q5
   and does capture that structure.

2. **`low_vol` is inverted in this universe.** q1 - the HIGHEST volatility
   names - returned 2.01% a month against q5's 0.96%. The low-volatility
   anomaly ran backwards here, which is plausible for tech-heavy survivors
   over 2000-2026. The signal as coded carries the wrong sign for this data.

3. **Reversal is monotonic and real** (t = 2.28 on the spread) but its q5
   advantage is thin once turnover is paid. Reversal is a high-turnover
   signal by construction - it holds recent losers, and they change monthly.

**The methodological lesson.** IC is a whole-cross-section statistic. A
long-only portfolio only ever holds the top bucket. Screening signals by IC
therefore discards non-monotonic signals that a top-N book can exploit, and
promotes monotonic ones whose edge lives in the bottom - the names you would
have to short. **Read the quintile table, not the IC, when the book is
long-only.**

Neither configuration beat the equal-weight universe significantly. See
[[portfolio-construction-does-not-add-signal]].
