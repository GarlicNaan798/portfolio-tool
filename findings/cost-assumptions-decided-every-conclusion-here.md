---
name: cost-assumptions-decided-every-conclusion-here
description: Three separate times a cost misspecification flipped a conclusion; the 25bps used for all ETF work is likely 10-25x too high for liquid ETFs.
metadata:
  type: finding
---
Cost has changed the answer more often than any signal choice in this
repo. Three instances, all caught after the fact:

1. **Futures charged at ETF rates.** 25bps/side instead of ~1.5bps turned
   era-A trend Sharpe from 0.99 into 0.22 and produced a reported failure
   that was not real. See
   [[futures-costs-decide-whether-trend-survives]].

2. **The ML ranker.** Real skill (IC +0.109, p=0.007) with ~90% of the gross
   spread consumed by assumed costs. See
   [[phase-b-had-skill-costs-ate-it]].

3. **The ETF work itself, still unresolved.** Every ETF result in this repo
   used FEE = 0.0025, i.e. **25bps per side**, inherited from
   [[sarainmaa-2024-sp500-ml]] - a European retail broker assumption.

For SPY at a modern US broker, commission is typically zero and the spread
is about one cent on a ~$600 share, roughly **0.1-0.2bps**. Even allowing
generously for slippage, 2-5bps is realistic. **25bps is somewhere between
10x and 100x too high.**

`mr_regime.py` shows what that does. Same strategy, same data, out of
sample:

    0bps    Sharpe  1.09
    5bps    Sharpe  0.86
    25bps   Sharpe -0.07

**Consequence:** [[paper-strategies-do-not-beat-buy-and-hold]] was
established at 25bps and needs re-running at realistic ETF costs before it
can be trusted as a statement about strategies rather than about a fee
assumption. The trend-on-equities conclusion may survive - trend was losing
on gross terms too - but that has not been checked.

The pattern to internalise: **state the cost assumption before the result,
and check it against the actual instrument.** Every time that step was
skipped here, the conclusion moved.
