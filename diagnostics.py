"""Two follow-ups to the Phase A / Phase B failures.

1. Was Phase A simply under-risked? Lever the blend to SPY's volatility and
   re-compare. Sharpe is leverage-invariant in theory; this checks it against
   the actual series, with financing charged on the borrowed portion.

2. Did Phase B's model have ranking skill that a long-only wrapper hid?
   Academic cross-sectional papers report a LONG-SHORT spread against zero,
   not a long-only book against SPY. Long-only carries full market beta, so
   it must clear SPY before any selection skill is visible. Measures rank IC
   and the top-minus-bottom spread, which is what the papers actually claim.

    uv run --with yfinance --with pandas --with numpy --with scikit-learn \
        python diagnostics.py
"""

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor

from swing_lab import FEE, UNIVERSE_1D, fetch
from phase_b_ranker import FOLDS, HORIZON, TOP_N, BPY, build_panel
from phase_a_combine import (COMPONENTS, ROTATION, SPLIT, component_returns,
                             curve_to_returns, metrics)
from cross_sectional import panel as price_panel, run as rotate

FINANCING = 0.04   # annual cost on the borrowed portion


def part1_leverage():
    print("=" * 62)
    print("1. WAS PHASE A UNDER-RISKED?")
    print("=" * 62)

    comps = {}
    for name, p in COMPONENTS.items():
        r = component_returns(name, p, UNIVERSE_1D)
        if r is not None:
            comps[name] = r
    rot, _ = rotate(price_panel(UNIVERSE_1D), **ROTATION)
    comps["rotation"] = curve_to_returns(rot)

    df = pd.DataFrame(comps).dropna()
    spy = fetch("SPY", "1d")["close"].pct_change().reindex(df.index).fillna(0.0)

    oos = df[df.index >= SPLIT]
    spy_oos = spy[spy.index >= SPLIT]
    blend = oos.mean(axis=1)

    spy_vol = spy_oos.std() * np.sqrt(BPY)
    bl_vol = blend.std() * np.sqrt(BPY)
    lev = spy_vol / bl_vol

    print(f"\nSPY realised vol   : {spy_vol:.1%}")
    print(f"blend realised vol : {bl_vol:.1%}")
    print(f"leverage to match  : {lev:.2f}x\n")

    # Financing applies only to the borrowed portion (lev - 1).
    daily_fin = max(lev - 1.0, 0.0) * FINANCING / BPY
    levered = blend * lev - daily_fin

    for label, r in (("SPY", spy_oos), ("blend (1.0x)", blend),
                     (f"blend ({lev:.2f}x levered)", levered)):
        c, d, s = metrics(r)
        print(f"{label:26s} CAGR {c:>7.2%}   maxDD {d:>7.1%}   Sharpe {s:>5.2f}")

    print("\nLeverage is Sharpe-neutral gross - it scales return and "
          "volatility together -\nand mildly Sharpe-negative net, because "
          "financing is charged on the borrowed\nportion. Matching SPY's "
          "risk cannot close a Sharpe gap.")


def part2_ranking_skill():
    print("\n" + "=" * 62)
    print("2. DID THE MODEL HAVE RANKING SKILL?")
    print("=" * 62)
    print("Long-short spread and rank IC - what the papers actually report.\n")

    panel, feat_cols = build_panel(UNIVERSE_1D)
    embargo = pd.Timedelta(days=int(HORIZON * 1.5))

    for i, (tr0, tr1, te0, te1) in enumerate(FOLDS, 1):
        train = panel[(panel.index >= tr0) &
                      (panel.index <= pd.Timestamp(tr1) - embargo)]
        test = panel[(panel.index >= te0) & (panel.index <= te1)].copy()
        if len(train) < 2000 or len(test) < 200:
            continue

        m = HistGradientBoostingRegressor(max_depth=4, max_iter=250,
                                          learning_rate=0.05,
                                          l2_regularization=1.0, random_state=0)
        m.fit(train[feat_cols], train["target"])
        test["pred"] = m.predict(test[feat_cols])

        dates = sorted(test.index.unique())[::HORIZON]
        ics, spreads, longs, shorts = [], [], [], []
        for d in dates:
            day = test.loc[[d]]
            if len(day) < 10:
                continue
            ic = stats.spearmanr(day["pred"], day["fwd"]).statistic
            if not np.isnan(ic):
                ics.append(ic)
            top = day.nlargest(TOP_N, "pred")["fwd"].mean()
            bot = day.nsmallest(TOP_N, "pred")["fwd"].mean()
            longs.append(top)
            shorts.append(bot)
            spreads.append(top - bot)

        if len(spreads) < 4:
            continue

        s = pd.Series(spreads)
        per_year = BPY / HORIZON
        t_ic = stats.ttest_1samp(ics, 0.0)
        t_sp = stats.ttest_1samp(spreads, 0.0)
        sp_sharpe = s.mean() / s.std() * np.sqrt(per_year) if s.std() > 0 else 0.0
        # spread pays two round-trips (long leg + short leg)
        net = s.mean() - FEE * 4

        print(f"fold {i}  {te0[:7]} -> {te1[:7]}  ({len(spreads)} periods)")
        print(f"   rank IC        mean {np.mean(ics):>+7.4f}  "
              f"t={t_ic.statistic:>5.2f}  p={t_ic.pvalue:.3f}")
        print(f"   long leg       mean {np.mean(longs):>+7.2%} per {HORIZON}d")
        print(f"   short leg      mean {np.mean(shorts):>+7.2%} per {HORIZON}d")
        print(f"   L-S spread     mean {s.mean():>+7.2%}  t={t_sp.statistic:>5.2f}"
              f"  p={t_sp.pvalue:.3f}  Sharpe {sp_sharpe:>5.2f}")
        print(f"   after costs    mean {net:>+7.2%} per {HORIZON}d\n")

    print("A positive, significant IC and spread would mean real ranking skill\n"
          "that the long-only wrapper buried under market beta. An IC near zero\n"
          "means there was nothing to bury.")


if __name__ == "__main__":
    part1_leverage()
    part2_ranking_skill()
