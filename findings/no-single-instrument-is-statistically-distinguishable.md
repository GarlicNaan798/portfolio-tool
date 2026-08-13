---
name: no-single-instrument-is-statistically-distinguishable
description: Zero of 83 instrument-tests survive multiple-testing correction; the nominal winners match chance exactly, so no instrument can be singled out.
metadata:
  type: finding
---
From `instrument_ranking.py`. Annualised Sharpe with Lo (2002) standard
error, SE = sqrt((1 + SR^2/2)/T), t = SR/SE, Bonferroni at 0.05/N.

    universe            N    survive Bonferroni   nominal p<0.05   chance
    futures era A      30          0                    -            1.5
    futures era B      31          0                    2            1.6
    equity ETFs        22          0                    2            1.1

**Nominal significance count equals the chance expectation.** Two out of 31
at p<0.05 is what randomness produces when you run 31 tests. There is no
instrument-level signal to find.

The reason is a power limit, not a data-collection problem. Over ~16 years
SE(SR) ~ 0.25, so clearing Bonferroni (t > 3.2) on ONE market requires
SR > 0.80. The best single market in era B was NQ=F at 0.55 (t = 2.08,
p = 0.038). Proving a single instrument at SR 0.5 would need roughly 40+
years of data.

**Portfolio-level, which is what [[moskowitz-2012-tsmom]] actually claims:**

    futures era A   SR  0.90   t  2.16   p 0.031
    futures era B   SR  0.41   t  1.61   p 0.108
    equity ETFs     SR -0.12   t -0.49   p 0.627

Era A is nominally significant; era B is not. Consistent with
[[trend-following-decayed-after-2009]] and with
[[grinold-fundamental-law]] - the evidence is a property of breadth, not of
any market.

**Where trend does beat buy and hold, it is on markets buy and hold did
badly.** Among era-B leaders, trend beats B&H on silver, Brent, soybeans and
cotton (B&H Sharpe 0.43, 0.20, 0.14, 0.16) and loses on Nasdaq, S&P, gold
(B&H 0.91, 0.76, 0.58). Reproduces
[[paper-strategies-do-not-beat-buy-and-hold]] on a different universe.

**Consequence:** any answer of the form "instrument X is the most promising"
is unsupported by this data. The defensible claim is about a diversified
futures book, and even that is not significant post-2009.
