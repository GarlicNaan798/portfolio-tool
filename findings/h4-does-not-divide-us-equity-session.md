---
name: h4-does-not-divide-us-equity-session
description: US-listed ETFs produce 1.99 H4 bars/day, so a 4-hour chart on them is an artifact, not a timeframe.
metadata:
  type: finding
---
Measured directly from VOO hourly data: 3,475 bars over 500 trading days,
covering session hours 9, 10, 11, 12, 13, 14, 15 ET - exactly 7 hourly bars a
day.

A 6.5-hour session does not divide into 4-hour bars. You get one 4h bar plus a
2.5h stub, and MT5 cuts H4 on broker-server-time boundaries that do not align
with the open. Resampled H4 measures 1.99 bars/day against 6.00 for a 24h
instrument.

**Consequence:** 4H is only meaningful on ~24h instruments - futures and
crypto. Cash equity ETFs are D1 or H1 only. Encoded in `swing_lab.py` as the
split between `UNIVERSE_1D` and `UNIVERSE_4H`.

Free intraday history is also capped at 730 days by Yahoo, so any 4H test has
about 1 year of holdout after warm-up - too little to conclude from.
