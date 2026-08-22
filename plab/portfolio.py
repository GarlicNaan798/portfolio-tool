"""Turning scores into weights, and weights into a tested equity curve.

This is the step every earlier phase skipped. They all used equal-weight
top-N, which is one construction method among several and not usually the
best one. Grinold's law says IR ~ IC x sqrt(breadth); construction is how
efficiently a given IC is converted into IR.

Construction methods here, cheapest assumption first:
    equal        every selected name the same weight
    inv_vol      weight by 1/volatility - the risk-parity approximation
    mean_var     mean-variance with a shrunk covariance, long-only

Shrinkage matters: a sample covariance over N names needs far more history
than we have to be invertible and stable. Ledoit-Wolf style shrinkage toward
a diagonal target is the standard fix and is implemented directly rather than
pulled in as a dependency.
"""

import numpy as np
import pandas as pd

from plab import metrics

BPY = 252


# ---------------------------------------------------------------- risk model
def shrunk_cov(returns, shrink=None):
    """Sample covariance pulled toward a diagonal target.

    shrink=None picks an automatic intensity from the ratio of off-diagonal
    mass to total - crude compared with full Ledoit-Wolf, but it removes the
    dependency and the failure mode it guards against (an unstable inverse)
    is the same.
    """
    r = returns.dropna(axis=1, how="all").dropna()
    if r.shape[0] < 20 or r.shape[1] < 2:
        return None
    S = r.cov().values
    n = S.shape[0]
    target = np.diag(np.diag(S))
    if shrink is None:
        off = S - target
        denom = (S ** 2).sum()
        shrink = float(np.clip((off ** 2).sum() / denom, 0.1, 0.9)) if denom else 0.5
    return pd.DataFrame(shrink * target + (1 - shrink) * S,
                        index=r.columns, columns=r.columns)


# ------------------------------------------------------------- constructions
def equal_weight(selected, **_):
    if len(selected) == 0:
        return pd.Series(dtype=float)
    return pd.Series(1.0 / len(selected), index=selected)


def inverse_vol(selected, vol=None, **_):
    if len(selected) == 0:
        return pd.Series(dtype=float)
    if vol is None or len(vol) == 0:
        return equal_weight(selected)   # too little history to size on risk
    v = vol.reindex(selected).replace(0, np.nan)
    if v.isna().all():
        return equal_weight(selected)
    w = (1.0 / v).fillna(0.0)
    return w / w.sum() if w.sum() else equal_weight(selected)


def mean_variance(selected, scores=None, cov=None, max_w=0.10, ridge=1e-4, **_):
    """Long-only mean-variance, solved by projected gradient.

    No solver dependency: maximise w'a - (lambda/2) w'Sw subject to w >= 0,
    sum(w) = 1 and w <= max_w, by gradient steps with a projection onto the
    simplex after each. Slower than a QP but transparent, and the cap plus
    the shrunk covariance matter far more than the solver does.
    """
    if len(selected) == 0:
        return pd.Series(dtype=float)
    if cov is None or scores is None:
        return equal_weight(selected)

    names = [s for s in selected if s in cov.index]
    if len(names) < 2:
        return equal_weight(selected)

    a = scores.reindex(names).fillna(0.0).values
    S = cov.loc[names, names].values + np.eye(len(names)) * ridge
    w = np.full(len(names), 1.0 / len(names))
    lam = 10.0
    step = 0.01 / (np.abs(S).max() or 1.0)

    for _ in range(300):
        grad = a - lam * S.dot(w)
        w = _project(w + step * grad, max_w)
    return pd.Series(w, index=names)


def _project(w, max_w):
    """Project onto {w >= 0, sum w = 1, w <= max_w}."""
    w = np.clip(w, 0.0, max_w)
    total = w.sum()
    if total <= 0:
        return np.full(len(w), min(max_w, 1.0 / len(w)))
    w = w / total
    # capping can break the sum, so iterate a few times
    for _ in range(20):
        over = w > max_w
        if not over.any():
            break
        excess = (w[over] - max_w).sum()
        w[over] = max_w
        room = ~over
        if not room.any():
            break
        w[room] += excess * w[room] / w[room].sum()
    return w


METHODS = {"equal": equal_weight, "inv_vol": inverse_vol,
           "mean_var": mean_variance}


# ------------------------------------------------------------------- backtest
def run(px, scores, method="equal", top_n=20, rebal=21, fee_bps=5.0,
        cov_window=252, max_w=0.10, start=None):
    """Rebalance into the top_n names by score, every `rebal` bars.

    Scores are read on the rebalance bar and the weights apply from the NEXT
    bar, so nothing is traded on information from its own bar. Costs are
    charged on turnover, both sides.
    """
    fee = fee_bps / 10_000.0
    rets = px.pct_change().fillna(0.0)
    dates = list(px.index)
    weights = pd.Series(dtype=float)
    equity, curve, idx, turn_log = 1.0, [], [], []

    rebal_points = set(dates[::rebal])

    for i in range(1, len(dates)):
        d = dates[i]
        # yesterday's weights earn today's return
        if len(weights):
            equity *= 1.0 + float((weights * rets.loc[d].reindex(weights.index)
                                   .fillna(0.0)).sum())

        if dates[i - 1] in rebal_points:
            s = scores.loc[dates[i - 1]].dropna()
            if len(s) >= top_n:
                sel = list(s.nlargest(top_n).index)
                hist = rets.loc[:dates[i - 1]].tail(cov_window)
                sub = hist[[c for c in sel if c in hist.columns]]
                kw = dict(scores=s, max_w=max_w,
                          vol=(sub.std() * np.sqrt(BPY)) if len(sub) > 20 else None,
                          cov=shrunk_cov(sub) if method == "mean_var" else None)
                new = METHODS[method](sel, **kw)
                new = new[new > 1e-6]

                allnames = weights.index.union(new.index)
                turnover = float((new.reindex(allnames).fillna(0.0)
                                  - weights.reindex(allnames).fillna(0.0))
                                 .abs().sum())
                equity *= 1.0 - fee * turnover
                turn_log.append(turnover)
                weights = new

        curve.append(equity)
        idx.append(d)

    eq = pd.Series(curve, index=idx)
    if start is not None:
        eq = eq[eq.index >= start]
        eq = eq / eq.iloc[0] if len(eq) else eq
    return eq, (float(np.mean(turn_log)) if turn_log else 0.0)


def benchmark(px_bench, index, start=None):
    b = px_bench.reindex(index).ffill().dropna()
    if start is not None:
        b = b[b.index >= start]
    return b / b.iloc[0] if len(b) else b


def report(eq, label="portfolio"):
    return metrics.fmt(label, metrics.summary(eq.pct_change().dropna()))
