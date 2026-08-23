"""Single entry point. Replaces run_portfolio.py, run_levels.py, run_alpha.py.

Those three duplicated their fold logic, their gate reporting and their
benchmark handling, and had already drifted apart - one of them compared to
SPY while another compared to the equal-weight universe, which is the error
NOTES.md records as having stood for seven phases.

Controls run FIRST and the run aborts if any fail. That is the fix for the
council's central criticism: every bug in this project was caught because a
number looked implausible, a filter that by construction preserves every
error producing a plausible result.

    uv run --with yfinance --with pandas --with numpy python run.py signals
    uv run ... python run.py portfolio
    uv run ... python run.py levels
    uv run ... python run.py alpha
"""

import argparse
import itertools

import pandas as pd

from plab import alpha as alpha_mod
from plab import data, levels, metrics, portfolio, validate, walkforward


def load_universe(refresh=False):
    px, dropped = data.panel(data.LARGE_CAP, refresh=refresh)
    px = px.dropna(axis=1, thresh=int(len(px) * 0.7)).ffill()
    bench = data.fetch(data.BENCHMARK)["close"].reindex(px.index).ffill()
    # Equal-weight of the SAME universe. SPY is a softer bar because this
    # universe is today's survivors and beats the index by construction.
    ew = px.pct_change().fillna(0.0).mean(axis=1)
    print(f"universe {px.shape[1]} names, {px.index[0]:%Y-%m} to "
          f"{px.index[-1]:%Y-%m}"
          + (f", dropped {len(dropped)}" if dropped else ""))
    print("Benchmark is the equal-weight universe, not SPY: these are today's")
    print("survivors, so SPY comparisons credit the strategy for survivorship.\n")
    return px, bench, ew


def cmd_signals(args):
    px, _, _ = load_universe(args.refresh)
    ic = alpha_mod.ic_report(px, horizon=args.horizon)
    print(f"{'signal':>10s} {'n':>5s} {'mean IC':>9s} {'t':>7s} {'hit':>6s}")
    for name, r in ic.iterrows():
        print(f"{name:>10s} {r['n']:>5.0f} {r['ic']:>9.4f} {r['t']:>7.2f} "
              f"{r['hit']:>6.0%}")

    dec = alpha_mod.decile_report(px, horizon=args.horizon)
    if not dec.empty:
        print("\nforward return by quintile - a long-only book only holds q5.")
        print("Read this, not the IC: IC is a whole-cross-section statistic")
        print("and is blind to non-monotonic signals a top-N book can use.\n")
        cols = [c for c in dec.columns if c.startswith("q")]
        print(f"{'signal':>10s} " + " ".join(f"{c:>8s}" for c in cols)
              + f" {'q5-q1':>8s} {'t':>6s}")
        for name, r in dec.iterrows():
            print(f"{name:>10s} " + " ".join(f"{r[c]:>8.2%}" for c in cols)
                  + f" {r['spread']:>8.2%} {r['t_spread']:>6.2f}")
    print("\nIC noise floor is about -0.004 (plab/validate). Read these as")
    print("distance above that, not as absolute numbers.")


def cmd_portfolio(args):
    px, _, ew = load_universe(args.refresh)
    scores = alpha_mod.combine(alpha_mod.build(px))
    grid = [dict(method=m, top_n=n)
            for m, n in itertools.product(("equal", "inv_vol", "mean_var"),
                                          (10, 20, 40))]

    def fit(px_slice, cfg, start=None):
        eq, _ = portfolio.run(px_slice, scores.reindex(px_slice.index),
                              fee_bps=args.fee_bps, start=start, **cfg)
        return eq.pct_change().dropna()

    oos, rand, chosen = walkforward.run(px, grid, fit, seed=args.seed,
                                        train_years=args.train_years,
                                        test_years=args.test_years,
                                        embargo_days=args.embargo)
    walkforward.report(oos, rand, ew, chosen, "portfolio")


