"""Per-stock signals, and the measurement that decides whether they matter.

The signals are deliberately classic and literature-grounded rather than
invented here - see papers/. Inventing new ones is how the earlier phases of
this project generated false positives.

ic_report() is the important function. Portfolio construction converts a
signal into returns efficiently; it cannot create signal. If the information
coefficient is ~0.02 (which is what
findings/phase-c-breadth-was-not-the-constraint.md measured on price-only
features), no weighting scheme rescues it. Measure first.
"""

import numpy as np
import pandas as pd

BPY = 252


def _rank_corr(a, b):
    """Spearman without scipy - it is just Pearson on the ranks."""
    return a.rank().corr(b.rank())


def _zscore_cs(df):
    """Cross-sectional z-score: each date scored against that date's peers.

    Cross-sectional, not time-series - the whole point is ranking names
    against each other on a given day.
    """
    mu = df.mean(axis=1)
    sd = df.std(axis=1).replace(0, np.nan)
    return df.sub(mu, axis=0).div(sd, axis=0)


def momentum_12_1(px, long=252, skip=21):
    """Jegadeesh-Titman 12-1: past year's return, skipping the last month.

    The skip avoids short-term reversal contaminating the momentum signal.
    """
    return px.shift(skip) / px.shift(long) - 1.0


def reversal_1m(px, window=21):
    """Short-term reversal: recent losers bounce. Sign is negated."""
    return -(px / px.shift(window) - 1.0)


def low_volatility(px, window=126):
    """Low-vol anomaly: lower realised volatility, higher risk-adjusted return."""
    return -px.pct_change().rolling(window).std()


def trend(px, window=200):
    """Distance above the long moving average."""
    return px / px.rolling(window).mean() - 1.0


SIGNALS = {
    "mom_12_1": momentum_12_1,
    "reversal": reversal_1m,
    "low_vol": low_volatility,
    "trend": trend,
}


def build(px, names=None):
    """Return {signal_name: cross-sectionally z-scored DataFrame}."""
    names = names or list(SIGNALS)
    return {n: _zscore_cs(SIGNALS[n](px)) for n in names}


def combine(signals, weights=None):
    """Equal-weight blend of z-scores unless told otherwise.

    Equal weight by default on purpose: fitting blend weights on the same
    data that will be evaluated is the mistake catalogued in IDEAS.md.
    """
    weights = weights or {k: 1.0 for k in signals}
    total = sum(weights.values())
    out = None
    for k, w in weights.items():
        term = signals[k] * (w / total)
        out = term if out is None else out.add(term, fill_value=0.0)
    return _zscore_cs(out)


def forward_return(px, horizon=21):
    """Return realised over the NEXT `horizon` bars, aligned to the signal date."""
    return (px.shift(-horizon) / px - 1.0)


def ic_report(px, horizon=21, min_names=20):
    """Rank information coefficient per signal.

    IC is the cross-sectional Spearman correlation between a signal and the
    forward return, averaged over dates. It answers "does this ranking
    predict anything" before any portfolio exists.

    Returns a DataFrame: mean IC, its t-stat, and hit rate.
    """
    fwd = forward_return(px, horizon)
    sigs = build(px)
    rows = []

    for name, s in sigs.items():
        ics = []
        # step by horizon so the forward windows do not overlap - overlapping
        # samples inflate the t-stat badly
        for d in s.index[::horizon]:
            if d not in fwd.index:
                continue
            a, b = s.loc[d], fwd.loc[d]
            ok = a.notna() & b.notna()
            if ok.sum() < min_names:
                continue
            ics.append(_rank_corr(a[ok], b[ok]))
        ics = pd.Series(ics).dropna()
        if len(ics) < 10:
            continue
        t = ics.mean() / ics.std() * np.sqrt(len(ics)) if ics.std() else 0.0
        rows.append(dict(signal=name, n=len(ics), ic=ics.mean(),
                         ic_std=ics.std(), t=t, hit=(ics > 0).mean()))

    combo = combine(sigs)
    ics = []
    for d in combo.index[::horizon]:
        if d not in fwd.index:
            continue
        a, b = combo.loc[d], fwd.loc[d]
        ok = a.notna() & b.notna()
        if ok.sum() >= min_names:
            ics.append(_rank_corr(a[ok], b[ok]))
    ics = pd.Series(ics).dropna()
    if len(ics) >= 10:
        t = ics.mean() / ics.std() * np.sqrt(len(ics)) if ics.std() else 0.0
        rows.append(dict(signal="COMBINED", n=len(ics), ic=ics.mean(),
                         ic_std=ics.std(), t=t, hit=(ics > 0).mean()))

    return pd.DataFrame(rows).set_index("signal")


def implied_ir(ic, n_names, rebals_per_year=12):
    """Grinold: IR ~ IC x sqrt(breadth), breadth = names x rebalances.

    An upper bound assuming independent bets. Real names are correlated, so
    treat it as a ceiling - measured IR ran about 40% of this in
    findings/phase-c-breadth-was-not-the-constraint.md.
    """
    return ic * np.sqrt(n_names * rebals_per_year)
