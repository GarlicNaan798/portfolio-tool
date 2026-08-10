# VooSwingH4

H4 swing EA for VOO / S&P500 trackers, synthesised from the three papers in the repo root.

## Strategy

| Layer | Timeframe | Source |
|---|---|---|
| Regime: J-month return > 0 (+ optional D1 SMA200) | D1 | Bird/Gao/Yeung, time-series momentum (Moskowitz et al. 2012) |
| Entry: close < SMA(50) and RSI(14) crossing up out of oversold | H4 | Sarainmaa (2024), §5.1 local-low labelling |
| Exit: ATR stop / RSI overbought / bar-count holding period | H4 | both |

Long-only by default. `AllowShorts=true` mirrors the logic for CFD symbols.

## Install

1. Run `mt5setup.exe` in the repo root yourself (I don't run installers).
2. In MT5: **File → Open Data Folder**, then copy `VooSwingH4.mq5` into `MQL5\Experts\`.
3. **View → Navigator → right-click Experts → Refresh**, then double-click the EA to compile in MetaEditor (F7).

On load the EA runs `SelfCheck()` and prints PASS/FAIL to the Experts log — it refuses to init on FAIL.

## Backtesting

**View → Strategy Tester** (Ctrl+R): pick the symbol, `H4`, modelling **"Every tick based on real ticks"** (or "1 minute OHLC" if ticks aren't available), and a date range that leaves ≥ `MomentumLookbackDays + 200` daily bars of warm-up before the start.

Optimise `MomentumLookbackDays` over `63 / 126 / 189 / 252` — those are exactly the J = 3/6/9/12-month formation periods the momentum paper tests, so the sweep stays inside the literature instead of curve-fitting a new one.

## Two problems with the premise

**1. VOO probably isn't on your broker.** VOO is a US-listed ETF; MT5 brokers almost never carry it. You'll most likely be testing `US500` / `SPX500` / `SP500` CFD instead. Check Market Watch → right-click → Symbols after install. That's a fine proxy — the thesis itself uses the S&P500 index, not VOO — but the CFD has financing charges and a broker-specific spread that VOO doesn't, so results won't transfer to an actual VOO position without adjustment.

**2. H4 bars don't fit a US cash session.** VOO trades 9:30–16:00 ET = 6.5h/day, so H4 gives you one 4h bar plus a 2.5h stub, and MT5 cuts H4 bars on broker-server-time boundaries that won't align with the open. Your bars will be ragged and the backtest will be measuring an artifact. An SPX500 CFD trades ~23h and gives clean 6 bars/day — another reason the CFD is the better test vehicle. If you must stay on cash VOO, H1 or D1 are the honest timeframes.

## Calibration

`RsiOversold`, `AtrStopMult` and `MaxBarsInTrade` are the knobs that need fitting to whichever symbol you land on — spread and volatility differ enough between an SPX500 CFD and cash VOO that the defaults are a starting point, not a setting.

## Prior evidence

The thesis backtest returned **p = 0.83** on Welch's t-test against buy & hold — no significant edge (p71). The momentum paper found neither momentum variant worked well in the US market specifically (p3). Test in-sample and out-of-sample separately and expect to have to beat buy & hold, not just be profitable.
