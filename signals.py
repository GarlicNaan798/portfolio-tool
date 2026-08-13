"""Daily signal report for the validated futures trend system.

This is the operational end of the research, not a new strategy. It runs the
one configuration that survived every phase:

    Donchian 100-bar breakout entry, 20-bar exit
    trailing ATR stop at 3.0x
    LONG ONLY - the short leg lost in every test (see
    findings/shorting-hurts-trend-following.md)
    inverse-volatility sizing to a 10% per-market risk budget
    31 futures across rates, FX, energy, metals, ags, equity indexes

Be clear about what it is: era B (2010-2026) Sharpe 0.41, max drawdown
-4.2%. That is below SPY's 0.83 and it is a diversifier, not an index
replacement. See findings/phase-e-validated-the-engine.md.

    uv run --with yfinance --with pandas --with numpy python signals.py
    uv run ... python signals.py --refresh --account 100000
"""

import argparse
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from swing_lab import CACHE, fetch
from phase_d_trend import VOL_TARGET, signals as trend_signals
from phase_e_futures import FEE_FUT, SECTORS

# The Phase E winner, chosen on era A (the control) and never on era B.
CONFIG = dict(entry_n=100, exit_n=20, atr_mult=3.0, short=False)
BPY = 252

NAMES = {
    "ZN=F": "10Y T-Note", "ZF=F": "5Y T-Note", "ZT=F": "2Y T-Note",
    "6E=F": "Euro FX", "6J=F": "Japanese Yen", "6B=F": "British Pound",
    "6A=F": "Australian $", "6C=F": "Canadian $", "6S=F": "Swiss Franc",
    "CL=F": "WTI Crude", "NG=F": "Natural Gas", "HO=F": "Heating Oil",
    "RB=F": "RBOB Gasoline", "BZ=F": "Brent Crude",
    "GC=F": "Gold", "SI=F": "Silver", "HG=F": "Copper",
    "PL=F": "Platinum", "PA=F": "Palladium",
    "ZC=F": "Corn", "ZW=F": "Wheat", "ZS=F": "Soybeans", "SB=F": "Sugar",
    "KC=F": "Coffee", "CT=F": "Cotton", "CC=F": "Cocoa",
    "LE=F": "Live Cattle", "HE=F": "Lean Hogs",
    "ES=F": "S&P 500", "NQ=F": "Nasdaq 100", "YM=F": "Dow",
}


def clear_cache():
    """Signals are worthless on stale prices, so --refresh is not optional
    hygiene - it is the difference between today's book and last week's."""
    n = 0
    for f in CACHE.glob("*_1d.csv"):
        f.unlink()
        n += 1
    return n


