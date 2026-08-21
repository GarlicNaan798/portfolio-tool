---
name: abrams-2010-mr-swing
description: Regime-switching system: mean-reversion in bear regimes, swing trading in bull, with asymmetric rules per regime.
metadata:
  type: reference
---
Abrams & Walker (2010), "MR Swing: A quantitative system for
mean-reversion and swing trading in market regimes", NAAIM. In the repo root
as `MR_Swing_NAAIM_03_13_2010.pdf`.

Four design principles: regime switching, **non-symmetrical** algorithms
(different rules per regime, not mirrored), volatility-adaptive metrics, and
robustness to regime whipsaws.

    regime   200-day SMA channel of bar highs/lows, ratchets only in the
             trend direction (hysteresis, fewer whipsaws than a plain SMA)
    bear     short-term mean reversion on the DV2 percentile oscillator,
             buy below 40, sell above 70
    bull     pullback entry on Value Chart oversold (-7.5) via limit order
             at min(low[1], low[2]); exit on SVAPO exhaustion via limit
             order at max(high[1], high[2])

Reported on SPY 2000-2010: 37.9% CAGR / 1.58 Sharpe (aggressive), or 23.1%
CAGR / 1.37 Sharpe / -13.1% drawdown (no counter-trend). Out-of-sample on
QQQQ, EEM, IWM, VTI.

**Costs are excluded entirely** - the paper states commissions, taxes and
slippage are all omitted, on a system doing ~400 trades. Given
[[cost-assumptions-decided-every-conclusion-here]] that is the number that
matters most, and it is absent.

Also: the sample ends 02/2010 and contains two of the largest bear markets
on record, which is precisely the condition the bear-regime claim needs.

Tested in `mr_regime.py` - see
[[mean-reversion-survives-out-of-sample-if-costs-are-low]].
