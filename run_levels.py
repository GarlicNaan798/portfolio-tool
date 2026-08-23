"""Support/resistance holding with a macro overlay, walk-forward validated.

Compares three things against the same benchmark:

    monthly       the calendar portfolio from run_portfolio.py
    levels        buy near support, sell at resistance, no calendar
    levels+macro  the same, with market trend gating new entries

Same discipline as everything else here: parameters chosen only from the
training window, an embargo before the test window, a random-selection null,
and a bootstrap on the EXCESS over the benchmark rather than the raw return.

    uv run --with yfinance --with pandas --with numpy python run_levels.py
"""

import argparse
import itertools

import numpy as np
import pandas as pd

from plab import alpha, data, levels, metrics, portfolio

WARMUP = 300


def folds(index, train_years, test_years, embargo_days):
    start, cut, out = index[0], index[0] + pd.DateOffset(years=train_years), []
    while True:
        ts = cut + pd.Timedelta(days=embargo_days)
        te = ts + pd.DateOffset(years=test_years)
        if te > index[-1]:
            break
        warm_i = max(0, index.searchsorted(ts) - WARMUP)
        out.append((start, cut, ts, te, index[warm_i]))
        cut = cut + pd.DateOffset(years=test_years)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slots", type=int, default=20)
    p.add_argument("--fee-bps", type=float, default=5.0)
    p.add_argument("--train-years", type=int, default=8)
    p.add_argument("--test-years", type=int, default=2)
    p.add_argument("--embargo", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    px, _ = data.panel(data.LARGE_CAP)
    px = px.dropna(axis=1, thresh=int(len(px) * 0.7)).ffill()
    bench = data.fetch(data.BENCHMARK)["close"].reindex(px.index).ffill()
    scores = alpha.combine(alpha.build(px))

    print(f"universe {px.shape[1]} names, {px.index[0]:%Y-%m} to "
          f"{px.index[-1]:%Y-%m}")
    print("Universe is today's large caps - absolute returns are")
    print("survivorship-inflated. Equal-weight universe is the real bar.\n")

    # ---------------- in-sample look, not a result ----------------
    print("=" * 74)
    print("IN SAMPLE - shape of the strategies, NOT evidence")
    print("=" * 74)
    eq, turn = portfolio.run(px, scores, method="equal", top_n=args.slots,
                             fee_bps=args.fee_bps)
    print(portfolio.report(eq, "monthly calendar"))
    for use_macro, label in ((False, "levels"), (True, "levels+macro")):
        e, st = levels.run(px, scores, bench_px=bench, slots=args.slots,
                           fee_bps=args.fee_bps, use_macro=use_macro)
        print(levels.report(e, st, label))
    ew = px.pct_change().fillna(0.0).mean(axis=1)
    print(metrics.fmt("equal-weight univ", metrics.summary(ew)))

    # ---------------- strict walk-forward ----------------
    print("\n" + "=" * 74)
    print(f"WALK-FORWARD  train {args.train_years}y / test {args.test_years}y "
          f"/ embargo {args.embargo}d")
    print("=" * 74)

    grid = [dict(window=w, entry_max=em, exit_at=xa, use_macro=mm)
            for w, em, xa, mm in itertools.product(
                (42, 63, 126), (0.20, 0.30), (0.80, 0.90), (True, False))]
    fs = folds(px.index, args.train_years, args.test_years, args.embargo)
    print(f"{len(grid)} configs per fold, {len(fs)} folds\n")

    rng = np.random.default_rng(args.seed)
    oos, oos_rand, chosen = [], [], []

    print(f"{'fold':>4s} {'test window':>18s} {'win':>4s} {'entry':>6s} "
          f"{'exit':>5s} {'macro':>6s} {'train':>7s} {'test':>7s} {'rand':>7s}")
    for k, (s0, cut, ts, te, warm) in enumerate(fs, 1):
        tr = px[(px.index >= s0) & (px.index < cut)]
        tb = bench.reindex(tr.index)
        te_px = px[(px.index >= warm) & (px.index < te)]
        tb2 = bench.reindex(te_px.index)

        scored = []
        for g in grid:
            e, _ = levels.run(tr, scores.reindex(tr.index), bench_px=tb,
                              slots=args.slots, fee_bps=args.fee_bps, **g)
            scored.append((metrics.sharpe(e.pct_change().dropna()), g))
        best_sr, best = max(scored, key=lambda x: x[0])

        e, _ = levels.run(te_px, scores.reindex(te_px.index), bench_px=tb2,
                          slots=args.slots, fee_bps=args.fee_bps,
                          start=ts, **best)
        rg = grid[rng.integers(len(grid))]
        er, _ = levels.run(te_px, scores.reindex(te_px.index), bench_px=tb2,
                           slots=args.slots, fee_bps=args.fee_bps,
                           start=ts, **rg)

        r, rr = e.pct_change().dropna(), er.pct_change().dropna()
        oos.append(r)
        oos_rand.append(rr)
        chosen.append(tuple(best.values()))
        print(f"{k:>4d} {ts:%Y-%m}-{te:%Y-%m}  {best['window']:>4d} "
              f"{best['entry_max']:>6.2f} {best['exit_at']:>5.2f} "
              f"{str(best['use_macro'])[0]:>6s} {best_sr:>7.2f} "
              f"{metrics.sharpe(r):>7.2f} {metrics.sharpe(rr):>7.2f}")

    R = pd.concat(oos).sort_index()
    RR = pd.concat(oos_rand).sort_index()
    EW = ew.reindex(R.index).dropna()

    print("\n" + "-" * 74)
    print(metrics.fmt("levels walk-forward", metrics.summary(R)))
    print(metrics.fmt("random config", metrics.summary(RR)))
    print(metrics.fmt("equal-weight univ", metrics.summary(EW)))

    excess = (R - EW.reindex(R.index).fillna(0.0)).dropna()
    _, lo, hi, frac = metrics.block_bootstrap_sharpe(excess)
    sr, rsr, bsr = metrics.sharpe(R), metrics.sharpe(RR), metrics.sharpe(EW)

    print(f"\nexcess over equal-weight universe:")
    print(f"  mean          {excess.mean() * 252:+.2%} a year")
    print(f"  bootstrap CI  {lo:+.2f} to {hi:+.2f}  "
          f"({frac:.1%} of resamples <= 0)")
    print(f"\nbeats random by     {sr - rsr:+.2f}")
    print(f"beats equal-weight  {sr - bsr:+.2f}")
    print(f"config stability    {len(set(chosen))} distinct over {len(fs)} folds")
    macro_picked = sum(1 for c in chosen if c[-1])
    print(f"macro overlay chosen {macro_picked}/{len(fs)} folds")

    print("\n" + "=" * 74)
    if sr > bsr and sr - rsr >= 0.1 and lo > 0:
        print("PASSES all three gates.")
    else:
        print("DOES NOT PASS. Needs: beat the equal-weight universe, beat")
        print("random selection, and an excess bootstrap CI excluding zero.")


if __name__ == "__main__":
    main()
