"""Phase C: is breadth the binding constraint?

IR ~ IC x sqrt(N). Phase B found real ranking skill on 22 ETFs that costs
ate. If N is what is missing, the same model on a wider universe should show
IR rising with sqrt(N) and nothing else changing.

Subsamples are drawn from ONE parent universe so the model, features and
periods are identical across sizes. Any survivorship bias inflates every
size equally, which leaves the scaling relationship intact even though the
absolute levels are optimistic. Prediction registered in PLAN.md before this
was run.

    uv run --with yfinance --with pandas --with numpy --with scikit-learn \
        --with scipy python phase_c_breadth.py
"""

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor

from swing_lab import FEE, fetch
from phase_b_ranker import FOLDS, HORIZON, BPY, features_for

SIZES = [25, 50, 100, 200]
DRAWS = 3
RNG = np.random.default_rng(0)

# Liquid US large caps with history back to at least 2005. Today's survivors,
# which is a stated limitation - see PLAN.md.
UNIVERSE = """
AAPL MSFT AMZN GOOGL META NVDA TSLA JPM V JNJ WMT PG MA HD CVX ABBV PFE KO
PEP BAC COST TMO CSCO MRK ACN LLY MCD ADBE ABT CRM NKE TXN DHR NEE WFC ORCL
PM UNP MS RTX LOW INTC UPS QCOM HON BMY AMGN SBUX BLK CAT GS INTU DE AXP
GILD ADI MDLZ ISRG TJX VRTX REGN ZTS SYK PLD MMC CB SO CI DUK BDX ITW MO
AON APD CL ICE FDX NSC EOG SLB PSX MPC VLO OXY HAL DVN FANG HES KMI WMB
OKE T VZ CMCSA DIS NFLX PYPL SQ SHOP UBER ABNB DASH SPOT SNAP PINS ROKU
EBAY ETSY F GM RIVN LCID CCL RCL NCLH MAR HLT WYNN LVS MGM DAL UAL LUV AAL
BA LMT NOC GD LHX TDG EMR ETN PH ROK AME FTV XYL DOV IR CMI PCAR
AMD MU LRCX KLAC AMAT ASML TSM AVGO NXPI ON SWKS MCHP TER ENTG
UNH ELV CVS CNC HUM MCK COR CAH DGX LH IQV A WST RMD BSX EW ZBH BAX
SPG O PSA EXR AVB EQR MAA UDR ESS VTR WELL DLR EQIX AMT CCI SBAC
XOM COP PXD CTRA MRO APA EQT AR RRC SWN CHK
""".split()


def build(tickers):
    """Per-ticker feature frames, cached in memory."""
    frames = {}
    for t in tickers:
        f = features_for(t)
        if f is not None and len(f) > 1500:
            frames[t] = f
    return frames


