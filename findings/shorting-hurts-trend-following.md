---
name: shorting-hurts-trend-following
description: Adding the short leg reduced returns in every test run, across both ETFs and futures and both eras.
metadata:
  type: finding
---
Observed independently three times:

    Phase D, ETFs      long+short -0.95 Sharpe   long only -0.33
    Phase E, era A     long+short  0.36          long only  0.85
    Phase E, era B     long+short  0.01          long only  0.35

Shorting breakdowns in markets that mostly rose produces repeated whipsaw
losses. This runs against [[moskowitz-2012-tsmom]], whose sample is
1985-2009 and includes genuine two-way trends in rates and FX.

Consistent with [[trend-following-decayed-after-2009]] reporting heterogeneous
decay by asset class - the short side may simply be where most of the decay
landed.
