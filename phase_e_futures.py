"""Phase E: trend following on the paper's actual universe, with a control.

31 futures across six sectors, 26 years. Two things are being tested:

  1. Does trend following work on futures where it failed on equity ETFs?
  2. Can this engine detect a real effect at all?

(2) matters more. The literature is clear that trend following worked
before 2009 and decayed sharply after. If the engine finds the effect in
era A and not era B, it is working and the decay is real. If it finds
nothing in era A either, the engine is broken and every earlier negative
result in this repo needs re-examining before it is believed.

Reuses the Phase D signal exactly - Donchian breakout, trailing ATR stop,
inverse-volatility sizing, long and short - so the only thing that changes
is the universe.

    uv run --with yfinance --with pandas --with numpy python phase_e_futures.py
"""

import itertools

import numpy as np
import pandas as pd

from swing_lab import fetch
from phase_d_trend import metrics, sleeve

SECTORS = {
    "rates":  ["ZN=F", "ZF=F", "ZT=F"],
    "fx":     ["6E=F", "6J=F", "6B=F", "6A=F", "6C=F", "6S=F"],
    "energy": ["CL=F", "NG=F", "HO=F", "RB=F", "BZ=F"],
    "metals": ["GC=F", "SI=F", "HG=F", "PL=F", "PA=F"],
    "ags":    ["ZC=F", "ZW=F", "ZS=F", "SB=F", "KC=F", "CT=F", "CC=F",
               "LE=F", "HE=F"],
    "equity": ["ES=F", "NQ=F", "YM=F"],
}

ERAS = {
    "A 2001-2008 (pre-decay)": ("2001-01-01", "2008-12-31"),
    "B 2010-2026 (post-decay)": ("2010-01-01", "2026-12-31"),
}

GATE_A = 0.5      # era A must clear this for the engine to be trusted
FLOOR_A = 0.2     # below this, the engine is suspect

# Per side. Futures are ~1-2bps all-in; the 25bps used for equity ETFs is a
# 25x overcharge here and on its own flips this strategy from working to
# losing. Reported at two levels so the sensitivity is visible.
FEE_FUT = 0.00015
FEE_FUT_PESSIMISTIC = 0.0005


def load():
    frames, by_sector = {}, {}
    for sector, tickers in SECTORS.items():
        got = []
        for t in tickers:
            df = fetch(t, "1d")
            if df is not None and len(df) > 2000:
                frames[t] = df
                got.append(t)
        by_sector[sector] = got
        print(f"  {sector:8s} {len(got)}/{len(tickers)}")
    return frames, by_sector


def era_returns(frames, p, lo, hi, fee=FEE_FUT):
    sleeves = {}
    for t, df in frames.items():
        sub = df[(df.index >= lo) & (df.index <= hi)]
        if len(sub) < 400:
            continue
        sleeves[t] = sleeve(sub, p, fee=fee)
    if not sleeves:
        return None
    return pd.DataFrame(sleeves).fillna(0.0).mean(axis=1)


def main():
    print("PHASE E - futures universe with a positive control\n")
    frames, by_sector = load()
    print(f"\nloaded {len(frames)} markets\n")

    configs = [dict(entry_n=e, exit_n=x, atr_mult=a, short=s)
               for e, x, a, s in itertools.product(
                   [20, 55, 100], [10, 20], [2.0, 3.0], [True, False])]

    print(f"{'entry':>6s} {'exit':>5s} {'atr':>4s} {'shrt':>5s}"
          f" | {'A CAGR':>8s} {'A DD':>7s} {'A Shrp':>7s}"
          f" | {'B CAGR':>8s} {'B DD':>7s} {'B Shrp':>7s}")
    rows = []
    for p in configs:
        out = {}
        for era, (lo, hi) in ERAS.items():
            r = era_returns(frames, p, lo, hi)
            out[era] = metrics(r) if r is not None else None
        if any(v is None for v in out.values()):
            continue
        a = out["A 2001-2008 (pre-decay)"]
        b = out["B 2010-2026 (post-decay)"]
        rows.append((a, b, p))
        print(f"{p['entry_n']:>6d} {p['exit_n']:>5d} {p['atr_mult']:>4.1f} "
              f"{str(p['short'])[:1]:>5s} | {a[0]:>8.2%} {a[1]:>7.1%} {a[2]:>7.2f}"
              f" | {b[0]:>8.2%} {b[1]:>7.1%} {b[2]:>7.2f}")

    if not rows:
        print("no results")
        return

    best_a = max(r[0][2] for r in rows)
    mean_a = float(np.mean([r[0][2] for r in rows]))
    mean_b = float(np.mean([r[1][2] for r in rows]))
    ls = [r for r in rows if r[2]["short"]]
    lo_ = [r for r in rows if not r[2]["short"]]

    print(f"\nera A  best Sharpe {best_a:>5.2f}   mean {mean_a:>5.2f}")
    print(f"era B  mean Sharpe  {mean_b:>5.2f}")
    if ls and lo_:
        print(f"\nlong+short  A {np.mean([r[0][2] for r in ls]):>5.2f}   "
              f"B {np.mean([r[1][2] for r in ls]):>5.2f}")
        print(f"long only   A {np.mean([r[0][2] for r in lo_]):>5.2f}   "
              f"B {np.mean([r[1][2] for r in lo_]):>5.2f}")

    # Cost sensitivity on the best in-sample config, since this is exactly
    # what was mis-specified the first time this phase ran.
    best = max(rows, key=lambda r: r[0][2])[2]
    print("\ncost sensitivity, best era-A config:")
    for bps in (1.5, 5, 10, 25):
        ra = era_returns(frames, best, *ERAS["A 2001-2008 (pre-decay)"], fee=bps / 10000)
        rb = era_returns(frames, best, *ERAS["B 2010-2026 (post-decay)"], fee=bps / 10000)
        print(f"  {bps:>4.1f}bps/side  era A Sharpe {metrics(ra)[2]:>+5.2f}   "
              f"era B Sharpe {metrics(rb)[2]:>+5.2f}")

    print("\n" + "=" * 62)
    if best_a > GATE_A and mean_a > mean_b:
        print("OUTCOME 1 - engine validated, decay confirmed.")
        print("Trend following worked pre-2009 and weakened after, exactly as")
        print("the literature reports. Earlier negative results stand as")
        print("findings about the market, not bugs in the code.")
    elif best_a > GATE_A and mean_b > GATE_A:
        print("OUTCOME 3 - it works in BOTH eras on futures.")
        print("The instrument universe was the problem; the ETF results do")
        print("not generalise.")
    elif best_a <= FLOOR_A:
        print("OUTCOME 2 - THE ENGINE IS SUSPECT.")
        print("It cannot find an effect that is known to be there. Every")
        print("earlier negative result needs re-examining before it is")
        print("believed. This invalidates the programme, not the market.")
    else:
        print("AMBIGUOUS - era A is weak but not absent. Treat earlier")
        print("negative results as provisional.")
    print("=" * 62)


if __name__ == "__main__":
    main()
