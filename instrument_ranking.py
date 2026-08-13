"""Which instrument actually carries statistical evidence for swing trading?

Ranks every market by the trend sleeve's Sharpe, then asks whether any of
them is distinguishable from luck once you account for having tested 31 of
them at the same time.

Statistics:
  Lo (2002) gives the standard error of an annualised Sharpe over T years as
      SE(SR) = sqrt((1 + SR^2 / 2) / T)
  so  t = SR / SE,  and a two-sided p follows from the normal.

  Testing N markets and reporting the best inflates the false-positive rate.
  Bonferroni holds family-wise error at 5% by requiring p < 0.05 / N. It is
  conservative, which is the correct direction when the alternative is
  trading real money on a fluke.

    uv run --with yfinance --with pandas --with numpy --with scipy \
        python instrument_ranking.py
"""

import numpy as np
import pandas as pd
from scipy import stats

from swing_lab import UNIVERSE_1D, fetch
from phase_d_trend import metrics, sleeve
from phase_e_futures import ERAS, FEE_FUT, SECTORS

FEE_ETF = 0.0025
CONFIG = dict(entry_n=100, exit_n=20, atr_mult=3.0, short=False)
BPY = 252


def sharpe_stats(ret, years):
    """Annualised Sharpe with Lo (2002) standard error, t and two-sided p."""
    if ret.std() == 0 or years <= 0:
        return 0.0, 0.0, 0.0, 1.0
    sr = ret.mean() / ret.std() * np.sqrt(BPY)
    se = np.sqrt((1 + sr ** 2 / 2) / years)
    t = sr / se
    p = 2 * (1 - stats.norm.cdf(abs(t)))
    return sr, se, t, p


def run_universe(tickers, fee, lo, hi, label):
    rows, streams = [], {}
    for t in tickers:
        df = fetch(t, "1d")
        if df is None:
            continue
        sub = df[(df.index >= lo) & (df.index <= hi)]
        if len(sub) < 400:
            continue
        r = sleeve(sub, CONFIG, fee=fee)
        years = len(r) / BPY
        sr, se, tstat, p = sharpe_stats(r, years)

        bh = sub["close"].pct_change().fillna(0.0).clip(-0.25, 0.25)
        bh_sr = bh.mean() / bh.std() * np.sqrt(BPY) if bh.std() else 0.0

        rows.append(dict(ticker=t, sr=sr, se=se, t=tstat, p=p,
                         years=years, bh=bh_sr))
        streams[t] = r
    return rows, streams


def report(rows, streams, label, years_note):
    if not rows:
        print(f"\n{label}: no data")
        return None

    n = len(rows)
    bonf = 0.05 / n
    rows.sort(key=lambda r: -r["sr"])

    print(f"\n{'=' * 78}")
    print(f"{label}   ({n} markets, {years_note})")
    print(f"Bonferroni threshold: p < 0.05/{n} = {bonf:.4f}")
    print("=" * 78)
    print(f"{'market':8s} {'trend SR':>9s} {'SE':>6s} {'t':>6s} {'p':>8s} "
          f"{'B&H SR':>7s}  verdict")
    for r in rows:
        if r["p"] < bonf:
            v = "SURVIVES correction"
        elif r["p"] < 0.05:
            v = "nominal only"
        else:
            v = ""
        print(f"{r['ticker']:8s} {r['sr']:>9.2f} {r['se']:>6.2f} {r['t']:>6.2f} "
              f"{r['p']:>8.4f} {r['bh']:>7.2f}  {v}")

    survivors = [r for r in rows if r["p"] < bonf]
    nominal = [r for r in rows if r["p"] < 0.05]
    print(f"\n  survive Bonferroni : {len(survivors)}/{n}")
    print(f"  nominally p<0.05   : {len(nominal)}/{n}  "
          f"(expected by chance alone: {0.05 * n:.1f})")

    # The diversified portfolio - which is what the literature actually claims
    port = pd.DataFrame(streams).fillna(0.0).mean(axis=1)
    yrs = len(port) / BPY
    sr, se, t, p = sharpe_stats(port, yrs)
    print(f"\n  EQUAL-WEIGHT PORTFOLIO  SR {sr:.2f}  SE {se:.2f}  "
          f"t {t:.2f}  p {p:.4f}")
    return dict(sr=sr, t=t, p=p, survivors=len(survivors), n=n)


def main():
    print("WHICH INSTRUMENT CARRIES THE EVIDENCE?")
    print("Trend sleeve, Donchian 100/20, 3x ATR trailing stop, long only.\n")
    print("A single market's Sharpe over ~16 years has SE ~0.25, so even")
    print("SR 0.5 gives t~2 - nominally significant, and worthless once you")
    print("have looked at 31 of them.")

    fut = [t for ts in SECTORS.values() for t in ts]

    out = {}
    for era, (lo, hi) in ERAS.items():
        yrs = f"{lo[:4]}-{hi[:4]}"
        out[f"futures {era[0]}"] = report(
            *run_universe(fut, FEE_FUT, lo, hi, era),
            label=f"FUTURES, era {era}", years_note=yrs)

    out["etf"] = report(
        *run_universe(UNIVERSE_1D, FEE_ETF, "2010-01-01", "2026-12-31", "etf"),
        label="EQUITY ETFs, 2010-2026 (at 25bps/side)",
        years_note="2010-2026")

    print(f"\n{'=' * 78}")
    print("CONCLUSION")
    print("=" * 78)
    for k, v in out.items():
        if v:
            print(f"  {k:12s} portfolio SR {v['sr']:>5.2f}  t {v['t']:>5.2f}  "
                  f"p {v['p']:.4f}   single-market survivors {v['survivors']}/{v['n']}")


if __name__ == "__main__":
    main()
