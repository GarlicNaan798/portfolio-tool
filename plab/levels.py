"""Support/resistance holding, and a macro overlay.

Replaces fixed monthly holding with event-driven exits: buy a stock sitting
near the bottom of its own recent range, hold it until it reaches the top,
then sell. Positions are opened and closed when something HAPPENS, not on a
calendar.

Support and resistance are mechanical - the rolling low and high of a
lookback window. Hand-drawn levels cannot be backtested, which means they
also cannot be shown to fail. See IDEAS.md.

Three exits, because a level-based trade can end three ways:
    target   price reached resistance      - the thesis worked
    stop     price broke below support     - the level failed
    time     held too long without either  - capital is being wasted

The macro overlay scales how much of the book is deployed based on the
market's own trend. It gates NEW entries only; positions already open are
left to reach their own targets, so a regime flip does not dump the book at
the worst moment.
"""

import numpy as np
import pandas as pd

from plab import metrics

BPY = 252


def levels(px, window=63):
    """Rolling support and resistance, shifted so today's bar is excluded."""
    support = px.rolling(window).min().shift(1)
    resistance = px.rolling(window).max().shift(1)
    return support, resistance


def range_position(px, support, resistance):
    """Where price sits in its own range. 0 = at support, 1 = at resistance.

    Scale-free, so a $12 stock and a $900 stock are directly comparable -
    which is what makes it usable as a cross-sectional score.
    """
    span = (resistance - support).replace(0, np.nan)
    return ((px - support) / span).clip(-0.5, 1.5)


def macro_regime(bench_px, fast=50, slow=200):
    """Market trend, as a fraction of the book to deploy.

    1.0  benchmark above both averages          - fully invested
    0.5  above one                              - half
    0.0  below both                             - stand aside

    Deliberately coarse. A finely tuned regime model is a parameter search
    over the same data everything else is tested on.
    """
    f = bench_px.rolling(fast).mean()
    s = bench_px.rolling(slow).mean()
    score = ((bench_px > f).astype(float) + (bench_px > s).astype(float)) / 2.0
    return score.shift(1)      # decided on yesterday's close


def run(px, scores, bench_px=None, slots=20, window=63, entry_max=0.30,
        exit_at=0.90, stop_below=-0.10, max_hold=126, fee_bps=5.0,
        use_macro=True, start=None):
    """Event-driven support/resistance portfolio.

    slots        how many positions can be open at once
    entry_max    buy only if range position is below this (0.30 = lower third)
    exit_at      sell when range position reaches this (0.90 = near resistance)
    stop_below   sell if range position falls this far under support
    max_hold     bars before giving up on a position that has done neither

    Every decision reads bar t-1 and fills at bar t's price, so nothing acts
    on its own bar.
    """
    fee = fee_bps / 10_000.0
    sup, res = levels(px, window)
    pos = range_position(px, sup, res)

    macro = (macro_regime(bench_px).reindex(px.index).ffill().fillna(0.0)
             if (use_macro and bench_px is not None)
             else pd.Series(1.0, index=px.index))

    cash, holdings = 1.0, {}          # ticker -> (shares_value_frac, entry_i)
    curve, idx = [], []
    n_entries = n_target = n_stop = n_time = 0
    hold_lens = []

    rets = px.pct_change().fillna(0.0)
    dates = list(px.index)

    for i in range(1, len(dates)):
        d, prev = dates[i], dates[i - 1]

        # existing positions earn today's return
        for t in list(holdings):
            val, ei = holdings[t]
            holdings[t] = (val * (1.0 + rets.at[d, t]), ei)

        # ---- exits, decided on yesterday's close ----
        for t in list(holdings):
            val, ei = holdings[t]
            p = pos.at[prev, t] if t in pos.columns else np.nan
            if np.isnan(p):
                continue
            why = None
            if p >= exit_at:
                why, n_target = "target", n_target + 1
            elif p <= stop_below:
                why, n_stop = "stop", n_stop + 1
            elif (i - ei) >= max_hold:
                why, n_time = "time", n_time + 1
            if why:
                cash += val * (1 - fee)
                hold_lens.append(i - ei)
                del holdings[t]

        # ---- entries ----
        deploy = float(macro.at[d]) if d in macro.index else 1.0
        allowed = int(round(slots * deploy))
        free = allowed - len(holdings)

        if free > 0 and prev in scores.index:
            s = scores.loc[prev].dropna()
            p_prev = pos.loc[prev]
            # candidates: scored well AND sitting low in their own range
            cand = [t for t in s.sort_values(ascending=False).index
                    if t not in holdings
                    and t in p_prev.index
                    and not np.isnan(p_prev[t])
                    and p_prev[t] <= entry_max]
            for t in cand[:free]:
                stake = cash / max(free, 1)
                if stake <= 0:
                    break
                cash -= stake
                holdings[t] = (stake * (1 - fee), i)
                n_entries += 1
                free -= 1

        curve.append(cash + sum(v for v, _ in holdings.values()))
        idx.append(d)

    eq = pd.Series(curve, index=idx)
    if start is not None:
        eq = eq[eq.index >= start]
        eq = eq / eq.iloc[0] if len(eq) else eq

    stats = dict(entries=n_entries, target=n_target, stop=n_stop, time=n_time,
                 avg_hold=float(np.mean(hold_lens)) if hold_lens else 0.0)
    return eq, stats


def report(eq, stats, label="levels"):
    line = metrics.fmt(label, metrics.summary(eq.pct_change().dropna()))
    tot = stats["target"] + stats["stop"] + stats["time"]
    if tot:
        line += (f"\n{'':22s} {stats['entries']} entries, exits: "
                 f"{stats['target'] / tot:.0%} target / "
                 f"{stats['stop'] / tot:.0%} stop / "
                 f"{stats['time'] / tot:.0%} time, "
                 f"avg hold {stats['avg_hold']:.0f} days")
    return line
