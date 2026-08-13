---
name: phase-c-breadth-was-not-the-constraint
description: Widening from 22 ETFs to 188 stocks raised breadth 8.5x but cut signal quality 5x; net of costs no size was positive.
metadata:
  type: finding
---
From `phase_c_breadth.py`, testing IR = IC x sqrt(N) by subsampling one
parent universe so model, features and periods stay identical across sizes.

    N=  25  IC +0.0065  IR -0.11  net -1.35%
    N=  50  IC -0.0046  IR -0.05  net -1.15%
    N= 100  IC +0.0217  IR  0.27  net -0.48%
    N= 188  IC +0.0123  IR  0.26  net -0.56%

IR does rise with N and plateaus near 100, running about 40% of the law's
prediction - the expected direction for correlated large caps, per
[[grinold-fundamental-law]].

But the prediction is not confirmed, and the reason matters: IC fell from
+0.109 on ETFs to +0.022 on single stocks. Price-only features capture far
less on individual companies, whose returns turn on earnings and news, than
on baskets where that idiosyncratic noise averages out. The two effects
cancel.

**Breadth was not the binding constraint. Signal strength was.**

Note [[aqr-trends-everywhere]] argues breadth of *markets* does help, which is
not contradicted here - futures across asset classes are far less correlated
than single equities.
