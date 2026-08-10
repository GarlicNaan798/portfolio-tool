"""Phase A: does combining low-correlation strategies beat SPY on Sharpe?

Per PLAN.md. Components are fixed a priori from the source papers, blends use
fixed rules only, and the holdout is scored exactly once against criteria
registered before the run.

    uv run --with yfinance --with pandas --with numpy python phase_a_combine.py
"""

import numpy as np
import pandas as pd

from swing_lab import FEE, UNIVERSE_1D, add_indicators, fetch, run
from cross_sectional import panel, run as rotate

SPLIT = "2020-01-01"
BPY = 252

# Pre-registered gates (PLAN.md). Do not edit after seeing results.
GATE_SHARPE = 0.95
GATE_MAXDD = -0.25
GATE_CAGR = 0.08

COMPONENTS = {
    "tsmom": dict(variant="tsmom", lookback=252, use_sma200=True, atr_stop=None,
                  rsi_os=35.0, rsi_ob=70.0, max_bars=None, fee=FEE),
    "dip":   dict(variant="dip", lookback=63, use_sma200=True, atr_stop=None,
                  rsi_os=35.0, rsi_ob=70.0, max_bars=25, fee=FEE),
}
ROTATION = dict(j=252, top_n=5, rebal=21, gap=1, absolute=False)


def curve_to_returns(c):
    return c.pct_change().fillna(0.0)


def component_returns(name, p, tickers):
    """Equal-weight the per-instrument equity curves of one strategy."""
    per = {}
    for t in tickers:
        raw = fetch(t, "1d")
        if raw is None or len(raw) < 600:
            continue
        df = add_indicators(raw, p["lookback"])
        if len(df) < 400:
            continue
        c, _, _ = run(df, p)
        per[t] = curve_to_returns(c)
    if not per:
        return None
    return pd.DataFrame(per).mean(axis=1)   # equal weight, daily rebalanced


def metrics(rets):
    eq = (1 + rets).cumprod()
    years = len(eq) / BPY
    cagr = eq.iloc[-1] ** (1 / max(years, 0.1)) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = rets.mean() / rets.std() * np.sqrt(BPY) if rets.std() > 0 else 0.0
    return cagr, dd, sharpe


def show(label, rets):
    c, d, s = metrics(rets)
    print(f"{label:24s} CAGR {c:>7.2%}   maxDD {d:>7.1%}   Sharpe {s:>5.2f}")
    return c, d, s


def main():
    print("PHASE A - strategy combination")
    print(f"gates: Sharpe >= {GATE_SHARPE}, maxDD > {GATE_MAXDD:.0%}, "
          f"CAGR >= {GATE_CAGR:.0%}\n")

    comps = {}
    for name, p in COMPONENTS.items():
        r = component_returns(name, p, UNIVERSE_1D)
        if r is not None:
            comps[name] = r
        print(f"built {name}")

    px = panel(UNIVERSE_1D)
    rot_curve, _ = rotate(px, **ROTATION)
    comps["rotation"] = curve_to_returns(rot_curve)
    print("built rotation\n")

    df = pd.DataFrame(comps).dropna()
    spy = fetch("SPY", "1d")["close"]
    spy_r = spy.pct_change().reindex(df.index).fillna(0.0)

    ins = df[df.index < SPLIT]
    oos = df[df.index >= SPLIT]
    spy_oos = spy_r[spy_r.index >= SPLIT]

    print("=== component correlations (in-sample) ===")
    corr = ins.copy()
    corr["SPY"] = spy_r[spy_r.index < SPLIT]
    print(corr.corr().round(2).to_string(), "\n")

    print("=== in-sample components ===")
    for c in df.columns:
        show(c, ins[c])
    show("SPY", spy_r[spy_r.index < SPLIT])

    # Blend weights come from IN-SAMPLE only, by fixed rule - never fitted.
    inv_vol = 1.0 / ins.std()
    inv_vol /= inv_vol.sum()
    print(f"\ninverse-vol weights (in-sample): "
          f"{', '.join(f'{k}={v:.2f}' for k, v in inv_vol.items())}")

    print("\n=== OUT-OF-SAMPLE ===")
    for c in df.columns:
        show(c, oos[c])
    spy_m = show("SPY (benchmark)", spy_oos)

    blends = {
        "blend equal-weight": oos.mean(axis=1),
        "blend inverse-vol": (oos * inv_vol).sum(axis=1),
    }
    print()
    results = {k: show(k, v) for k, v in blends.items()}

    print("\n=== GATE ===")
    passed = False
    for name, (c, d, s) in results.items():
        checks = [
            (s >= GATE_SHARPE, f"Sharpe {s:.2f} >= {GATE_SHARPE}"),
            (d > GATE_MAXDD, f"maxDD {d:.1%} > {GATE_MAXDD:.0%}"),
            (c >= GATE_CAGR, f"CAGR {c:.2%} >= {GATE_CAGR:.0%}"),
        ]
        ok = all(x[0] for x in checks)
        print(f"\n{name}: {'PASS' if ok else 'FAIL'}")
        for good, text in checks:
            print(f"   [{'x' if good else ' '}] {text}")
        passed = passed or ok

    print("\n" + "=" * 58)
    if passed:
        print("PHASE A PASSED - refine the blend, do not pivot.")
    else:
        print("PHASE A FAILED - pivot to Phase B (learned cross-sectional ranker).")
    print("=" * 58)
    return passed


if __name__ == "__main__":
    main()