def cmd_levels(args):
    px, bench, ew = load_universe(args.refresh)
    scores = alpha_mod.combine(alpha_mod.build(px))
    grid = [dict(window=w, entry_max=e, exit_at=x, use_macro=m)
            for w, e, x, m in itertools.product(
                (42, 63, 126), (0.20, 0.30), (0.80, 0.90), (True, False))]

    def fit(px_slice, cfg, start=None):
        eq, _ = levels.run(px_slice, scores.reindex(px_slice.index),
                           bench_px=bench.reindex(px_slice.index),
                           slots=args.top_n, fee_bps=args.fee_bps,
                           start=start, **cfg)
        return eq.pct_change().dropna()

    oos, rand, chosen = walkforward.run(px, grid, fit, seed=args.seed,
                                        train_years=args.train_years,
                                        test_years=args.test_years,
                                        embargo_days=args.embargo)
    walkforward.report(oos, rand, ew, chosen, "levels")


def cmd_alpha(args):
    px, bench, ew = load_universe(args.refresh)
    scores = alpha_mod.combine(alpha_mod.build(px))
    grid = [dict(method=m, top_n=n)
            for m, n in itertools.product(("equal", "inv_vol", "mean_var"),
                                          (10, 20, 40))]

    def fit(px_slice, cfg, start=None):
        eq, _ = portfolio.run(px_slice, scores.reindex(px_slice.index),
                              fee_bps=args.fee_bps, start=start, **cfg)
        return eq.pct_change().dropna()

    oos, rand, _ = walkforward.run(px, grid, fit, seed=args.seed,
                                   train_years=args.train_years,
                                   test_years=args.test_years,
                                   embargo_days=args.embargo, verbose=False)
    spy = bench.pct_change().reindex(oos.index).dropna()
    ewr = ew.reindex(oos.index).dropna()

    print("\nvs SPY - flattering, credits us for the universe:")
    for lbl, r in (("model", oos), ("equal-weight universe", ewr),
                   ("random config", rand)):
        a = metrics.alpha_beta(r, spy)
        print(f"  {lbl:24s} alpha {a['alpha']:>+7.2%}/yr  t {a['t']:>5.2f}  "
              f"beta {a['beta']:>5.2f}")

    print("\nvs EQUAL-WEIGHT UNIVERSE - the honest test:")
    for lbl, r in (("model", oos), ("random config", rand)):
        a = metrics.alpha_beta(r, ewr)
        print(f"  {lbl:24s} alpha {a['alpha']:>+7.2%}/yr  t {a['t']:>5.2f}  "
              f"beta {a['beta']:>5.2f}  R2 {a['r2']:>5.2f}")

    a_ew = metrics.alpha_beta(oos, ewr)
    a_spy = metrics.alpha_beta(oos, spy)
    ew_spy = metrics.alpha_beta(ewr, spy)
    print(f"\n  total alpha vs SPY          {a_spy['alpha']:+.2%}/yr")
    print(f"  of which the universe gives {ew_spy['alpha']:+.2%}/yr (free)")
    print(f"  left for stock selection    {a_ew['alpha']:+.2%}/yr "
          f"(t = {a_ew['t']:.2f})")


COMMANDS = {"signals": cmd_signals, "portfolio": cmd_portfolio,
            "levels": cmd_levels, "alpha": cmd_alpha}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=list(COMMANDS))
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--fee-bps", type=float, default=5.0)
    p.add_argument("--horizon", type=int, default=21)
    p.add_argument("--train-years", type=int, default=8)
    p.add_argument("--test-years", type=int, default=2)
    p.add_argument("--embargo", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--skip-controls", action="store_true",
                   help="not recommended; controls exist because every bug "
                        "here was previously caught only by luck")
    args = p.parse_args()

    if not args.skip_controls:
        validate.run_all(strict=True)
        print()

    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
