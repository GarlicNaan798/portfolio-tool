---
name: moskowitz-2012-tsmom
description: 12-month time-series momentum is positive on all 58 futures across four asset classes, 1985-2009.
metadata:
  type: reference
---
Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum", *Journal of
Financial Economics* 104(2).

A security's own past 12-month return predicts its next-month return. Tested
on 58 futures and forwards - country equity indexes, currencies, commodities,
sovereign bonds - and **positive on every single one**. The effect persists
about 12 months then partially reverses. The diversified portfolio shows
little exposure to standard factors and performs best in extreme markets.

**For us:** source of the `tsmom` variant and the J = 3/6/9/12 month grid.
Its universe is futures, not equity ETFs - the distinction
[[phase-e-validated-the-engine]] turned on. Sample ends 2009, before the break
in [[trend-following-decayed-after-2009]].

https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf
