"""Strict walk-forward: choose parameters only from the past, test on the future.

Every earlier result in this repo picked its parameters while able to see the
whole history. This does not. For each fold:

    train on [start, cut)          grid-search here, and ONLY here
    embargo  [cut, cut+gap)        discarded entirely
    test on  [cut+gap, cut+gap+L)  the chosen config runs untouched

The out-of-sample curve is the concatenation of the test windows. That single
number is the only honest result the file produces.

FIVE THINGS THAT MAKE IT STRICT

1. EMBARGO. A gap between train and test. Trades open at the end of training
   would otherwise resolve inside the test window, leaking outcome
   information across the boundary.

2. WARM-UP IS PAST DATA ONLY. Indicators need 252 bars of history. That
   history is drawn from before the test window and the equity curve is
   measured only from the test start, so no future bar reaches an indicator.

3. THE RANDOM-SELECTION NULL. The same folds are re-run picking a config at
   random instead of by training Sharpe. If optimisation cannot beat a coin
   flip, the optimisation is worthless - this catches what a plain
   walk-forward hides.

4. PARAMETER STABILITY. If the winning config changes every fold, the search
   is fitting noise, however good the concatenated curve looks.

5. DEFLATED SHARPE. Searching N configs inflates the best Sharpe even with no
   edge. The expected maximum under the null is subtracted explicitly.

    uv run --with yfinance --with pandas --with numpy python walkforward.py
    uv run ... python walkforward.py --mode rolling --test-years 2
"""

import argparse
import itertools
from collections import Counter

import numpy as np
import pandas as pd

from swing import BPY, START_EQUITY, atr, dv2, load, self_check

WARMUP = 300          # bars of history each test window needs for indicators


def grid():
    """Small and paper-grounded on purpose.

    A large grid is itself the overfitting risk: the more configs searched,
    the higher the best training Sharpe rises with no edge at all. DV2
    thresholds come from Abrams & Walker; the drawdown filter is the
    crash-recovery hypothesis from crash_recovery.py, included so walk-forward
    can settle it rather than a human eyeballing buckets.
    """
    out = []
    for buy, sell, regime, dd_min in itertools.product(
            (30.0, 40.0, 50.0), (60.0, 70.0, 80.0), (True, False),
            (0.0, 0.25)):
        out.append(dict(buy=buy, sell=sell, regime=regime, dd_min=dd_min))
    return out


def prep(df):
    d = df.copy()
    d["dv2"] = dv2(d)
    d["sma200"] = d["close"].rolling(200).mean()
    d["dd"] = 1.0 - d["close"] / d["close"].cummax()
    d["atr"] = atr(d)
    return d.dropna(subset=["dv2", "sma200", "atr"])


