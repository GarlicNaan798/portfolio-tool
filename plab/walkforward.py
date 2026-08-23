"""Shared walk-forward machinery.

The fold logic was copy-pasted across run_portfolio.py, run_levels.py and
run_alpha.py and had already started to drift. One implementation, used by
all of them.

Everything here exists to stop a result being believed too easily:

    embargo         a gap between train and test, so a position opened at
                    the end of training cannot resolve inside the test
    warm-up         indicator history drawn strictly from bars BEFORE the
                    test window; returns measured only from test start
    random null     the same folds re-run picking a config at random. If
                    optimisation cannot beat a coin flip, it is not finding
                    signal
    excess bootstrap  resamples the strategy MINUS the benchmark, not the
                    raw return. Any long-equity book has a positive Sharpe
                    in a bull market; testing SR > 0 passes on beta alone
"""

import numpy as np
import pandas as pd

from plab import metrics

WARMUP = 300


def folds(index, train_years=8, test_years=2, embargo_days=30):
    """Yield (train_start, cut, test_start, test_end, warmup_start)."""
    start = index[0]
    cut = start + pd.DateOffset(years=train_years)
    out = []
    while True:
        ts = cut + pd.Timedelta(days=embargo_days)
        te = ts + pd.DateOffset(years=test_years)
        if te > index[-1]:
            break
        warm_i = max(0, index.searchsorted(ts) - WARMUP)
        out.append((start, cut, ts, te, index[warm_i]))
        cut = cut + pd.DateOffset(years=test_years)
    return out


def run(px, grid, fit_fn, seed=0, train_years=8, test_years=2,
        embargo_days=30, verbose=True):
    """Generic walk-forward.

    fit_fn(px_slice, config, start=None) -> daily return Series.
    Called once per config on the training slice to choose, then once on the
    test slice to score. `start` is passed only for the test call so returns
    are measured from the test boundary while warm-up bars still feed the
    indicators.

    Returns (oos_returns, random_returns, chosen_configs).
    """
    fs = folds(px.index, train_years, test_years, embargo_days)
    if not fs:
        raise SystemExit("no folds - shorten --train-years or --test-years")

    rng = np.random.default_rng(seed)
    oos, oos_rand, chosen = [], [], []

    if verbose:
        print(f"{len(grid)} configs per fold, {len(fs)} folds\n")
        print(f"{'fold':>4s} {'test window':>18s} {'train SR':>9s} "
              f"{'test SR':>8s} {'rand SR':>8s}  config")

    for k, (s0, cut, ts, te, warm) in enumerate(fs, 1):
        tr = px[(px.index >= s0) & (px.index < cut)]
        te_px = px[(px.index >= warm) & (px.index < te)]

        scored = []
        for g in grid:
            r = fit_fn(tr, g)
            scored.append((metrics.sharpe(r), g))
        best_sr, best = max(scored, key=lambda x: x[0])

        r = fit_fn(te_px, best, start=ts)
        rg = grid[int(rng.integers(len(grid)))]
        rr = fit_fn(te_px, rg, start=ts)

        oos.append(r)
        oos_rand.append(rr)
        chosen.append(tuple(sorted(best.items())))

        if verbose:
            desc = ", ".join(f"{k2}={v}" for k2, v in sorted(best.items()))
            print(f"{k:>4d} {ts:%Y-%m}-{te:%Y-%m} {best_sr:>9.2f} "
                  f"{metrics.sharpe(r):>8.2f} {metrics.sharpe(rr):>8.2f}  {desc}")

    return (pd.concat(oos).sort_index(),
            pd.concat(oos_rand).sort_index(), chosen)


def report(oos, rand, bench, chosen, label="walk-forward"):
    """Print the three gates and return True only if all pass."""
    bench = pd.Series(bench).reindex(oos.index).fillna(0.0)

    print("\n" + "-" * 74)
    print(metrics.fmt(label, metrics.summary(oos)))
    print(metrics.fmt("random config", metrics.summary(rand)))
    print(metrics.fmt("benchmark", metrics.summary(bench)))

    sr, rsr, bsr = (metrics.sharpe(oos), metrics.sharpe(rand),
                    metrics.sharpe(bench))
    excess = (oos - bench).dropna()
    _, lo, hi, frac = metrics.block_bootstrap_sharpe(excess)

    print(f"\nexcess over benchmark:")
    print(f"  mean          {excess.mean() * 252:+.2%} a year")
    print(f"  bootstrap CI  {lo:+.2f} to {hi:+.2f}  "
          f"({frac:.1%} of resamples <= 0)")
    print(f"\nbeats random by     {sr - rsr:+.2f} Sharpe")
    print(f"beats benchmark by  {sr - bsr:+.2f} Sharpe  "
          f"(SE ~{metrics.summary(oos)['se']:.2f})")
    print(f"config stability    {len(set(chosen))} distinct over "
          f"{len(chosen)} folds")

    g1, g2, g3 = sr > bsr, (sr - rsr) >= 0.1, lo > 0
    print("\n" + "=" * 74)
    print(f"  [{'x' if g1 else ' '}] beats the benchmark")
    print(f"  [{'x' if g2 else ' '}] beats random selection by >= 0.10 Sharpe")
    print(f"  [{'x' if g3 else ' '}] excess bootstrap interval excludes zero")
    passed = g1 and g2 and g3
    print("\nPASSES all three gates." if passed else
          "\nDOES NOT PASS. All three are required.")
    return passed
