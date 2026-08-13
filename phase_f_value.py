"""Phase F: add value to trend on the futures book.

Phase A's blend failed because its components were 0.67-0.69 correlated to
SPY - the same long-equity bet three times. Asness, Moskowitz & Pedersen
(2013) name the missing ingredient: value and momentum are NEGATIVELY
correlated with each other, which is where the combined Sharpe comes from.

For non-equity assets they define value as long-horizon reversal, computable
from price alone - roughly the negated 5-year return. That works on the same
31 futures Phase E validated the engine on.

Carry is not included: it needs front-versus-deferred contract prices and
Yahoo serves only continuous front-month. Inventing it from one series would
be fabricating data.

    uv run --with yfinance --with pandas --with numpy python phase_f_value.py
"""

import numpy as np
import pandas as pd

from swing_lab import fetch
from phase_d_trend import VOL_TARGET, metrics, signals
from phase_e_futures import ERAS, FEE_FUT, SECTORS

BPY = 252
VALUE_LOOKBACK = 5 * BPY      # 5-year reversal, per AMP 2013
VALUE_REBAL = 21              # monthly
GATE_CORR = 0.30
GATE_SHARPE = 0.42            # trend-only era B was 0.35


def clean_returns(df):
    r = df["close"].pct_change().fillna(0.0)
    # Same winsorisation as phase_d_trend: Yahoo's continuous futures are
    # unadjusted, so rolls appear as fake returns.
    return r.replace([np.inf, -np.inf], 0.0).clip(-0.25, 0.25)


def vol_scale(ret):
    realised = ret.rolling(63).std() * np.sqrt(BPY)
    return (VOL_TARGET / realised).clip(upper=3.0).shift(1).fillna(0.0)


def trend_sleeve(df, p, fee=FEE_FUT):
    pos = signals(df, p["entry_n"], p["exit_n"], p["atr_mult"], p["short"])
    ret = clean_returns(df)
    sc = vol_scale(ret)
    return pos * sc * ret - (pos * sc).diff().abs().fillna(0.0) * fee


def value_sleeve(df, fee=FEE_FUT):
    """Long-horizon reversal: cheap = fell over 5 years, rich = rose.

    Sign is the opposite of momentum by construction, which is exactly why
    the two are expected to diversify each other.
    """
    close = df["close"]
    past = close.shift(VALUE_LOOKBACK)
    five_yr = (close / past - 1.0)

    raw = -np.sign(five_yr)                 # cheap -> long, rich -> short
    raw = raw.where(five_yr.notna(), 0.0)

    # Rebalance monthly rather than daily; value is a slow signal and daily
    # flipping would pay costs for nothing.
    pos = raw.where(np.arange(len(raw)) % VALUE_REBAL == 0).ffill().fillna(0.0)
    pos = pos.shift(1).fillna(0.0)          # decided on t, held from t+1

    ret = clean_returns(df)
    sc = vol_scale(ret)
    return pos * sc * ret - (pos * sc).diff().abs().fillna(0.0) * fee


