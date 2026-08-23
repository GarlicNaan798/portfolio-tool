---
name: support-breaks-more-often-than-it-holds
description: Buying near support and selling at resistance exits on a broken level 58% of the time and underperforms both calendar holding and doing nothing.
metadata:
  type: finding
---
From `run_levels.py`, 141 US large caps, event-driven exits replacing fixed
monthly holding. Support and resistance are the rolling low/high of a
lookback window - mechanical, so it can be tested.

    IN SAMPLE            SR     maxDD    exits
    monthly calendar   1.04    -40.8%
    levels             0.92    -46.5%   42% target / 58% stop / 0% time
    levels+macro       0.86    -29.7%   47% target / 53% stop / 0% time
    equal-weight univ  0.89    -46.5%

    WALK-FORWARD         SR
    levels             0.78
    random config      0.72
    equal-weight univ  0.83
    excess -2.96%/yr, bootstrap CI -0.62 to +0.23, 81% of resamples <= 0

**58% of exits were stops.** The level broke more often than it was reached.
That is the mechanism, measured rather than argued: a stock sitting at the
bottom of its range is frequently there because it is still falling. "Support
holds" is true less than half the time on this universe.

**Average hold was 25 days** - it did not even produce longer holds than the
monthly calendar it replaced. It added a stop that fired constantly.

**The macro overlay behaves exactly like every other regime filter here.**
Drawdown improved a lot (-46.5% to -29.7%); return fell further. The
walk-forward selected it in 8 of 9 folds, so the optimiser preferred it - it
just does not convert into risk-adjusted gain. Same shape as
[[paper-strategies-do-not-beat-buy-and-hold]] and
[[both-factors-decayed-not-just-trend]].

**Nothing beat the equal-weight universe.** Levels lost to it by 0.05 Sharpe
and beat random config selection by only 0.06.

Answers directly the question raised in
[[crash-recovery-is-suggestive-not-significant]] about whether level-based
trading - fading a level rather than trading its break - was the untested
half. It was untested. It is now tested, and it does not work here.
