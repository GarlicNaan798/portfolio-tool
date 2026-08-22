"""Does the oil mean-reversion edge only exist after a crash?

findings/oil-mean-reversion-edge-is-three-years.md showed the whole Sharpe
advantage lives in 2016, 2021 and 2026 - all sharp recoveries from a
collapse. If the rule only pays when oil is already deeply below its peak,
that is a narrower and far more honest strategy than "trade oil mean
reversion", and it is testable.

Method: tag every trade with the underlying's drawdown from its own running
peak AT ENTRY - information available at the time, no lookahead - then bucket
outcomes by that depth.

If profit is flat across buckets, drawdown is irrelevant and the three-year
concentration was coincidence. If it concentrates in the deep buckets, the
rule is a crash-recovery trade wearing a mean-reversion costume.

    uv run --with yfinance --with pandas --with numpy python crash_recovery.py
"""

import argparse

import numpy as np
import pandas as pd

from swing import BPY, atr, dv2, load, self_check

BUCKETS = [(0.00, 0.10, "0-10%"), (0.10, 0.25, "10-25%"),
           (0.25, 0.50, "25-50%"), (0.50, 1.01, ">50%")]


def trades_with_context(df, fee, buy_below=40.0, sell_above=70.0):
    """Re-run the mean-reversion rule, recording context at each entry.

    Drawdown is computed from the running peak of closes UP TO that bar, so
    it uses nothing the trader would not have known.
    """
    d = df.copy()
    d["dv2"] = dv2(d)
    d["sma200"] = d["close"].rolling(200).mean()
    d["peak"] = d["close"].cummax()
    d["dd"] = 1.0 - d["close"] / d["peak"]
    d["atr"] = atr(d)
    d = d.dropna(subset=["dv2", "sma200", "atr"])

    rows = list(d.itertuples())
    out = []
    entry = None

    for i in range(1, len(rows)):
        prev, bar = rows[i - 1], rows[i]
        fill = bar.open
        bull = prev.close > prev.sma200

        if entry is not None and (prev.dv2 > sell_above or not bull):
            ret = (fill * (1 - fee)) / (entry["px"] * (1 + fee)) - 1.0
            out.append({**entry, "exit_px": fill, "ret": ret,
                        "days": i - entry["i"], "exit_date": bar.Index})
            entry = None
        elif entry is None and bull and prev.dv2 < buy_below:
            entry = {"i": i, "px": fill, "date": bar.Index,
                     "dd": prev.dd, "dv2": prev.dv2,
                     "vol": float(prev.atr / prev.close)}

    return pd.DataFrame(out)


def report(t, label):
    print(f"\n{'=' * 68}\n{label}  ({len(t)} closed trades)\n{'=' * 68}")
    print(f"{'drawdown at entry':>18s} {'n':>5s} {'win%':>6s} {'avg ret':>9s} "
          f"{'total':>9s} {'share of P&L':>13s}")

    total_pnl = t["ret"].sum()
    for lo, hi, name in BUCKETS:
        sub = t[(t["dd"] >= lo) & (t["dd"] < hi)]
        if sub.empty:
            print(f"{name:>18s} {0:>5d}       -         -         -")
            continue
        share = sub["ret"].sum() / total_pnl if total_pnl else float("nan")
        print(f"{name:>18s} {len(sub):>5d} {(sub['ret'] > 0).mean():>6.0%} "
              f"{sub['ret'].mean():>9.2%} {sub['ret'].sum():>9.1%} "
              f"{share:>13.0%}")

    print(f"{'ALL':>18s} {len(t):>5d} {(t['ret'] > 0).mean():>6.0%} "
          f"{t['ret'].mean():>9.2%} {total_pnl:>9.1%} {1.0:>13.0%}")

    deep = t[t["dd"] >= 0.25]
    shallow = t[t["dd"] < 0.25]
    if len(deep) > 5 and len(shallow) > 5:
        print(f"\ndeep (>=25% below peak)   {len(deep):>4d} trades, "
              f"mean {deep['ret'].mean():>+7.2%}")
        print(f"shallow (<25%)            {len(shallow):>4d} trades, "
              f"mean {shallow['ret'].mean():>+7.2%}")
        # Welch t-test without scipy: unequal variances.
        a, b = deep["ret"], shallow["ret"]
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        tstat = (a.mean() - b.mean()) / se if se > 0 else 0.0
        print(f"difference                {a.mean() - b.mean():>+7.2%}  "
              f"t = {tstat:.2f}")
        if abs(tstat) < 2:
            print("\nNot a significant difference. Depth of drawdown does not")
            print("explain where the profit came from.")
        else:
            print("\nSignificant. The rule is materially a crash-recovery trade.")


def by_year_share(t):
    print(f"\n{'=' * 68}\nwhere the P&L sits by year\n{'=' * 68}")
    t = t.copy()
    t["year"] = t["date"].dt.year
    g = t.groupby("year")["ret"].agg(["count", "sum", "mean"])
    g["mean_dd"] = t.groupby("year")["dd"].mean()
    top = g.sort_values("sum", ascending=False).head(6)
    print(f"{'year':>6s} {'trades':>7s} {'sum ret':>9s} {'avg dd at entry':>16s}")
    for y, r in top.iterrows():
        print(f"{y:>6.0f} {r['count']:>7.0f} {r['sum']:>9.1%} {r['mean_dd']:>16.0%}")
    print(f"\nmean drawdown at entry, all trades: {t['dd'].mean():.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="CL=F")
    ap.add_argument("--fee-bps", type=float, default=1.5)
    a = ap.parse_args()

    self_check()
    df = load(a.symbol)
    t = trades_with_context(df, a.fee_bps / 10_000)
    if t.empty:
        print("no trades")
        return
    report(t, f"{a.symbol}: trade outcome vs drawdown at entry")
    by_year_share(t)


if __name__ == "__main__":
    main()