def value_book_cs(frames, lo, hi, fee=FEE_FUT):
    """Cross-sectional value, as AMP 2013 actually define it.

    The time-series version above asks "did this fall over 5 years?" in
    isolation. AMP rank assets AGAINST EACH OTHER and go long the cheap
    tertile, short the rich one - a market-neutral spread, not an absolute
    call. That distinction is the same one that made Phase B's long-only
    framing unfair.
    """
    closes, rets, scales = {}, {}, {}
    for t, df in frames.items():
        sub = df[(df.index >= lo) & (df.index <= hi)]
        if len(sub) < 400:
            continue
        closes[t] = sub["close"]
        r = clean_returns(sub)
        rets[t] = r
        scales[t] = vol_scale(r)

    if len(closes) < 6:
        return None

    px = pd.DataFrame(closes).dropna(how="all").ffill()
    rt = pd.DataFrame(rets).reindex(px.index).fillna(0.0)
    sc = pd.DataFrame(scales).reindex(px.index).fillna(0.0)

    five_yr = px / px.shift(VALUE_LOOKBACK) - 1.0
    rank = five_yr.rank(axis=1, pct=True)          # 1.0 = most expensive

    n_side = max(1, len(px.columns) // 3)          # tertiles
    pos = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    pos[rank <= (n_side / len(px.columns))] = 1.0   # cheap -> long
    pos[rank >= 1 - (n_side / len(px.columns))] = -1.0  # rich -> short
    pos = pos.where(five_yr.notna(), 0.0)

    mask = pd.Series(np.arange(len(pos)) % VALUE_REBAL == 0, index=pos.index)
    pos = pos.where(mask, np.nan).ffill().fillna(0.0).shift(1).fillna(0.0)

    gross = (pos * sc * rt)
    cost = (pos * sc).diff().abs().fillna(0.0) * fee
    return (gross - cost).mean(axis=1)


def book(frames, fn, lo, hi, **kw):
    sleeves = {}
    for t, df in frames.items():
        sub = df[(df.index >= lo) & (df.index <= hi)]
        if len(sub) < 400:
            continue
        sleeves[t] = fn(sub, **kw)
    if not sleeves:
        return None
    return pd.DataFrame(sleeves).fillna(0.0).mean(axis=1)


def main():
    print("PHASE F - trend + value on futures")
    print(f"gates: corr < {GATE_CORR}, combined Sharpe > {GATE_SHARPE}\n")

    frames = {}
    for tickers in SECTORS.values():
        for t in tickers:
            df = fetch(t, "1d")
            if df is not None and len(df) > 2000:
                frames[t] = df
    print(f"universe: {len(frames)} futures\n")

    # Trend config: best long-only from Phase E, chosen on era A (the control
    # era), never on era B which is what we are scoring.
    trend_p = dict(entry_n=100, exit_n=20, atr_mult=3.0, short=False)

    for era, (lo, hi) in ERAS.items():
        tr = book(frames, trend_sleeve, lo, hi, p=trend_p)
        va_ts = book(frames, value_sleeve, lo, hi)
        va = value_book_cs(frames, lo, hi)
        if tr is None or va is None:
            continue

        both = pd.DataFrame({"trend": tr, "value": va}).dropna()
        corr = both["trend"].corr(both["value"])
        if va_ts is not None:
            c2, d2, s2 = metrics(va_ts.reindex(both.index).fillna(0.0))
            print(f"  (time-series value, for contrast: Sharpe {s2:+.2f})")

        eq = both.mean(axis=1)
        iv = 1.0 / both.std()
        iv /= iv.sum()
        ivb = (both * iv).sum(axis=1)

        print(f"=== {era} ===")
        print(f"  trend/value correlation : {corr:>+6.3f}")
        for label, r in (("trend only", both["trend"]),
                         ("value only", both["value"]),
                         ("blend equal-weight", eq),
                         ("blend inverse-vol", ivb)):
            c, d, s = metrics(r)
            print(f"  {label:20s} CAGR {c:>+7.2%}  maxDD {d:>7.1%}  "
                  f"Sharpe {s:>+5.2f}")
        print()

        if era.startswith("B"):
            best = max(metrics(eq)[2], metrics(ivb)[2])
            g1, g2 = corr < GATE_CORR, best > GATE_SHARPE
            print("=== GATE (era B, the live regime) ===")
            print(f"   [{'x' if g1 else ' '}] correlation {corr:+.3f} < {GATE_CORR}")
            print(f"   [{'x' if g2 else ' '}] best blend Sharpe {best:.2f} > {GATE_SHARPE}")
            print("\n" + "=" * 58)
            if g1 and g2:
                print("PHASE F PASSED - value diversifies trend and the blend wins.")
            elif g1:
                print("PARTIAL - the sleeves are uncorrelated, but the blend does")
                print("not clear the trend-only sleeve. Diversification without")
                print("enough underlying signal.")
            else:
                print("PHASE F FAILED - price-derived value is not distinct from")
                print("price-derived momentum here. The combination idea is closed,")
                print("not merely untuned.")
            print("=" * 58)


if __name__ == "__main__":
    main()