def atr_of(df, n=14):
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                    (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def analyse(ticker, df):
    """Current state of one market. Returns None if history is too short."""
    if df is None or len(df) < 300:
        return None

    pos = trend_signals(df, CONFIG["entry_n"], CONFIG["exit_n"],
                        CONFIG["atr_mult"], CONFIG["short"])
    if pos.iloc[-1] == 0:
        state = "flat"
    else:
        state = "LONG"

    ret = df["close"].pct_change().replace([np.inf, -np.inf], 0.0).clip(-.25, .25)
    realised = float(ret.rolling(63).std().iloc[-1] * np.sqrt(BPY))
    weight = 0.0 if realised <= 0 else min(VOL_TARGET / realised, 3.0)

    # bars since the position last changed
    changed = (pos != pos.shift(1))
    since = int(len(pos) - 1 - np.max(np.where(changed.values)[0])) \
        if changed.any() else len(pos)

    close = float(df["close"].iloc[-1])
    atr = float(atr_of(df).iloc[-1])
    hi = float(df["high"].rolling(CONFIG["entry_n"]).max().shift(1).iloc[-1])

    stop = np.nan
    if state == "LONG":
        # Reconstruct the ratchet over the life of the trade.
        seg = df.iloc[-since - 1:] if since < len(df) else df
        stop = float((seg["close"] - CONFIG["atr_mult"] * atr_of(df).loc[seg.index]).cummax().iloc[-1])

    return dict(ticker=ticker, name=NAMES.get(ticker, ticker), state=state,
                close=close, atr=atr, vol=realised, weight=weight,
                bars=since, stop=stop, breakout=hi,
                to_breakout=(hi / close - 1.0) if close else np.nan,
                to_stop=(close / stop - 1.0) if state == "LONG" and stop > 0 else np.nan,
                asof=df.index[-1])


def self_check():
    """One runnable check: a synthetic uptrend must produce a LONG, and a
    flat series must produce no position. If this fails the signal logic is
    broken and the report is noise."""
    idx = pd.date_range("2020-01-01", periods=400, freq="B")

    # The ramp must out-run its own intrabar range, or the breakout level
    # sits permanently above the next close and nothing can ever trigger.
    up = pd.Series(np.linspace(100, 1000, 400), index=idx)
    trend_df = pd.DataFrame({"open": up, "high": up * 1.001,
                             "low": up * 0.999, "close": up})
    r = analyse("TEST", trend_df)
    assert r and r["state"] == "LONG", "self-check: uptrend did not go long"

    flat = pd.Series(100.0, index=idx)
    flat_df = pd.DataFrame({"open": flat, "high": flat, "low": flat,
                            "close": flat})
    r2 = analyse("TEST", flat_df)
    assert r2 and r2["state"] == "flat", "self-check: flat series took a position"
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="drop the daily cache and re-download")
    ap.add_argument("--account", type=float, default=100_000,
                    help="account size for notional sizing")
    args = ap.parse_args()

    if not self_check():
        sys.exit("self-check failed")
    print("self-check: PASS")

    if args.refresh:
        print(f"cleared {clear_cache()} cached files, re-downloading\n")

    rows = []
    for sector, tickers in SECTORS.items():
        for t in tickers:
            r = analyse(t, fetch(t, "1d"))
            if r:
                r["sector"] = sector
                rows.append(r)

    if not rows:
        sys.exit("no data")

    stale = max(r["asof"] for r in rows)
    print(f"TREND SIGNALS  -  data through {stale:%Y-%m-%d}  "
          f"(generated {datetime.now():%Y-%m-%d %H:%M})")
    print(f"config: Donchian {CONFIG['entry_n']}/{CONFIG['exit_n']}, "
          f"{CONFIG['atr_mult']}x ATR trailing stop, long only, "
          f"{VOL_TARGET:.0%} vol target\n")

    longs = [r for r in rows if r["state"] == "LONG"]
    total_w = sum(r["weight"] for r in longs)

    print(f"{'market':16s} {'sector':8s} {'signal':>6s} {'close':>10s} "
          f"{'stop':>10s} {'to stop':>8s} {'wt':>6s} {'notional':>11s} {'bars':>5s}")
    print("-" * 96)
    for r in sorted(rows, key=lambda x: (x["state"] != "LONG", x["sector"])):
        if r["state"] == "LONG":
            notional = args.account * r["weight"] / max(len(longs), 1)
            print(f"{r['name']:16s} {r['sector']:8s} {r['state']:>6s} "
                  f"{r['close']:>10.2f} {r['stop']:>10.2f} "
                  f"{r['to_stop']:>7.1%} {r['weight']:>6.2f} "
                  f"{notional:>11,.0f} {r['bars']:>5d}")
    print("-" * 96)

    flats = [r for r in rows if r["state"] == "flat"]
    near = sorted(flats, key=lambda x: x["to_breakout"])[:5]
    print(f"\n{len(longs)} long / {len(rows)} markets   "
          f"gross weight {total_w:.2f}")
    print("\nclosest to triggering (distance to the 100-bar high):")
    for r in near:
        print(f"  {r['name']:16s} {r['close']:>10.2f}  needs "
              f"{r['to_breakout']:>+6.1%} to {r['breakout']:.2f}")

    print("\nNotional is a target dollar exposure, not a contract count -")
    print("converting needs each contract's multiplier, which is exchange")
    print("specific and not in the price feed. Sizing assumes no leverage")
    print("beyond the vol target.")


if __name__ == "__main__":
    main()