def panel_from(frames, subset):
    rows = []
    for t in subset:
        f = frames[t].copy()
        f["ticker"] = t
        rows.append(f)
    panel = pd.concat(rows).sort_index()

    counts = panel.groupby(level=0).size()
    panel = panel[panel.index.isin(counts[counts >= max(8, len(subset) // 2)].index)]

    feat = [c for c in panel.columns if c not in ("ticker", "target", "fwd")]
    ranked = panel.groupby(level=0)[feat].rank(pct=True)
    for c in feat:                       # positional, index is non-unique
        panel[f"r_{c}"] = ranked[c].values
    return panel, [f"r_{c}" for c in feat]


def spread_ir(panel, feat_cols, n_side):
    """Long-short IR and IC pooled across the walk-forward folds."""
    embargo = pd.Timedelta(days=int(HORIZON * 1.5))
    all_spreads, all_ics = [], []

    for tr0, tr1, te0, te1 in FOLDS:
        train = panel[(panel.index >= tr0) &
                      (panel.index <= pd.Timestamp(tr1) - embargo)]
        test = panel[(panel.index >= te0) & (panel.index <= te1)].copy()
        if len(train) < 2000 or len(test) < 200:
            continue

        m = HistGradientBoostingRegressor(max_depth=4, max_iter=200,
                                          learning_rate=0.05,
                                          l2_regularization=1.0, random_state=0)
        m.fit(train[feat_cols], train["target"])
        test["pred"] = m.predict(test[feat_cols])

        for d in sorted(test.index.unique())[::HORIZON]:
            day = test.loc[[d]]
            if len(day) < max(10, n_side * 2):
                continue
            ic = stats.spearmanr(day["pred"], day["fwd"]).statistic
            if not np.isnan(ic):
                all_ics.append(ic)
            top = day.nlargest(n_side, "pred")["fwd"].mean()
            bot = day.nsmallest(n_side, "pred")["fwd"].mean()
            all_spreads.append(top - bot)

    if len(all_spreads) < 10:
        return None
    s = pd.Series(all_spreads)
    per_year = BPY / HORIZON
    ir = s.mean() / s.std() * np.sqrt(per_year) if s.std() > 0 else 0.0
    return dict(ir=ir, ic=float(np.mean(all_ics)), gross=s.mean(),
                net=s.mean() - FEE * 4, n=len(all_spreads))


def main():
    print("PHASE C - does IR scale with sqrt(N)?")
    print("prediction (PLAN.md): IR multiple vs N=25 -> 1.41x / 2.00x / 2.83x\n")

    print(f"fetching {len(UNIVERSE)} tickers...")
    frames = build(UNIVERSE)
    pool = sorted(frames)
    print(f"usable: {len(pool)} tickers\n")

    SIZES[:] = [s for s in SIZES if s < len(pool)] + [len(pool)]
    print(f"sizes: {SIZES}\n")

    results = {}
    for n in SIZES:
        runs = []
        for d in range(DRAWS):
            subset = list(RNG.choice(pool, size=min(n, len(pool)), replace=False))
            panel, feat = panel_from(frames, subset)
            # hold decile-style side size proportional to universe
            r = spread_ir(panel, feat, max(3, n // 10))
            if r:
                runs.append(r)
        if runs:
            results[n] = dict(
                ir=float(np.mean([x["ir"] for x in runs])),
                ic=float(np.mean([x["ic"] for x in runs])),
                gross=float(np.mean([x["gross"] for x in runs])),
                net=float(np.mean([x["net"] for x in runs])))
            print(f"N={n:>4d}  IR {results[n]['ir']:>5.2f}   "
                  f"IC {results[n]['ic']:>+7.4f}   "
                  f"gross {results[n]['gross']:>+6.2%}   "
                  f"net {results[n]['net']:>+6.2%}")

    if len(results) < 2:
        print("\ninsufficient results")
        return

    # Ratios against a near-zero or negative baseline are meaningless, so
    # test the law itself: IR = IC * sqrt(BR), BR = N * rebalances per year.
    rebals = BPY / HORIZON
    print(f"\n=== fundamental law: IR = IC x sqrt(N x {rebals:.0f}) ===")
    print(f"{'N':>5s} {'IC':>9s} {'IR pred':>8s} {'IR meas':>8s} {'ratio':>7s}")
    irs = []
    for n in sorted(results):
        ic = results[n]["ic"]
        pred = ic * np.sqrt(n * rebals)
        meas = results[n]["ir"]
        irs.append(meas)
        ratio = meas / pred if abs(pred) > 1e-9 else float("nan")
        print(f"{n:>5d} {ic:>+9.4f} {pred:>8.2f} {meas:>8.2f} {ratio:>7.2f}")

    monotonic = all(b >= a - 0.05 for a, b in zip(irs, irs[1:]))
    tradeable = any(results[n]["net"] > 0 for n in results)

    print("\n" + "=" * 58)
    print(f"IR monotonic in N      : {monotonic}")
    print(f"any N net of costs > 0 : {tradeable}")
    print(f"best IC seen           : {max(r['ic'] for r in results.values()):+.4f}"
          f"   (ETF universe reached +0.109)")
    if monotonic and tradeable:
        print("PHASE C CONFIRMED - breadth was the constraint.")
    elif monotonic:
        print("PARTIAL - IR does rise with N, but the signal on single names "
              "is\ntoo weak for any N tested to survive costs.")
    else:
        print("PHASE C REFUTED - breadth is not the constraint.")
    print("=" * 58)
    print("\nLevels are survivorship-inflated (today's large caps). The "
          "scaling\nrelationship is the claim; the absolute IR is not.")


if __name__ == "__main__":
    main()
