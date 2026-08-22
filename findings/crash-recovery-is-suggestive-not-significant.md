---
name: crash-recovery-is-suggestive-not-significant
description: Deep-drawdown entries produce 64% of oil P&L from 26% of trades, but the effect fails significance and is non-monotonic.
metadata:
  type: finding
---
From `crash_recovery.py`. Every WTI mean-reversion trade tagged with the
underlying's drawdown from its running peak AT ENTRY - no lookahead - then
bucketed.

    drawdown at entry     n   win%   avg ret   share of P&L
            0-10%        84    69%    +0.52%        23%
           10-25%        68    54%    -0.34%       -12%
           25-50%       159    60%    +0.31%        26%
             >50%       108    64%    +1.13%        64%

    deep (>=25%) +0.64%  vs  shallow (<25%) +0.14%
    difference   +0.51%,  t = 1.15  -> not significant

The `>50%` bucket producing 64% of profit from 26% of trades is striking and
matches the observation that 2016, 2021 and 2026 were all recoveries from
collapse. But two things stop it being a finding:

1. **t = 1.15.** Trade returns are noisy enough that the difference is not
   distinguishable from chance.
2. **It is non-monotonic.** The shallowest bucket is second-best while
   10-25% actually loses money. A real crash-recovery mechanism should
   improve steadily with depth.

**Deliberately not hard-coded into the rule.** Adding a filter on a
non-significant, non-monotonic pattern is the exact error this repo keeps
catching. It was instead put into the walk-forward grid as `dd_min`, where it
was selected in 2 of 9 folds and scored +0.84 then -1.15 - see
[[oil-strategy-fails-strict-walk-forward]].
