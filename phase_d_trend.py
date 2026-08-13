"""Phase D: trend following the way managed futures actually runs it.

Four things separate this from the `tsmom` variant already falsified in
swing_lab.py, and all four matter:

  long AND short      - a downtrend is a profit, not a trip to cash
  inverse-vol sizing  - each instrument contributes equal risk
  trailing stop       - ratchets up behind price, so winners can run
  breakout entry      - a new N-day high, not a "trend is up" state

Judged as a diversified portfolio, which is how the strategy is actually
run. Individual trend followers lose most of the time; the claim is that
the basket is positive.

    uv run --with yfinance --with pandas --with numpy python phase_d_trend.py
"""

import itertools

import numpy as np
import pandas as pd

from swing_lab import FEE, UNIVERSE_1D, fetch

SPLIT = "2020-01-01"
BPY = 252
VOL_TARGET = 0.10        # annualised, per instrument sleeve
GATE_SHARPE = 0.83       # SPY
GATE_CAGR = 0.05


def signals(df, entry_n, exit_n, atr_mult, allow_short):
    """Donchian breakout with a trailing ATR stop. Returns position in
    {-1, 0, +1} per bar, already lagged so bar t's position was decided
    on bar t-1's close."""
    high, low, close = df["high"], df["low"], df["close"]

    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()],
                   axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()

    up = high.rolling(entry_n).max().shift(1)
    dn = low.rolling(entry_n).min().shift(1)
    exit_dn = low.rolling(exit_n).min().shift(1)
    exit_up = high.rolling(exit_n).max().shift(1)

    pos = np.zeros(len(df))
    state, stop = 0, np.nan
    c = close.values
    h, l = high.values, low.values
    a = atr.values

    for i in range(len(df)):
        if np.isnan(up.values[i]) or np.isnan(a[i]):
            pos[i] = 0
            continue

        if state == 1:
            stop = max(stop, c[i] - atr_mult * a[i])      # ratchet only up
            if l[i] <= stop or c[i] < exit_dn.values[i]:
                state = 0
        elif state == -1:
            stop = min(stop, c[i] + atr_mult * a[i])
            if h[i] >= stop or c[i] > exit_up.values[i]:
                state = 0

        if state == 0:
            if c[i] > up.values[i]:
                state, stop = 1, c[i] - atr_mult * a[i]
            elif allow_short and c[i] < dn.values[i]:
                state, stop = -1, c[i] + atr_mult * a[i]

        pos[i] = state

    # decided on bar i's close -> held from bar i+1
    return pd.Series(pos, index=df.index).shift(1).fillna(0.0)


def sleeve(df, p, fee=None):
    """One instrument's return stream, scaled to a constant risk budget.

    `fee` is per side and MUST match the asset class. Charging an ETF's 25bps
    to a futures contract (~1-2bps) is a 25x overcharge that turns a working
    strategy into a losing one - see the Phase E correction.
    """
    fee = FEE if fee is None else fee
    pos = signals(df, p["entry_n"], p["exit_n"], p["atr_mult"], p["short"])
    ret = df["close"].pct_change().fillna(0.0)

    # ponytail: winsorise instead of back-adjusting. Yahoo's continuous
    # futures are unadjusted front-month, so rolls appear as fake returns and
    # CL=F even crosses zero in April 2020 (pct_change -> -306%). Proper
    # back-adjusted series are not freely available; clip at +/-25% to stop
    # single artifacts dominating. Upgrade path: paid roll-adjusted data.
    ret = ret.replace([np.inf, -np.inf], 0.0).clip(-0.25, 0.25)

    realised = ret.rolling(63).std() * np.sqrt(BPY)
    scale = (VOL_TARGET / realised).clip(upper=3.0).shift(1).fillna(0.0)

    gross = pos * scale * ret
    turn = (pos * scale).diff().abs().fillna(0.0)
    return gross - turn * fee


def metrics(r):
    eq = (1 + r).cumprod()
    years = len(r) / BPY
    cagr = eq.iloc[-1] ** (1 / max(years, 0.1)) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = r.mean() / r.std() * np.sqrt(BPY) if r.std() > 0 else 0.0
    return cagr, dd, sharpe


def portfolio(frames, p):
    sleeves = {t: sleeve(df, p) for t, df in frames.items()}
    return pd.DataFrame(sleeves).dropna(how="all").fillna(0.0).mean(axis=1)


def main():
    print("PHASE D - trend following, portfolio level")
    print(f"gates: OOS Sharpe > {GATE_SHARPE}, OOS CAGR > {GATE_CAGR:.0%}\n")

    frames = {}
    for t in UNIVERSE_1D:
        df = fetch(t, "1d")
        if df is not None and len(df) > 800:
            frames[t] = df
    print(f"universe: {len(frames)} instruments\n")

    spy = fetch("SPY", "1d")["close"].pct_change().fillna(0.0)
    spy_oos = spy[spy.index >= SPLIT]
    spy_m = metrics(spy_oos)

    configs = [dict(entry_n=e, exit_n=x, atr_mult=a, short=s)
               for e, x, a, s in itertools.product(
                   [20, 55, 100], [10, 20], [2.0, 3.0], [True, False])]

    rows = []
    for p in configs:
        r = portfolio(frames, p)
        ins = r[r.index < SPLIT]
        oos = r[r.index >= SPLIT]
        if len(ins) < 400 or len(oos) < 200:
            continue
        rows.append((metrics(ins), metrics(oos), p))

    # rank in-sample only; the holdout is scored, never used to choose
    rows.sort(key=lambda x: -x[0][2])

    print(f"{'entry':>6s} {'exit':>5s} {'atr':>4s} {'short':>6s} "
          f"{'IS Shrp':>8s} {'OOS CAGR':>9s} {'OOS DD':>7s} {'OOS Shrp':>9s}")
    for (ic, idd, ish), (oc, odd, osh), p in rows[:12]:
        print(f"{p['entry_n']:>6d} {p['exit_n']:>5d} {p['atr_mult']:>4.1f} "
              f"{str(p['short'])[:1]:>6s} {ish:>8.2f} {oc:>9.2%} {odd:>7.1%} "
              f"{osh:>9.2f}")

    print(f"\nSPY (benchmark)  CAGR {spy_m[0]:.2%}  maxDD {spy_m[1]:.1%}  "
          f"Sharpe {spy_m[2]:.2f}")

    # long-short vs long-only, averaged, to isolate the short side
    for flag, label in ((True, "long+short"), (False, "long only")):
        sub = [r for r in rows if r[2]["short"] is flag]
        if sub:
            print(f"{label:12s} mean OOS Sharpe "
                  f"{np.mean([r[1][2] for r in sub]):>5.2f}   "
                  f"mean OOS CAGR {np.mean([r[1][0] for r in sub]):>6.2%}")

    best_is = rows[0]
    (oc, odd, osh) = best_is[1]
    print("\n=== GATE (config chosen in-sample) ===")
    c1, c2 = osh > GATE_SHARPE, oc > GATE_CAGR
    print(f"   [{'x' if c1 else ' '}] OOS Sharpe {osh:.2f} > {GATE_SHARPE}")
    print(f"   [{'x' if c2 else ' '}] OOS CAGR {oc:.2%} > {GATE_CAGR:.0%}")

    n_beat = sum(1 for r in rows if r[1][2] > GATE_SHARPE)
    print(f"\ncensus: {n_beat}/{len(rows)} configs beat SPY's Sharpe OOS")

    print("\n" + "=" * 58)
    print("PHASE D PASSED" if (c1 and c2) else "PHASE D FAILED")
    print("=" * 58)


if __name__ == "__main__":
    main()
