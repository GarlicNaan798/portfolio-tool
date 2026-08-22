"""One instrument, one rule. Read it top to bottom in five minutes.

INSTRUMENT: WTI crude (CL=F). Oil mean-reverts hard, and holding it has been
punishing - buy and hold returned 3.77% a year with a 93% drawdown since
2000. That is the condition where a rule can add something.

THE RULE (mean reversion, the default)
    Measure where today's close sits inside its own bar, ranked against the
    last year of such readings. That is DV2 - a percentile, so it adapts to
    volatility instead of assuming a fixed scale.
    Buy when DV2 drops below 40 - the close is weak against its own history.
    Sell when DV2 rises above 70.
    Only while price is above its 200-day average. Long only.

THE OTHER RULE (breakout, --rule breakout)
    Buy above the 100-day high, trail a ratcheting 3xATR stop, exit below the
    20-day low. Kept because it is what survived the futures work - but on
    oil it does not hold up.

WHY MEAN REVERSION HERE
    Both rules were run on both oils, then stress-tested twice: delete
    calendar 2020, and delete each strategy's single best month.

        CL=F  DV2 bull    0.40  ->  ex-2020  0.37   ex-best-month  0.33
        CL=F  breakout    0.08  ->  ex-2020 -0.01
        BZ=F  breakout    0.30  ->  ex-2020  0.20   ex-best-month  0.21

    Mean reversion on WTI is the only combination that barely moves under
    both. The breakout rule leans on 2020 and on single months.

WHAT IT WILL NOT DO
    Be provable. Over 26 years the standard error on a Sharpe is about 0.20,
    so one instrument needs Sharpe above 0.8 to clear significance after
    correcting for how many were looked at. See
    findings/no-single-instrument-is-statistically-distinguishable.md.

    And the drawdowns here are severe. This is oil.

    uv run --with yfinance --with pandas --with numpy python swing.py
    uv run ... python swing.py --symbol BZ=F --rule breakout
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).parent / "data" / "cache"
BPY = 252
START_EQUITY = 10_000.0

DEFAULT_SYMBOL = "CL=F"

# Per side. Futures ~1-2bps, liquid ETFs ~1-5bps, thin ETFs 5-25bps. This one
# number has flipped a conclusion three times in this project - set it to what
# you actually pay, and check it against the instrument.
DEFAULT_FEE_BPS = 1.5


def load(symbol, refresh=False):
    """Daily bars, cached. Yahoo's cookie endpoint fails at random."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol.replace('=', '_')}_1d.csv"

    if path.exists() and not refresh:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        import yfinance as yf
        df = None
        for _ in range(3):
            try:
                got = yf.Ticker(symbol).history(period="max", interval="1d")
                if not got.empty:
                    df = got.rename(columns=str.lower)[
                        ["open", "high", "low", "close"]]
                    df.index = df.index.tz_localize(None)
                    df.to_csv(path)
                    break
            except Exception:
                pass
            time.sleep(2)
        if df is None:
            sys.exit(f"could not fetch {symbol}")

    # Continuous futures from Yahoo are unadjusted front-month, so contract
    # rolls appear as fake jumps and WTI's April 2020 print is negative - a
    # percentage change across zero is meaningless. Drop those bars.
    # ponytail: filtering, not back-adjusting. Paid roll-adjusted data is the
    # upgrade path if this ever needs to be precise.
    return df[(df["high"] >= df["low"]) & (df["close"] > 0) & (df["open"] > 0)]


