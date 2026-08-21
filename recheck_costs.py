"""Re-run the core ETF conclusion at realistic costs.

findings/paper-strategies-do-not-beat-buy-and-hold.md was established with
FEE = 25bps per side, inherited from the Sarainmaa thesis. For liquid US
ETFs at a modern broker that is 10-100x too high: SPY's spread is about a
cent on a ~$600 share, with zero commission.

Cost has already flipped two conclusions in this repo. This checks whether
it flipped a third - the headline negative the whole project rests on.

Same universe, same variants, same out-of-sample split as the original.
Only the fee changes.

    uv run --with yfinance --with pandas --with numpy python recheck_costs.py
"""

import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).parent / "data" / "cache"
BPY = 252
START = 10_000.0
SPLIT = "2020-01-01"

UNIVERSE = ["GLD", "SLV", "USO", "UNG", "DBA", "DBC", "CPER",
            "SPY", "QQQ", "IWM", "EFA", "EEM",
            "TLT", "IEF", "HYG", "UUP", "FXE", "FXY",
            "XLE", "XLF", "XLK", "XLU"]

FEES_BPS = [0.0, 2.0, 5.0, 25.0]


def load(sym):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{sym}_1d.csv"
    if p.exists():
        return pd.read_csv(p, index_col=0, parse_dates=True)
    import yfinance as yf
    for _ in range(3):
        try:
            g = yf.Ticker(sym).history(period="max", interval="1d")
            if not g.empty:
                d = g.rename(columns=str.lower)[["open", "high", "low", "close"]]
                d.index = d.index.tz_localize(None)
                d.to_csv(p)
                return d
        except Exception:
            pass
        time.sleep(2)
    return None


def indicators(df, lookback):
    d = df.copy()
    d["sma50"] = d["close"].rolling(50).mean()
    d["sma200"] = d["close"].rolling(200).mean()
    d["mom"] = d["close"] - d["close"].shift(lookback)

    delta = d["close"].diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50)
    d["rsi_prev"] = d["rsi"].shift(1)

    mid = (d["high"] + d["low"]) / 2.0
    rel = (d["close"] / mid - 1.0).rolling(2).mean()
    d["dv2"] = rel.rolling(252).apply(
        lambda w: (w[-1] > w[:-1]).sum() / (len(w) - 1) * 100.0, raw=True)
    return d.dropna(subset=["sma200", "mom", "rsi_prev"])


def run(d, variant, fee, rsi_os=35.0):
    """Long only, full allocation. Signal on bar t, fill at t+1 open."""
    eq, sh = START, 0
    curve = []
    rows = list(d.itertuples())
    for i in range(1, len(rows)):
        p, b = rows[i - 1], rows[i]
        fill = b.open
        bull = p.mom > 0 and p.close > p.sma200

        if variant == "tsmom":
            want = bull
        elif variant == "cross":
            want = p.sma50 > p.sma200
        elif variant == "dip":
            want = bull and p.close < p.sma50 and p.rsi_prev < rsi_os <= p.rsi
        elif variant == "dv2":
            want = (not np.isnan(p.dv2)) and p.dv2 < 40.0
        else:
            want = False

        if variant in ("dip",):
            hold = sh > 0 and not (p.rsi_prev > 70 >= p.rsi)
            want = want or hold
        if variant == "dv2":
            if sh > 0 and not (not np.isnan(p.dv2) and p.dv2 > 70.0):
                want = True

        if sh > 0 and not want:
            eq += sh * fill * (1 - fee)
            sh = 0
        elif sh == 0 and want:
            n = int(eq // (fill * (1 + fee)))
            if n > 0:
                eq -= n * fill * (1 + fee)
                sh = n
        curve.append(eq + sh * b.close)
    return pd.Series(curve, index=d.index[1:])


def sharpe(c):
    r = c.pct_change().dropna()
    return r.mean() / r.std() * np.sqrt(BPY) if r.std() > 0 else 0.0


def cagr(c):
    return (c.iloc[-1] / START) ** (1 / max(len(c) / BPY, 0.1)) - 1


def main():
    data = {}
    for s in UNIVERSE:
        d = load(s)
        if d is not None and len(d) > 900:
            data[s] = d
    print(f"universe: {len(data)} ETFs, OOS from {SPLIT}\n")
    if not data:
        sys.exit("no data")

    configs = [(v, lb) for v, lb in itertools.product(
        ("tsmom", "cross", "dip", "dv2"), (63, 126, 189, 252))]

    print(f"{'fee':>6s}  {'variant':8s} {'J':>4s}  {'beat B&H':>9s}  "
          f"{'mean SR':>8s}  {'B&H mean SR':>11s}")
    print("-" * 60)

    best_by_fee = {}
    for fee_bps in FEES_BPS:
        fee = fee_bps / 10_000
        rows = []
        for variant, lb in configs:
            wins, srs, bsrs = 0, [], []
            for s, df in data.items():
                d = indicators(df, lb)
                oos = d[d.index >= SPLIT]
                if len(oos) < 300:
                    continue
                c = run(oos, variant, fee)
                bh = oos["close"] / oos["close"].iloc[0] * START
                s_sr, b_sr = sharpe(c), sharpe(bh)
                srs.append(s_sr)
                bsrs.append(b_sr)
                wins += cagr(c) > cagr(bh)
            if srs:
                rows.append((wins, variant, lb, np.mean(srs), np.mean(bsrs)))
        rows.sort(key=lambda r: -r[0])
        best_by_fee[fee_bps] = rows[0]
        for wins, v, lb, msr, mbsr in rows[:3]:
            print(f"{fee_bps:>5.0f}b  {v:8s} {lb:>4d}  {wins:>4d}/{len(data):<4d}  "
                  f"{msr:>8.2f}  {mbsr:>11.2f}")
        print()

    print("=" * 60)
    print("headline: the original finding recorded 6/22 at 25bps.")
    for f, (w, v, lb, msr, _) in best_by_fee.items():
        print(f"  at {f:>4.0f}bps -> best is {v} J={lb}, beats B&H on {w}/{len(data)}")


if __name__ == "__main__":
    main()
