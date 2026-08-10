"""Phase B: can a learned model rank the cross-section?

Triggered by Phase A's failure. StockFormer's edge is cross-sectional
selection, so the model ranks a universe rather than timing one instrument.

Two deliberate departures from the paper, both in PLAN.md:
  * ETF universe, not S&P 500 constituents - point-in-time membership is not
    freely available and today's members would inject survivorship bias.
  * Gradient boosting before any transformer - if a GBM cannot rank these
    features, self-attention on the same features will not either.

Walk-forward, expanding window, with an embargo equal to the prediction
horizon so no training label overlaps the test window.

    uv run --with yfinance --with pandas --with numpy --with scikit-learn \
        python phase_b_ranker.py
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from swing_lab import FEE, UNIVERSE_1D, fetch

HORIZON = 21          # predict forward 21-bar return, rebalance monthly
TOP_N = 5
BPY = 252

FOLDS = [
    ("2011-01-01", "2017-12-31", "2018-01-01", "2019-12-31"),
    ("2011-01-01", "2019-12-31", "2020-01-01", "2022-12-31"),
    ("2011-01-01", "2022-12-31", "2023-01-01", "2026-12-31"),
]


def features_for(ticker):
    df = fetch(ticker, "1d")
    if df is None or len(df) < 600:
        return None
    c = df["close"]
    out = pd.DataFrame(index=df.index)

    for n in (21, 63, 126, 252):
        out[f"mom{n}"] = c.pct_change(n)
    out["vol21"] = c.pct_change().rolling(21).std()
    out["vol63"] = c.pct_change().rolling(63).std()
    out["d_sma50"] = c / c.rolling(50).mean() - 1
    out["d_sma200"] = c / c.rolling(200).mean() - 1

    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    out["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))

    # label: forward return over the horizon. Shifted so row t knows only
    # what is knowable at t; the target is realised at t+HORIZON.
    out["target"] = c.pct_change(HORIZON).shift(-HORIZON)
    out["fwd"] = out["target"]
    return out.dropna()


def build_panel(tickers):
    frames = []
    for t in tickers:
        f = features_for(t)
        if f is None:
            continue
        f = f.copy()
        f["ticker"] = t
        frames.append(f)
    panel = pd.concat(frames).sort_index()

    # Cross-sectional ranks: the model should judge instruments against each
    # other on a given day, not against absolute levels that drift over time.
    # Only keep dates where enough instruments exist to rank against.
    counts = panel.groupby(level=0).size()
    panel = panel[panel.index.isin(counts[counts >= 8].index)]

    feat_cols = [c for c in panel.columns if c not in ("ticker", "target", "fwd")]
    ranked = panel.groupby(level=0)[feat_cols].rank(pct=True)
    # Assign by position, NOT join/align: the index has one row per
    # (date, ticker) so it is non-unique, and joining on it would produce a
    # cartesian product that silently pairs a row with other tickers' ranks.
    for c in feat_cols:
        panel[f"r_{c}"] = ranked[c].values
    return panel, [f"r_{c}" for c in feat_cols]


def evaluate(panel, feat_cols, tr0, tr1, te0, te1):
    embargo = pd.Timedelta(days=int(HORIZON * 1.5))
    train = panel[(panel.index >= tr0) & (panel.index <= pd.Timestamp(tr1) - embargo)]
    test = panel[(panel.index >= te0) & (panel.index <= te1)]
    if len(train) < 2000 or len(test) < 200:
        return None

    model = HistGradientBoostingRegressor(
        max_depth=4, max_iter=250, learning_rate=0.05,
        l2_regularization=1.0, random_state=0)
    model.fit(train[feat_cols], train["target"])
    test = test.copy()
    test["pred"] = model.predict(test[feat_cols])

    # Monthly rebalance into the top-N predictions, equal weight.
    dates = sorted(test.index.unique())
    rebal_dates = dates[::HORIZON]
    rets, held = [], []
    for i, d in enumerate(rebal_dates[:-1]):
        day = test.loc[[d]] if isinstance(test.loc[d], pd.Series) else test.loc[d]
        if isinstance(day, pd.Series):
            continue
        picks = day.nlargest(min(TOP_N, len(day)), "pred")
        if picks.empty:
            continue
        r = float(picks["fwd"].mean()) - FEE * 2
        rets.append(r)
        held.append(list(picks["ticker"]))

    if len(rets) < 4:
        return None

    per_year = BPY / HORIZON
    s = pd.Series(rets)
    sharpe = s.mean() / s.std() * np.sqrt(per_year) if s.std() > 0 else 0.0
    eq = (1 + s).cumprod()
    cagr = eq.iloc[-1] ** (per_year / len(s)) - 1
    dd = (eq / eq.cummax() - 1).min()

    # benchmarks over the identical windows
    bench = {}
    for name, tick in (("SPY", "SPY"),):
        px = fetch(tick, "1d")["close"]
        px = px[(px.index >= te0) & (px.index <= te1)]
        br = px.pct_change(HORIZON).dropna()[::HORIZON]
        bench[name] = (br.mean() / br.std() * np.sqrt(per_year)
                       if br.std() > 0 else 0.0)

    ew = test.groupby(level=0)["fwd"].mean()
    ewr = ew.iloc[::HORIZON]
    bench["EW"] = ewr.mean() / ewr.std() * np.sqrt(per_year) if ewr.std() > 0 else 0.0

    return dict(cagr=cagr, dd=dd, sharpe=sharpe, n=len(rets),
                spy=bench["SPY"], ew=bench["EW"], held=held)


def main():
    print("PHASE B - learned cross-sectional ranker")
    print("gate: beat SPY AND equal-weight on Sharpe in >= 2 of 3 folds\n")

    panel, feat_cols = build_panel(UNIVERSE_1D)
    print(f"panel: {len(panel):,} rows, {panel['ticker'].nunique()} instruments, "
          f"{len(feat_cols)} features")
    print(f"{panel.index.min().date()} -> {panel.index.max().date()}\n")

    wins = 0
    for i, (tr0, tr1, te0, te1) in enumerate(FOLDS, 1):
        r = evaluate(panel, feat_cols, tr0, tr1, te0, te1)
        if r is None:
            print(f"fold {i}: insufficient data")
            continue
        beat = r["sharpe"] > r["spy"] and r["sharpe"] > r["ew"]
        wins += beat
        print(f"fold {i}  test {te0[:7]} -> {te1[:7]}  ({r['n']} rebalances)")
        print(f"   model  Sharpe {r['sharpe']:>5.2f}   CAGR {r['cagr']:>7.2%}   "
              f"maxDD {r['dd']:>7.1%}")
        print(f"   SPY    Sharpe {r['spy']:>5.2f}")
        print(f"   EW     Sharpe {r['ew']:>5.2f}")
        print(f"   -> {'BEAT both' if beat else 'did not beat both'}\n")

    print("=" * 58)
    print(f"folds won: {wins}/3")
    if wins >= 2:
        print("PHASE B PASSED - a transformer is now worth trying.")
    else:
        print("PHASE B FAILED - stop. The papers' material is exhausted.")
    print("=" * 58)


if __name__ == "__main__":
    main()
