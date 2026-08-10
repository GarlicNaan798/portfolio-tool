"""Grid-search paper-derived strategies on VOO, with an out-of-sample holdout.

Tunes on IN-SAMPLE only, then replays the leaders on OUT-OF-SAMPLE years the
search never touched. A config that wins in-sample and collapses out-of-sample
was fitted to noise - which is the thing this file exists to expose.

    uv run --with pandas --with numpy python strategy_search.py
"""

import itertools

import numpy as np
import pandas as pd

from backtest_voo import FEE, START_EQUITY, add_indicators, load

SPLIT = "2020-01-01"   # tune before this date, validate after

VARIANTS = {
    # momentum paper: hold while the trailing J-day return is positive
    "tsmom":       "long while mom>0 (+optional SMA200), exit when it flips",
    # thesis: buy local lows, sell into strength
    "dip":         "regime + close<SMA50 + RSI crossing up out of oversold",
    "dip_free":    "same dip entry, no momentum/SMA200 regime filter",
    # classic baseline neither paper proposes, included as a control
    "cross":       "long while SMA50 > SMA200",
}


def run(df, p):
    """Event-driven backtest. Signals read bar t, fills happen at t+1 open."""
    fee = p["fee"]
    equity, shares, entry_i, stop = START_EQUITY, 0, None, 0.0
    curve, in_mkt, n_trades = [], [], 0

    rows = df.itertuples()
    prev = next(rows)

    for i, bar in enumerate(rows, start=1):
        fill = bar.open

        regime_ok = prev.mom > 0 and (not p["use_sma200"] or prev.close > prev.sma200)

        if p["variant"] == "tsmom":
            want_in = regime_ok
        elif p["variant"] == "cross":
            want_in = prev.sma50 > prev.sma200
        elif p["variant"] == "dip":
            want_in = (regime_ok and prev.close < prev.sma50
                       and prev.rsi_prev < p["rsi_os"] <= prev.rsi)
        else:  # dip_free
            want_in = (prev.close < prev.sma50
                       and prev.rsi_prev < p["rsi_os"] <= prev.rsi)

        # ---- exits ----
        if shares > 0:
            held = i - entry_i
            px = reason = None
            if p["atr_stop"] and bar.low <= stop:
                px, reason = stop, "stop"
            elif p["variant"] in ("tsmom", "cross"):
                if not want_in:                       # trend gone
                    px, reason = fill, "signal"
            else:
                if prev.rsi_prev > p["rsi_ob"] >= prev.rsi:
                    px, reason = fill, "rsi"
                elif p["max_bars"] and held >= p["max_bars"]:
                    px, reason = fill, "time"
            if reason:
                equity += shares * px * (1 - fee)
                shares, entry_i = 0, None

        # ---- entries ----
        if shares == 0 and want_in and not np.isnan(prev.sma200) and not np.isnan(prev.atr):
            n = int(equity // (fill * (1 + fee)))     # full allocation, no leverage
            if n > 0:
                equity -= n * fill * (1 + fee)
                shares, entry_i = n, i
                stop = fill - prev.atr * p["atr_stop"] if p["atr_stop"] else 0.0
                n_trades += 1

        curve.append(equity + shares * bar.close)
        in_mkt.append(shares > 0)
        prev = bar

    return pd.Series(curve, index=df.index[1:]), n_trades, float(np.mean(in_mkt))


def metrics(curve, years):
    final = curve.iloc[-1]
    cagr = (final / START_EQUITY) ** (1 / years) - 1
    dd = (curve / curve.cummax() - 1).min()
    r = curve.pct_change().dropna()
    sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0
    return cagr, dd, sharpe


def bh(df, years):
    n = int(START_EQUITY // (df["open"].iloc[1] * (1 + FEE)))
    cash = START_EQUITY - n * df["open"].iloc[1] * (1 + FEE)
    return metrics(cash + n * df["close"].iloc[1:], years)


def yrs(df):
    return (df.index[-1] - df.index[0]).days / 365.25


def grid():
    """Parameter values come from the papers, not from a numeric sweep.

    J = 3/6/9/12 months are the momentum paper's formation periods; the RSI
    and MA settings are the thesis's. Sweeping arbitrary values would just
    widen the multiple-comparisons problem.
    """
    out = []
    for variant in VARIANTS:
        for lookback, use200, atr_stop in itertools.product(
                [63, 126, 189, 252], [True, False], [None, 2.0, 3.0]):
            if variant in ("tsmom", "cross"):
                out.append(dict(variant=variant, lookback=lookback,
                                use_sma200=use200, atr_stop=atr_stop,
                                rsi_os=35.0, rsi_ob=70.0, max_bars=None, fee=FEE))
            else:
                for rsi_os, max_bars in itertools.product([30.0, 35.0, 40.0],
                                                          [25, 50, None]):
                    out.append(dict(variant=variant, lookback=lookback,
                                    use_sma200=use200, atr_stop=atr_stop,
                                    rsi_os=rsi_os, rsi_ob=70.0,
                                    max_bars=max_bars, fee=FEE))
    return out


def prep(raw, lookback):
    df = add_indicators(raw)
    df["mom"] = df["close"] - df["close"].shift(lookback)
    return df.dropna(subset=["sma200", "atr", "rsi_prev", "mom"])


def main():
    raw = load()
    configs = grid()

    ins_raw = raw[raw.index < SPLIT]
    oos_raw = raw[raw.index >= SPLIT]

    # OOS needs warm-up history, so feed it the tail of the in-sample period.
    warm = raw[raw.index < SPLIT].tail(260)
    oos_raw = pd.concat([warm, oos_raw])

    print(f"configs tested : {len(configs)}")
    print(f"in-sample      : {ins_raw.index[0].date()} -> {ins_raw.index[-1].date()}")
    print(f"out-of-sample  : {oos_raw.index[260].date()} -> {oos_raw.index[-1].date()}\n")

    cache = {}
    results = []
    for p in configs:
        key = p["lookback"]
        if key not in cache:
            cache[key] = (prep(ins_raw, key), prep(oos_raw, key))
        ins, oos = cache[key]

        c_in, n_in, e_in = run(ins, p)
        cagr_in, dd_in, sh_in = metrics(c_in, yrs(ins))
        results.append((cagr_in, dd_in, sh_in, n_in, e_in, p))

    results.sort(key=lambda r: -r[0])

    ins_bh = bh(prep(ins_raw, 63), yrs(prep(ins_raw, 63)))
    print(f"IN-SAMPLE buy & hold : CAGR {ins_bh[0]:6.2%}  maxDD {ins_bh[1]:6.1%}  Sharpe {ins_bh[2]:.2f}")
    print("\nTop 10 in-sample:")
    print(f"{'variant':10s} {'J':>4s} {'200':>4s} {'stop':>5s} {'rsi':>5s} {'bars':>5s} "
          f"{'CAGR':>7s} {'maxDD':>7s} {'Shrp':>5s} {'trd':>4s} {'expo':>6s}")
    for cagr, dd, sh, n, e, p in results[:10]:
        print(f"{p['variant']:10s} {p['lookback']:>4d} {str(p['use_sma200'])[:1]:>4s} "
              f"{str(p['atr_stop']):>5s} {p['rsi_os']:>5.0f} {str(p['max_bars']):>5s} "
              f"{cagr:>7.2%} {dd:>7.1%} {sh:>5.2f} {n:>4d} {e:>6.1%}")

    print("\n--- the same 10 configs, replayed OUT-OF-SAMPLE ---")
    oos_prepped = prep(oos_raw, 63)
    oos_bh = bh(oos_prepped, yrs(oos_prepped))
    print(f"OOS buy & hold : CAGR {oos_bh[0]:6.2%}  maxDD {oos_bh[1]:6.1%}  Sharpe {oos_bh[2]:.2f}\n")
    print(f"{'variant':10s} {'J':>4s} {'IS CAGR':>8s} {'OOS CAGR':>9s} {'OOS DD':>7s} "
          f"{'OOS Shrp':>8s} {'beats B&H':>10s}")
    for cagr, dd, sh, n, e, p in results[:10]:
        _, oos = cache[p["lookback"]]
        c_out, n_out, e_out = run(oos, p)
        cagr_o, dd_o, sh_o = metrics(c_out, yrs(oos))
        print(f"{p['variant']:10s} {p['lookback']:>4d} {cagr:>8.2%} {cagr_o:>9.2%} "
              f"{dd_o:>7.1%} {sh_o:>8.2f} {'YES' if cagr_o > oos_bh[0] else 'no':>10s}")

    # How many of the whole grid clear buy & hold on ANY metric? This is a
    # census, not a selection - picking the best OOS performer would just be
    # overfitting to the holdout instead of the training set.
    beat_cagr = beat_sharpe = beat_dd = 0
    best_sh = None
    for _, _, _, _, _, p in results:
        _, oos = cache[p["lookback"]]
        c_out, _, e_out = run(oos, p)
        cagr_o, dd_o, sh_o = metrics(c_out, yrs(oos))
        beat_cagr += cagr_o > oos_bh[0]
        beat_sharpe += sh_o > oos_bh[2]
        beat_dd += dd_o > oos_bh[1]        # less negative = shallower drawdown
        if best_sh is None or sh_o > best_sh[0]:
            best_sh = (sh_o, cagr_o, dd_o, e_out, p)

    n = len(results)
    print(f"\n--- census over all {n} configs, out-of-sample ---")
    print(f"beat B&H on CAGR   : {beat_cagr:>4d} / {n}")
    print(f"beat B&H on Sharpe : {beat_sharpe:>4d} / {n}")
    print(f"beat B&H on drawdown: {beat_dd:>3d} / {n}")
    sh_o, cagr_o, dd_o, e_out, p = best_sh
    print(f"\nbest OOS Sharpe: {p['variant']} J={p['lookback']} stop={p['atr_stop']} "
          f"-> Sharpe {sh_o:.2f} (B&H {oos_bh[2]:.2f}), CAGR {cagr_o:.2%}, "
          f"DD {dd_o:.1%}, {e_out:.0%} in market")


if __name__ == "__main__":
    main()
