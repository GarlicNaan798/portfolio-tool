---
name: grid-is-44-percent-duplicate-configs
description: 147 of swing_lab's 336 configs are exact duplicates because cross and dip_free ignore the lookback and SMA200 dimensions
metadata:
  type: finding
---

`grid()` in swing_lab.py sweeps `lookback` (4 values) x `use_sma200` (2)
across every variant, but two of the four variants never read those inputs:

- `cross` decides on `sma50 > sma200` alone
- `dip_free` decides on `close < sma50` plus the RSI cross alone

Only `tsmom` and `dip` consult `regime`, which is where `lookback` and
`use_sma200` are used. Measured on 2026-08-10:

| variant | configs | distinct |
|---|--:|--:|
| tsmom | 24 | 24 |
| cross | 24 | **3** |
| dip | 144 | 144 |
| dip_free | 144 | **18** |
| total | 336 | 189 |

**147 of 336 configs (44%) are exact duplicates.** This is visible in any
`notes/` run as blocks of identical rows differing only in the J and 200
columns — see [[2026-08-10-2013-1d]], where six `dip_free` rows report the
same 6/22 and 3.86%.

**How to apply:** the "336 configs" headline overstates the search — it is
really 189. Do not read repeated rows as independent confirmation; they are
one result printed eight times. Fix, when it is worth the diff: skip the
inert dimensions per variant inside `grid()`, which cuts sweep time ~44%.
Ranking conclusions are unaffected — duplicates score identically and do not
bias which config wins.
