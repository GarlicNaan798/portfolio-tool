"""Proper backtest of the swing.py rule: is it stable, or one lucky stretch?

swing.py reports the full period. That is not a test - the instrument (WTI),
the rule (mean reversion) and the thresholds (40/70) were all chosen while
looking at full-sample results. This file tries to break that result.

Four attacks, in increasing order of how much they hurt:

1. SPLIT HALF      does the second half look like the first?
2. YEAR BY YEAR    is it consistent, or carried by a few years?
3. ROLLING SHARPE  what fraction of rolling 1-year windows are positive?
4. BLOCK BOOTSTRAP resample the daily returns in 20-day blocks 2000 times.
                   If the real Sharpe sits inside the bulk of that
                   distribution, it is indistinguishable from reordered luck.

An honest caveat this file cannot fix: because the instrument and rule were
selected after seeing the whole history, even the "second half" is not
genuinely out of sample. Consistency across sub-periods is evidence; it is
not proof.

    uv run --with yfinance --with pandas --with numpy python backtest.py
    uv run ... python backtest.py --symbol BZ=F --rule breakout
"""

import argparse

import numpy as np
import pandas as pd

from swing import (BPY, START_EQUITY, backtest, buy_hold, load, self_check,
                   stats)


def sharpe_of(returns):
    return (returns.mean() / returns.std() * np.sqrt(BPY)
            if len(returns) > 2 and returns.std() > 0 else 0.0)


def section(title):
    print(f"\n{'=' * 66}\n{title}\n{'=' * 66}")


def split_half(df, rule, fee):
    section("1. SPLIT HALF - does the second half resemble the first?")
    mid = df.index[len(df) // 2]
    for label, sub in (("first half ", df[df.index < mid]),
                       ("second half", df[df.index >= mid])):
        if len(sub) < 400:
            continue
        curve, trades, expo = backtest(sub, rule, fee)
        c, dd, sr, se, yrs = stats(curve)
        bc, bdd, bsr, _, _ = stats(buy_hold(sub, fee))
        print(f"{label}  {sub.index[0]:%Y-%m} to {sub.index[-1]:%Y-%m}  "
              f"CAGR {c:>7.2%}  maxDD {dd:>7.1%}  SR {sr:>5.2f}  "
              f"(B&H {bsr:>5.2f})  {len(trades):>4d} trades")
    print("\nA rule that works only in one half is a rule fitted to that half.")


def by_year(df, rule, fee):
    section("2. YEAR BY YEAR - consistent, or carried by a few years?")
    curve, _, _ = backtest(df, rule, fee)
    r = curve.pct_change().dropna()
    bh = buy_hold(df, fee).pct_change().dropna().reindex(r.index).fillna(0)

    rows = []
    for y, grp in r.groupby(r.index.year):
        if len(grp) < 100:
            continue
        strat = (1 + grp).prod() - 1
        hold = (1 + bh.loc[grp.index]).prod() - 1
        rows.append((y, strat, hold))

    print(f"{'year':>6s} {'strategy':>10s} {'buy&hold':>10s}   {'':4s}")
    for y, s, h in rows:
        mark = "win" if s > h else ""
        bar = "+" * min(int(abs(s) * 40), 28)
        print(f"{y:>6d} {s:>10.1%} {h:>10.1%}   {mark:4s} "
              f"{'' if s >= 0 else '-'}{bar}")

    wins = sum(1 for _, s, h in rows if s > h)
    pos = sum(1 for _, s, _ in rows if s > 0)
    print(f"\npositive years        {pos}/{len(rows)}")
    print(f"years beating B&H     {wins}/{len(rows)}")
    best = max(rows, key=lambda x: x[1])
    others = [s for y, s, _ in rows if y != best[0]]
    print(f"best year             {best[0]} at {best[1]:.1%}")
    print(f"CAGR excluding it     {(np.prod([1 + s for s in others]) ** (1 / max(len(others), 1)) - 1):.2%}")


def rolling(df, rule, fee, window=252):
    section(f"3. ROLLING {window}-DAY SHARPE - how often is it working?")
    curve, _, _ = backtest(df, rule, fee)
    r = curve.pct_change().dropna()
    roll = r.rolling(window).apply(
        lambda w: w.mean() / w.std() * np.sqrt(BPY) if w.std() > 0 else 0.0,
        raw=False).dropna()
    if roll.empty:
        print("not enough data")
        return
    print(f"windows            {len(roll)}")
    print(f"median             {roll.median():>6.2f}")
    print(f"25th / 75th pct    {roll.quantile(.25):>6.2f} / {roll.quantile(.75):.2f}")
    print(f"worst / best       {roll.min():>6.2f} / {roll.max():.2f}")
    print(f"fraction positive  {(roll > 0).mean():>6.0%}")
    print("\nA real edge is positive most of the time, not spectacular")
    print("occasionally. Look at the fraction, not the peak.")


def bootstrap(df, rule, fee, n=2000, block=20, seed=0):
    section(f"4. BLOCK BOOTSTRAP - {n} reshuffles in {block}-day blocks")
    curve, _, _ = backtest(df, rule, fee)
    r = curve.pct_change().dropna().values
    if len(r) < block * 5:
        print("not enough data")
        return

    real = r.mean() / r.std() * np.sqrt(BPY)
    rng = np.random.default_rng(seed)
    n_blocks = len(r) // block
    out = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, len(r) - block, n_blocks)
        samp = np.concatenate([r[s:s + block] for s in starts])
        out[i] = samp.mean() / samp.std() * np.sqrt(BPY) if samp.std() > 0 else 0.0

    lo, hi = np.percentile(out, [2.5, 97.5])
    print(f"actual Sharpe            {real:>6.2f}")
    print(f"bootstrap 95% interval   {lo:>6.2f} to {hi:.2f}")
    print(f"share of resamples <= 0  {(out <= 0).mean():>6.1%}")
    if lo > 0:
        print("\nThe interval excludes zero. Blocks preserve short-term")
        print("structure, so this is not merely reordered noise.")
    else:
        print("\nThe interval includes zero. Cannot rule out that the result")
        print("is an artifact of ordering.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="CL=F")
    p.add_argument("--rule", default="meanrev", choices=["meanrev", "breakout"])
    p.add_argument("--fee-bps", type=float, default=1.5)
    a = p.parse_args()

    self_check()
    fee = a.fee_bps / 10_000
    df = load(a.symbol)
    curve, trades, expo = backtest(df, a.rule, fee)
    c, dd, sr, se, yrs = stats(curve)
    bc, bdd, bsr, _, _ = stats(buy_hold(df, fee))

    print(f"\n{a.symbol}  rule={a.rule}  {a.fee_bps}bps/side  "
          f"{df.index[0]:%Y-%m} to {df.index[-1]:%Y-%m}  ({yrs:.1f}y)")
    print(f"full period:  CAGR {c:.2%}  maxDD {dd:.1%}  Sharpe {sr:.2f}  "
          f"(B&H {bsr:.2f})  {len(trades)} trades  {expo:.0%} in market")

    split_half(df, a.rule, fee)
    by_year(df, a.rule, fee)
    rolling(df, a.rule, fee)
    bootstrap(df, a.rule, fee)

    section("VERDICT")
    print("Read attacks 1-3 for stability and 4 for whether the ordering")
    print("matters. None of them fixes the selection problem: the instrument")
    print("and rule were chosen after seeing this history, so treat a good")
    print("result as 'not yet broken', not as 'proven'.")


if __name__ == "__main__":
    main()
