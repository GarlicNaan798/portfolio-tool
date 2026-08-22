"""Portfolio system: measure the signal, then construct, then validate.

Order matters and is enforced here.

  STEP 1  measure IC. If the signal cannot rank stocks, no construction
          method saves it, and the rest of the run is theatre. IDEAS.md
          records that price-only IC on single stocks was about +0.02.
  STEP 2  compare construction methods in-sample. This is NOT a result -
          it is a look at whether construction changes anything at all.
  STEP 3  strict walk-forward. Method and parameters chosen only on past
          data, scored on the future, against a random-selection null.

Only step 3 produces a number worth quoting.

    uv run --with yfinance --with pandas --with numpy python run_portfolio.py
    uv run ... python run_portfolio.py --top-n 30 --fee-bps 2
"""

import argparse
import itertools

import numpy as np
import pandas as pd

from plab import alpha, data, metrics, portfolio

WARMUP = 300


def step1_ic(px, horizon):
    print("=" * 74)
    print(f"STEP 1  signal quality - rank IC over a {horizon}-bar horizon")
    print("=" * 74)
    ic = alpha.ic_report(px, horizon=horizon)
    if ic.empty:
        print("no usable IC")
        return None
    print(f"{'signal':>10s} {'n':>5s} {'mean IC':>9s} {'t':>7s} {'hit':>6s} "
          f"{'implied IR':>11s}")
    for name, r in ic.iterrows():
        print(f"{name:>10s} {r['n']:>5.0f} {r['ic']:>9.4f} {r['t']:>7.2f} "
              f"{r['hit']:>6.0%} "
              f"{alpha.implied_ir(r['ic'], px.shape[1], 252 / horizon):>11.2f}")
    print("\nImplied IR is Grinold's ceiling assuming independent bets. Real")
    print("names are correlated, so expect roughly 40% of it.")
    dec = alpha.decile_report(px, horizon=horizon)
    if not dec.empty:
        print("")
        print("  forward return by quintile (q5 = highest score) - the")
        print(f"  long-only book only ever holds q5")
        cols = [c for c in dec.columns if c.startswith("q")]
        print(f"{'signal':>10s} " + " ".join(f"{c:>8s}" for c in cols)
              + f" {'q5-q1':>8s} {'t':>6s}")
        for name, r in dec.iterrows():
            print(f"{name:>10s} " + " ".join(f"{r[c]:>8.2%}" for c in cols)
                  + f" {r['spread']:>8.2%} {r['t_spread']:>6.2f}")

    best = ic["t"].abs().max()
    if best < 2:
        print(f"\nNo signal clears t=2 (best {best:.2f}). Construction cannot")
        print("create signal - treat everything below as a negative result.")
    return ic


def step2_construction(px, scores, bench, args):
    print("\n" + "=" * 74)
    print("STEP 2  construction methods, IN SAMPLE - not a result")
    print("=" * 74)
    idx = None
    for method in ("equal", "inv_vol", "mean_var"):
        eq, turn = portfolio.run(px, scores, method=method, top_n=args.top_n,
                                 rebal=args.rebal, fee_bps=args.fee_bps,
                                 max_w=args.max_w)
        if idx is None:
            idx = eq.index
        print(portfolio.report(eq, method) + f"  turnover {turn:.2f}")

    b = portfolio.benchmark(bench, idx)
    print(metrics.fmt("SPY", metrics.summary(b.pct_change().dropna())))
    ew = (1 + px.pct_change().fillna(0.0).mean(axis=1)).cumprod().reindex(idx).dropna()
    print(metrics.fmt("equal-weight univ", metrics.summary(ew.pct_change().dropna())))


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