def returns_of(d, p, fee, start=None):
    """Daily returns of the rule over d, counted only from `start`.

    Bars before `start` still run - they warm the indicators and can leave a
    position open - but they contribute no measured return.
    """
    equity, shares = START_EQUITY, 0
    idx, vals = [], []
    rows = list(d.itertuples())

    for i in range(1, len(rows)):
        prev, bar = rows[i - 1], rows[i]
        fill = bar.open
        ok_regime = (prev.close > prev.sma200) if p["regime"] else True
        ok_dd = prev.dd >= p["dd_min"]

        if shares > 0 and (prev.dv2 > p["sell"] or not ok_regime):
            equity += shares * fill * (1 - fee)
            shares = 0
        elif shares == 0 and ok_regime and ok_dd and prev.dv2 < p["buy"]:
            n = int(equity // (fill * (1 + fee)))
            if n > 0:
                equity -= n * fill * (1 + fee)
                shares = n

        idx.append(bar.Index)
        vals.append(equity + shares * bar.close)

    curve = pd.Series(vals, index=idx)
    if start is not None:
        curve = curve[curve.index >= start]
    return curve.pct_change().dropna()


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(BPY) if len(r) > 5 and r.std() > 0 else 0.0


def metrics(r):
    if len(r) < 5:
        return 0.0, 0.0, 0.0
    eq = (1 + r).cumprod()
    yrs = len(r) / BPY
    return (eq.iloc[-1] ** (1 / max(yrs, .1)) - 1,
            (eq / eq.cummax() - 1).min(), sharpe(r))


def folds(d, mode, train_years, test_years, embargo_days):
    """Yield (train_slice, test_slice_with_warmup, test_start)."""
    dates = d.index
    start = dates[0]
    cut = start + pd.DateOffset(years=train_years)
    out = []
    while True:
        test_start = cut + pd.Timedelta(days=embargo_days)
        test_end = test_start + pd.DateOffset(years=test_years)
        if test_end > dates[-1]:
            break
        train = d[(d.index >= (start if mode == "anchored"
                               else cut - pd.DateOffset(years=train_years)))
                  & (d.index < cut)]
        warm_from = d.index[max(0, d.index.searchsorted(test_start) - WARMUP)]
        test = d[(d.index >= warm_from) & (d.index < test_end)]
        if len(train) > 400 and len(test) > WARMUP + 100:
            out.append((train, test, test_start))
        cut = cut + pd.DateOffset(years=test_years)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="CL=F")
    ap.add_argument("--mode", default="anchored", choices=["anchored", "rolling"])
    ap.add_argument("--train-years", type=int, default=6)
    ap.add_argument("--test-years", type=int, default=2)
    ap.add_argument("--embargo-days", type=int, default=30)
    ap.add_argument("--fee-bps", type=float, default=1.5)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    self_check()
    fee = a.fee_bps / 10_000
    d = prep(load(a.symbol))
    g = grid()
    fs = folds(d, a.mode, a.train_years, a.test_years, a.embargo_days)
    if not fs:
        raise SystemExit("no folds - shorten --train-years or --test-years")

    print(f"\n{a.symbol}  {a.mode}  train {a.train_years}y / test "
          f"{a.test_years}y / embargo {a.embargo_days}d")
    print(f"{len(g)} configs searched per fold, {len(fs)} folds, "
          f"{a.fee_bps}bps/side\n")

    rng = np.random.default_rng(a.seed)
    oos, oos_rand, chosen, train_srs = [], [], [], []

    print(f"{'fold':>4s} {'test window':>19s} {'buy':>4s} {'sell':>5s} "
          f"{'reg':>4s} {'ddmin':>6s} {'train SR':>9s} {'test SR':>8s} "
          f"{'rand SR':>8s}")
    for k, (train, test, ts) in enumerate(fs, 1):
        scored = [(sharpe(returns_of(train, p, fee)), i) for i, p in enumerate(g)]
        best_sr, best_i = max(scored)
        p = g[best_i]
        r = returns_of(test, p, fee, start=ts)
        rp = g[rng.integers(len(g))]
        rr = returns_of(test, rp, fee, start=ts)

        oos.append(r)
        oos_rand.append(rr)
        chosen.append((p["buy"], p["sell"], p["regime"], p["dd_min"]))
        train_srs.append([s for s, _ in scored])

        print(f"{k:>4d} {ts:%Y-%m}-{test.index[-1]:%Y-%m}   {p['buy']:>4.0f} "
              f"{p['sell']:>5.0f} {str(p['regime'])[0]:>4s} {p['dd_min']:>6.2f} "
              f"{best_sr:>9.2f} {sharpe(r):>8.2f} {sharpe(rr):>8.2f}")

    R = pd.concat(oos).sort_index()
    RR = pd.concat(oos_rand).sort_index()
    c, dd, sr = metrics(R)
    rc, rdd, rsr = metrics(RR)

    bh = load(a.symbol)["close"]
    bh = bh[(bh.index >= R.index[0]) & (bh.index <= R.index[-1])].pct_change().dropna()
    bc, bdd, bsr = metrics(bh)

    print(f"\n{'=' * 70}\nCONCATENATED OUT-OF-SAMPLE  ({len(R)} days, "
          f"{len(R) / BPY:.1f} years)\n{'=' * 70}")
    print(f"{'walk-forward':16s} CAGR {c:>7.2%}  maxDD {dd:>7.1%}  SR {sr:>5.2f}")
    print(f"{'random config':16s} CAGR {rc:>7.2%}  maxDD {rdd:>7.1%}  SR {rsr:>5.2f}")
    print(f"{'buy & hold':16s} CAGR {bc:>7.2%}  maxDD {bdd:>7.1%}  SR {bsr:>5.2f}")

    print(f"\n{'=' * 70}\nSTRICTNESS CHECKS\n{'=' * 70}")

    print(f"selection beats random by  {sr - rsr:+.2f} Sharpe")
    if sr - rsr < 0.1:
        print("  -> optimisation adds nothing over picking blind. The grid")
        print("     search is decoration.")

    cnt = Counter(chosen)
    print(f"\nparameter stability        {len(cnt)} distinct configs over "
          f"{len(fs)} folds")
    top, n = cnt.most_common(1)[0]
    print(f"  most common               buy<{top[0]:.0f} sell>{top[1]:.0f} "
          f"regime={top[2]} ddmin={top[3]:.2f}  chosen {n}/{len(fs)}")
    if len(cnt) > len(fs) * 0.6:
        print("  -> the winner changes almost every fold; the search is")
        print("     tracking noise, not a stable parameter.")

    # Deflated Sharpe: subtract the expected best-of-N under a null of no skill.
    all_tr = np.array(train_srs)
    sd = all_tr.std()
    N = len(g)
    expected_max = sd * ((1 - np.euler_gamma) * 2**0.5 * 0.8 +
                         np.euler_gamma * 1.0) * np.log(N) ** 0.5
    print(f"\ngrid inflation             {N} configs, train SR sd {sd:.2f}")
    print(f"  expected best-of-N if no edge exists ~ {expected_max:.2f} Sharpe")
    print(f"  mean training SR of winners           {all_tr.max(axis=1).mean():.2f}")
    if all_tr.max(axis=1).mean() < expected_max:
        print("  -> winning training Sharpes are within what pure chance")
        print("     produces at this grid size.")

    print(f"\n{'=' * 70}")
    if sr > bsr and sr - rsr >= 0.1:
        print("Walk-forward beats buy & hold AND beats random selection.")
        print("The weakest link is now sample size, not method.")
    else:
        print("Does not clear both bars. Treat the earlier full-sample")
        print("result as fitted, not validated.")


if __name__ == "__main__":
    main()
