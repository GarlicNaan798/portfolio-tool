"""Cross-sectional momentum: rank the universe, hold the leaders, rotate.

The other arm of Bird/Gao/Yeung. Everything tested so far is TIME-SERIES
momentum - each instrument judged against its own past, held or not. That
fails on a rising asset because "not held" means cash, and cash earns
nothing while the asset compounds.

Cross-sectional keeps capital deployed: it always owns *something*, namely
whatever has been strongest. Optionally gated by absolute momentum, which is
the hybrid the literature usually finds strongest.

Benchmarks are equal-weight buy & hold of the same universe (the honest
comparison for a rotation strategy) and SPY.

    uv run --with yfinance --with pandas --with numpy python cross_sectional.py
"""

import itertools

import numpy as np
import pandas as pd

from swing_lab import FEE, START_EQUITY, UNIVERSE_1D, fetch

SPLIT = "2020-01-01"


def panel(tickers):
    """Close prices aligned on dates every instrument has."""
    cols = {}
    for t in tickers:
        df = fetch(t, "1d")
        if df is not None and len(df) > 600:
            cols[t] = df["close"]
    px = pd.DataFrame(cols).dropna()
    return px


def run(px, j, top_n, rebal, gap=0, absolute=False, fee=FEE):
    """Rebalance every `rebal` bars into the top_n by J-bar return.

    gap=1 skips the most recent month when measuring momentum (the standard
    short-term-reversal control). absolute=True holds cash instead of a
    leader whose own momentum is negative.
    """
    equity = START_EQUITY
    weights = pd.Series(0.0, index=px.columns)
    curve = []
    n_rebal = 0

    rets = px.pct_change().fillna(0.0)
    lookback_end = -gap * 21 if gap else None

    for i in range(len(px)):
        if i > 0:
            equity *= 1.0 + float((weights * rets.iloc[i]).sum())

        if i >= j + gap * 21 and i % rebal == 0:
            past = px.iloc[i - j - (gap * 21):(i - gap * 21) if gap else i]
            mom = past.iloc[-1] / past.iloc[0] - 1.0

            picks = mom.nlargest(top_n)
            if absolute:
                picks = picks[picks > 0]

            new = pd.Series(0.0, index=px.columns)
            if len(picks):
                new[picks.index] = 1.0 / len(picks)

            turnover = float((new - weights).abs().sum())
            equity *= 1.0 - fee * turnover
            weights = new
            n_rebal += 1

        curve.append(equity)

    return pd.Series(curve, index=px.index), n_rebal


def metrics(curve):
    years = len(curve) / 252
    cagr = (curve.iloc[-1] / START_EQUITY) ** (1 / max(years, 0.1)) - 1
    dd = (curve / curve.cummax() - 1).min()
    r = curve.pct_change().dropna()
    sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0
    return cagr, dd, sharpe


def ew_hold(px, fee=FEE):
    """Equal-weight buy & hold of the same universe."""
    w = 1.0 / len(px.columns)
    growth = (px / px.iloc[0]).sum(axis=1) * w
    return START_EQUITY * (1 - fee) * growth


def main():
    px = panel(UNIVERSE_1D)
    print(f"universe: {len(px.columns)} instruments, "
          f"{px.index[0].date()} -> {px.index[-1].date()} ({len(px)} bars)")
    print(f"aligned on: {', '.join(px.columns)}\n")

    ins = px[px.index < SPLIT]
    oos = px[px.index >= SPLIT]
    # rotation needs history before the OOS window to rank on
    oos_full = pd.concat([ins.tail(300), oos])

    configs = [
        dict(j=j, top_n=n, rebal=r, gap=g, absolute=a)
        for j, n, r, g, a in itertools.product(
            [63, 126, 189, 252], [1, 3, 5], [21, 63], [0, 1], [False, True])
    ]
    print(f"configs: {len(configs)}\n")

    ins_bh = metrics(ew_hold(ins))
    print(f"IN-SAMPLE  equal-weight B&H : CAGR {ins_bh[0]:6.2%}  "
          f"maxDD {ins_bh[1]:6.1%}  Sharpe {ins_bh[2]:.2f}")

    results = []
    for c in configs:
        curve, _ = run(ins, **c)
        results.append((metrics(curve), c))
    results.sort(key=lambda r: -r[0][0])

    print("\nTop 10 in-sample:")
    print(f"{'J':>4s} {'top':>4s} {'rebal':>6s} {'gap':>4s} {'abs':>4s} "
          f"{'CAGR':>8s} {'maxDD':>7s} {'Sharpe':>7s}")
    for (cagr, dd, sh), c in results[:10]:
        print(f"{c['j']:>4d} {c['top_n']:>4d} {c['rebal']:>6d} {c['gap']:>4d} "
              f"{str(c['absolute'])[:1]:>4s} {cagr:>8.2%} {dd:>7.1%} {sh:>7.2f}")

    oos_bh = metrics(ew_hold(oos_full.iloc[300:]))
    spy = fetch("SPY", "1d")
    spy_oos = spy["close"][spy.index >= SPLIT]
    spy_m = metrics(START_EQUITY * spy_oos / spy_oos.iloc[0])

    print(f"\n--- OUT-OF-SAMPLE ({oos.index[0].date()} -> {oos.index[-1].date()}) ---")
    print(f"equal-weight B&H : CAGR {oos_bh[0]:6.2%}  maxDD {oos_bh[1]:6.1%}  Sharpe {oos_bh[2]:.2f}")
    print(f"SPY buy & hold   : CAGR {spy_m[0]:6.2%}  maxDD {spy_m[1]:6.1%}  Sharpe {spy_m[2]:.2f}\n")

    print(f"{'J':>4s} {'top':>4s} {'rebal':>6s} {'gap':>4s} {'abs':>4s} "
          f"{'IS CAGR':>8s} {'OOS CAGR':>9s} {'OOS DD':>7s} {'OOS Shrp':>8s} {'vs EW':>6s} {'vs SPY':>7s}")
    beat_ew = beat_spy = 0
    for (cagr, dd, sh), c in results[:10]:
        curve, _ = run(oos_full, **c)
        co, ddo, sho = metrics(curve.iloc[300:])
        print(f"{c['j']:>4d} {c['top_n']:>4d} {c['rebal']:>6d} {c['gap']:>4d} "
              f"{str(c['absolute'])[:1]:>4s} {cagr:>8.2%} {co:>9.2%} {ddo:>7.1%} "
              f"{sho:>8.2f} {'YES' if co > oos_bh[0] else 'no':>6s} "
              f"{'YES' if co > spy_m[0] else 'no':>7s}")

    # census over the whole grid, not just the in-sample leaders
    for (cagr, dd, sh), c in results:
        curve, _ = run(oos_full, **c)
        co, _, _ = metrics(curve.iloc[300:])
        beat_ew += co > oos_bh[0]
        beat_spy += co > spy_m[0]
    n = len(results)
    print(f"\n--- census over all {n} configs, out-of-sample ---")
    print(f"beat equal-weight B&H : {beat_ew:>3d} / {n}")
    print(f"beat SPY              : {beat_spy:>3d} / {n}")


if __name__ == "__main__":
    main()