def step3_walkforward(px, scores, bench, args):
    print("\n" + "=" * 74)
    print(f"STEP 3  strict walk-forward - train {args.train_years}y / test "
          f"{args.test_years}y / embargo {args.embargo}d")
    print("=" * 74)

    grid = [dict(method=m, top_n=n)
            for m, n in itertools.product(("equal", "inv_vol", "mean_var"),
                                          (10, 20, 40))]
    fs = folds(px.index, args.train_years, args.test_years, args.embargo)
    if not fs:
        print("not enough history for these fold sizes")
        return
    print(f"{len(grid)} configs per fold, {len(fs)} folds\n")

    rng = np.random.default_rng(args.seed)
    oos, oos_rand, chosen = [], [], []

    print(f"{'fold':>4s} {'test window':>18s} {'method':>9s} {'N':>4s} "
          f"{'train SR':>9s} {'test SR':>8s} {'rand SR':>8s}")
    for k, (s0, cut, ts, te, warm) in enumerate(fs, 1):
        tr_px = px[(px.index >= s0) & (px.index < cut)]
        tr_sc = scores.reindex(tr_px.index)
        te_px = px[(px.index >= warm) & (px.index < te)]
        te_sc = scores.reindex(te_px.index)

        scored = []
        for g in grid:
            eq, _ = portfolio.run(tr_px, tr_sc, fee_bps=args.fee_bps,
                                  rebal=args.rebal, max_w=args.max_w, **g)
            scored.append((metrics.sharpe(eq.pct_change().dropna()), g))
        best_sr, best = max(scored, key=lambda x: x[0])

        eq, _ = portfolio.run(te_px, te_sc, fee_bps=args.fee_bps,
                              rebal=args.rebal, max_w=args.max_w,
                              start=ts, **best)
        rg = grid[rng.integers(len(grid))]
        eqr, _ = portfolio.run(te_px, te_sc, fee_bps=args.fee_bps,
                               rebal=args.rebal, max_w=args.max_w,
                               start=ts, **rg)

        r, rr = eq.pct_change().dropna(), eqr.pct_change().dropna()
        oos.append(r)
        oos_rand.append(rr)
        chosen.append((best["method"], best["top_n"]))
        print(f"{k:>4d} {ts:%Y-%m}-{te:%Y-%m}  {best['method']:>9s} "
              f"{best['top_n']:>4d} {best_sr:>9.2f} {metrics.sharpe(r):>8.2f} "
              f"{metrics.sharpe(rr):>8.2f}")

    R, RR = pd.concat(oos).sort_index(), pd.concat(oos_rand).sort_index()
    b = portfolio.benchmark(bench, R.index).pct_change().dropna()
    # The universe is today's large caps, so it beats SPY by construction.
    # Equal-weighting it is therefore the benchmark that isolates the SIGNAL;
    # comparing to SPY mostly measures survivorship.
    ew = px.pct_change().fillna(0.0).mean(axis=1).reindex(R.index).dropna()

    print("\n" + "-" * 74)
    print(metrics.fmt("walk-forward OOS", metrics.summary(R)))
    print(metrics.fmt("random config", metrics.summary(RR)))
    print(metrics.fmt("equal-weight univ", metrics.summary(ew)))
    print(metrics.fmt("SPY", metrics.summary(b)))
    print("\nEqual-weight universe is the bar that matters. Beating SPY here")
    print("mostly measures survivorship, not skill.")

    sr, rsr = metrics.sharpe(R), metrics.sharpe(RR)
    bsr = metrics.sharpe(ew)

    # Bootstrap the EXCESS return over the benchmark, not the raw return.
    # Any long-equity book has a positive Sharpe in a bull market; testing
    # SR > 0 therefore passes on beta alone and says nothing about skill.
    excess = (R - ew.reindex(R.index).fillna(0.0)).dropna()
    _, lo, hi, frac = metrics.block_bootstrap_sharpe(excess)

    print(f"\nexcess over equal-weight universe:")
    print(f"  mean          {excess.mean() * 252:+.2%} a year")
    print(f"  bootstrap CI  {lo:+.2f} to {hi:+.2f}   "
          f"({frac:.1%} of resamples <= 0)")
    print(f"\nbeats random by     {sr - rsr:+.2f} Sharpe")
    print(f"beats equal-weight  {sr - bsr:+.2f} Sharpe  "
          f"(SE on each is ~{metrics.summary(R)['se']:.2f})")
    print(f"config stability    {len(set(chosen))} distinct over {len(fs)} folds")

    print("\n" + "=" * 74)
    if sr > bsr and sr - rsr >= 0.1 and lo > 0:
        print("PASSES: beats the equal-weight universe, beats random")
        print("selection, and the EXCESS bootstrap interval excludes zero.")
    else:
        print("DOES NOT PASS. All three are required: beat the equal-weight")
        print("universe, beat random selection, and an excess-return")
        print("bootstrap interval that excludes zero.")
        if lo <= 0:
            print("\nThe excess interval includes zero: the portfolio's")
            print("advantage over simply holding the universe is not")
            print("distinguishable from chance.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--rebal", type=int, default=21)
    p.add_argument("--fee-bps", type=float, default=5.0)
    p.add_argument("--max-w", type=float, default=0.10)
    p.add_argument("--horizon", type=int, default=21)
    p.add_argument("--train-years", type=int, default=8)
    p.add_argument("--test-years", type=int, default=2)
    p.add_argument("--embargo", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--signal", default="combined",
                   help="'combined', or a comma list from "
                        + ",".join(alpha.SIGNALS))
    args = p.parse_args()

    px, dropped = data.panel(data.LARGE_CAP, refresh=args.refresh)
    px = px.dropna(axis=1, thresh=int(len(px) * 0.7)).ffill()
    bench = data.fetch(data.BENCHMARK)["close"]

    print(f"universe {px.shape[1]} names, {px.index[0]:%Y-%m} to "
          f"{px.index[-1]:%Y-%m} ({len(px)} bars)")
    if dropped:
        print(f"dropped {len(dropped)} for insufficient history")
    print("NOTE: today's large caps, so absolute returns are "
          "survivorship-inflated.\nCross-sectional ranking is far less "
          "affected, but the bias is real.\n")

    step1_ic(px, args.horizon)

    sigs = alpha.build(px)
    if args.signal == "combined":
        scores = alpha.combine(sigs)
    else:
        picked = [s.strip() for s in args.signal.split(",")]
        unknown = [s for s in picked if s not in sigs]
        if unknown:
            raise SystemExit(f"unknown signal(s): {unknown}")
        scores = alpha.combine({k: sigs[k] for k in picked})
        print(f"\nscoring on: {', '.join(picked)} (not the full blend)")
        print("Note: this signal was chosen after reading the IC table above,")
        print("so it carries selection bias. Short-term reversal is at least")
        print("independently documented (Jegadeesh 1990, Lehmann 1990) rather")
        print("than discovered here - but the choice is still post-hoc.")
    step2_construction(px, scores, bench, args)
    step3_walkforward(px, scores, bench, args)


if __name__ == "__main__":
    main()
