"""Does mean-reversion only work in bear regimes?

Tests the foundational claim of MR Swing (Abrams & Walker, NAAIM 2010):

    MR in BULL regime:  0.69% CAGR, Sharpe -0.09
    MR in BEAR regime: 11.89% CAGR, Sharpe  0.72

If that holds, every strategy in this project so far was mis-specified - we
applied one rule uniformly, including in regimes where it cannot work.

Three things the paper omits, all added here:
  * COSTS. The paper states "commissions and taxes are excluded, slippage
    is excluded" on a system doing ~400 trades. Cost decided the outcome of
    every earlier phase in this repo, so it is reported at 0, 5 and 25bps.
  * OUT OF SAMPLE. Their window ends 02/2010. Everything after is unseen.
  * Their window contains two of the largest bear markets on record, which
    is exactly the condition their bear-regime claim needs.

    uv run --with yfinance --with pandas --with numpy python mr_regime.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).parent / "data" / "cache"
BPY = 252
START = 100_000.0


def load(symbol="SPY"):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol}_1d.csv"
    if path.exists():
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        import yfinance as yf
        df = None
        for _ in range(3):
            try:
                got = yf.Ticker(symbol).history(period="max", interval="1d")
                if not got.empty:
                    df = got.rename(columns=str.lower)[["open","high","low","close"]]
                    df.index = df.index.tz_localize(None)
                    df.to_csv(path)
                    break
            except Exception:
                pass
            time.sleep(2)
        if df is None:
            sys.exit(f"could not fetch {symbol}")
    return df[df["close"] > 0]


def dv2(df, lookback=252):
    """David Varadi Oscillator (DV2), the paper's mean-reversion metric.

    Close relative to the bar's midpoint, smoothed over 2 days, then
    percentile-ranked over a year. Percentile ranking is what makes it
    volatility-adaptive - it assumes nothing about the return distribution,
    which is the paper's third design principle.
    """
    mid = (df["high"] + df["low"]) / 2.0
    rel = df["close"] / mid - 1.0
    smooth = rel.rolling(2).mean()
    return smooth.rolling(lookback).apply(
        lambda w: (w[-1] > w[:-1]).sum() / (len(w) - 1) * 100.0, raw=True)


def run(df, regime, fee, buy_below=40.0, sell_above=70.0):
    """Long-only DV2 mean reversion, restricted to one regime.

    regime: "bull" (close > SMA200), "bear" (close < SMA200), or "all".
    Signals read bar t; fills at bar t+1 open.
    """
    d = df.copy()
    d["dv2"] = dv2(d)
    d["sma200"] = d["close"].rolling(200).mean()
    d = d.dropna(subset=["dv2", "sma200"])
    if len(d) < 300:
        return None

    equity, shares = START, 0
    curve, in_mkt = [], []
    rows = list(d.itertuples())

    for i in range(1, len(rows)):
        prev, bar = rows[i - 1], rows[i]
        fill = bar.open
        bull = prev.close > prev.sma200
        allowed = regime == "all" or (regime == "bull") == bull

        if shares > 0 and (prev.dv2 > sell_above or not allowed):
            equity += shares * fill * (1 - fee)
            shares = 0
        elif shares == 0 and allowed and prev.dv2 < buy_below:
            n = int(equity // (fill * (1 + fee)))
            if n > 0:
                equity -= n * fill * (1 + fee)
                shares = n

        curve.append(equity + shares * bar.close)
        in_mkt.append(shares > 0)

    return pd.Series(curve, index=d.index[1:]), float(np.mean(in_mkt))


def stats(curve):
    years = len(curve) / BPY
    cagr = (curve.iloc[-1] / START) ** (1 / max(years, 0.1)) - 1
    dd = (curve / curve.cummax() - 1).min()
    r = curve.pct_change().dropna()
    sr = r.mean() / r.std() * np.sqrt(BPY) if r.std() > 0 else 0.0
    return cagr, dd, sr


def self_check():
    """DV2 must be a bounded percentile ranking the close's position INSIDE
    the bar, not the trend.

    A steady uptrend with identically-shaped bars has a constant
    close-vs-midpoint ratio, so ranking it is degenerate - that is correct
    behaviour, and an earlier version of this check wrongly asserted the
    opposite. Vary the bar shapes instead.
    """
    rng = np.random.default_rng(0)
    n = 600
    idx = pd.date_range("2010-01-01", periods=n, freq="B")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=idx)
    span = close * 0.02
    frac = pd.Series(rng.uniform(0, 1, n), index=idx)
    low = close - span * frac
    high = low + span
    df = pd.DataFrame({"open": close, "high": high, "low": low, "close": close})

    v = dv2(df).dropna()
    assert len(v) > 100, "self-check: DV2 produced too few values"
    assert v.between(0, 100).all(), "self-check: DV2 outside 0-100"

    mid = (df["high"] + df["low"]) / 2.0
    raw = (df["close"] / mid - 1.0).rolling(2).mean()
    c = v.corr(raw.loc[v.index])
    assert c > 0.5, f"self-check: DV2 does not track its input (corr {c:.2f})"
    print(f"self-check: PASS (DV2 spans {v.min():.0f}-{v.max():.0f}, corr {c:.2f})")
    print()


def main():
    self_check()
    df = load("SPY")
    windows = {
        "their sample 2000-2010": ("2000-02-01", "2010-02-12"),
        "OUT OF SAMPLE 2010-2026": ("2010-02-13", "2026-12-31"),
    }

    for label, (lo, hi) in windows.items():
        sub = df[(df.index >= lo) & (df.index <= hi)]
        if len(sub) < 400:
            continue
        bh = sub["close"] / sub["close"].iloc[0] * START
        bc, bdd, bsr = stats(bh)
        print(f"=== {label} ===")
        print(f"{'':22s} {'CAGR':>8s} {'maxDD':>8s} {'Sharpe':>7s} {'expo':>6s}")
        print(f"{'buy & hold':22s} {bc:>8.2%} {bdd:>8.1%} {bsr:>7.2f} {1.0:>6.0%}")
        for fee_bps in (0, 5, 25):
            fee = fee_bps / 10_000
            for regime in ("bull", "bear", "all"):
                out = run(sub, regime, fee)
                if out is None:
                    continue
                curve, expo = out
                c, dd, sr = stats(curve)
                print(f"{f'MR in {regime} @{fee_bps}bps':22s} {c:>8.2%} "
                      f"{dd:>8.1%} {sr:>7.2f} {expo:>6.0%}")
        print()

    print("Paper's claim: MR in bull Sharpe -0.09, MR in bear Sharpe 0.72.")
    print("Paper charges zero costs and its sample ends 02/2010.")


if __name__ == "__main__":
    main()