def atr(df, n=14):
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - prev).abs(),
                    (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def dv2(df, lookback=252):
    """Where the close sits inside its bar, percentile-ranked over a year.

    Percentile ranking is what makes this volatility-adaptive: it assumes
    nothing about the shape of the return distribution.
    """
    mid = (df["high"] + df["low"]) / 2.0
    smooth = (df["close"] / mid - 1.0).rolling(2).mean()
    return smooth.rolling(lookback).apply(
        lambda w: (w[-1] > w[:-1]).sum() / (len(w) - 1) * 100.0, raw=True)


def backtest(df, rule, fee, entry_n=100, exit_n=20, stop_mult=3.0,
             buy_below=40.0, sell_above=70.0):
    """Signals read bar t. Fills happen at bar t+1's open. No lookahead."""
    d = df.copy()
    d["atr"] = atr(d)
    d["sma200"] = d["close"].rolling(200).mean()
    if rule == "breakout":
        d["resistance"] = d["high"].rolling(entry_n).max().shift(1)
        d["support"] = d["low"].rolling(exit_n).min().shift(1)
        d = d.dropna(subset=["atr", "resistance", "support"])
    else:
        d["dv2"] = dv2(d)
        d = d.dropna(subset=["atr", "sma200", "dv2"])

    equity, shares, stop = START_EQUITY, 0, 0.0
    curve, in_market, trades = [], [], []
    entry_px = entry_i = None

    rows = list(d.itertuples())
    for i in range(1, len(rows)):
        prev, bar = rows[i - 1], rows[i]
        fill = bar.open

        if rule == "breakout":
            if shares > 0:
                stop = max(stop, prev.close - stop_mult * prev.atr)
                hit, broke = bar.low <= stop, prev.close < prev.support
                if hit or broke:
                    px = stop if hit else fill
                    equity += shares * px * (1 - fee)
                    trades.append((entry_px, px, i - entry_i,
                                   "stop" if hit else "support"))
                    shares, entry_px, entry_i = 0, None, None
            if shares == 0 and prev.close > prev.resistance:
                n = int(equity // (fill * (1 + fee)))
                if n > 0:
                    equity -= n * fill * (1 + fee)
                    shares, entry_px, entry_i = n, fill, i
                    stop = fill - stop_mult * prev.atr
        else:
            bull = prev.close > prev.sma200
            if shares > 0 and (prev.dv2 > sell_above or not bull):
                equity += shares * fill * (1 - fee)
                why = "overbought" if prev.dv2 > sell_above else "regime"
                trades.append((entry_px, fill, i - entry_i, why))
                shares, entry_px, entry_i = 0, None, None
            elif shares == 0 and bull and prev.dv2 < buy_below:
                n = int(equity // (fill * (1 + fee)))
                if n > 0:
                    equity -= n * fill * (1 + fee)
                    shares, entry_px, entry_i = n, fill, i

        curve.append(equity + shares * bar.close)
        in_market.append(shares > 0)

    return (pd.Series(curve, index=d.index[1:]), trades,
            float(np.mean(in_market)))


def stats(curve):
    years = len(curve) / BPY
    cagr = (curve.iloc[-1] / START_EQUITY) ** (1 / max(years, 0.1)) - 1
    dd = (curve / curve.cummax() - 1).min()
    r = curve.pct_change().dropna()
    sharpe = r.mean() / r.std() * np.sqrt(BPY) if r.std() > 0 else 0.0
    se = np.sqrt((1 + sharpe ** 2 / 2) / max(years, 0.1))   # Lo (2002)
    return cagr, dd, sharpe, se, years


def buy_hold(df, fee):
    n = int(START_EQUITY // (df["open"].iloc[1] * (1 + fee)))
    cash = START_EQUITY - n * df["open"].iloc[1] * (1 + fee)
    return cash + n * df["close"].iloc[1:]


def self_check():
    """Each rule must fire when it should and stay flat when it should not."""
    idx = pd.date_range("2015-01-01", periods=600, freq="B")

    # Breakout: a ramp out-running its own bar range must stay held.
    ramp = pd.Series(np.linspace(100, 900, 600), index=idx)
    up = pd.DataFrame({"open": ramp, "high": ramp * 1.001,
                       "low": ramp * 0.999, "close": ramp})
    _, _, expo = backtest(up, "breakout", 0.0)
    assert expo > 0.5, f"self-check: breakout held only {expo:.0%} in an uptrend"

    # A dead-flat series must never trade, under either rule.
    flat = pd.Series(100.0, index=idx)
    fl = pd.DataFrame({"open": flat, "high": flat, "low": flat, "close": flat})
    for r in ("breakout", "meanrev"):
        _, _, e = backtest(fl, r, 0.0)
        assert e == 0, f"self-check: {r} traded a flat market"

    # DV2 is a percentile: bounded, and it must track its own input. A steady
    # trend has a CONSTANT close-vs-midpoint ratio, so bar shapes have to vary
    # or the rank is degenerate - an earlier version of this check had that
    # backwards and asserted the opposite.
    rng = np.random.default_rng(0)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, .01, 600))), index=idx)
    span = close * 0.02
    low = close - span * rng.uniform(0, 1, 600)
    df = pd.DataFrame({"open": close, "high": low + span,
                       "low": low, "close": close})
    v = dv2(df).dropna()
    assert v.between(0, 100).all(), "self-check: DV2 outside 0-100"
    raw = (df["close"] / ((df["high"] + df["low"]) / 2) - 1).rolling(2).mean()
    assert v.corr(raw.loc[v.index]) > 0.5, "self-check: DV2 lost its input"
    print("self-check: PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=DEFAULT_SYMBOL)
    p.add_argument("--rule", default="meanrev", choices=["meanrev", "breakout"])
    p.add_argument("--fee-bps", type=float, default=DEFAULT_FEE_BPS)
    p.add_argument("--refresh", action="store_true")
    a = p.parse_args()

    self_check()
    fee = a.fee_bps / 10_000
    df = load(a.symbol, a.refresh)
    if len(df) < 500:
        sys.exit(f"{a.symbol}: only {len(df)} bars, need 500+")

    curve, trades, expo = backtest(df, a.rule, fee)
    c, dd, sr, se, years = stats(curve)
    bh = buy_hold(df, fee)
    bc, bdd, bsr, bse, _ = stats(bh)

    print(f"\n{a.symbol}   {df.index[0]:%Y-%m-%d} to {df.index[-1]:%Y-%m-%d}"
          f"   ({years:.1f} years)   rule: {a.rule}   {a.fee_bps}bps/side\n")
    print(f"{'':10s} {'CAGR':>8s} {'maxDD':>8s} {'Sharpe':>8s} {'+/-':>6s}")
    print(f"{'strategy':10s} {c:>8.2%} {dd:>8.1%} {sr:>8.2f} {se:>6.2f}")
    print(f"{'buy & hold':10s} {bc:>8.2%} {bdd:>8.1%} {bsr:>8.2f} {bse:>6.2f}")

    if trades:
        wins = sum(1 for t in trades if t[1] > t[0])
        print(f"\n{len(trades)} trades, {wins / len(trades):.0%} winners, "
              f"{np.mean([t[2] for t in trades]):.0f} days held on average, "
              f"{expo:.0%} of days in market")

    t = sr / se if se > 0 else 0.0
    print(f"\nSharpe {sr:.2f} +/- {se:.2f} over {years:.0f} years -> t = {t:.2f}")
    if abs(t) < 2:
        print("Not distinguishable from zero on its own.")
    else:
        print("Nominally significant, but this instrument and this rule were\n"
              "both chosen after reading the results of others - the honest\n"
              "bar is higher than t > 2.")

    if sr > bsr:
        print(f"\nBeats buy and hold on Sharpe ({sr:.2f} vs {bsr:.2f}) and on\n"
              f"drawdown ({dd:.0%} vs {bdd:.0%}), earning {c - bc:+.1%} a year\n"
              f"against it.")
    else:
        print(f"\nBuy and hold scored higher ({bsr:.2f} vs {sr:.2f}). This rule\n"
              f"earns its keep only where holding is painful.")


if __name__ == "__main__":
    main()
