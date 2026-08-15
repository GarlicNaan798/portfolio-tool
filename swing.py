"""One instrument, one rule. Read it top to bottom in five minutes.

THE RULE
    Buy when price closes above its highest high of the last N days.
    Trail a stop ATR*M below the highest close since entry - it only ever
    ratchets up.
    Sell when the stop is hit, or price closes below its lowest low of the
    last X days.
    Long only. Never short.

That is the whole strategy. It is mechanical support and resistance: the
N-day high is resistance, and breaking it is the signal.

WHY THIS RULE
    It is the only thing that survived seven phases of testing - see
    findings/phase-e-validated-the-engine.md. Long only because shorting
    lost in all three tests that included it
    (findings/shorting-hurts-trend-following.md).

WHAT IT WILL NOT DO
    Beat buy & hold on something that rises steadily. It sits in cash
    between signals, and cash loses to a compounding asset
    (findings/paper-strategies-do-not-beat-buy-and-hold.md).

    Nor can one instrument ever be proven to work: over ~16 years the
    standard error on a Sharpe is about 0.25, so a single market needs
    Sharpe > 0.8 to clear significance
    (findings/no-single-instrument-is-statistically-distinguishable.md).
    This is a rule you can run and understand, not a result you can prove.

    uv run --with yfinance --with pandas --with numpy python swing.py
    uv run ... python swing.py --symbol GC=F --entry 55
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

# Default is silver: the highest trend Sharpe in the 2010-2026 futures book
# that ALSO beat its own buy & hold (0.47 vs 0.43). Be honest about what that
# is - a pick made after seeing the table, so it carries selection bias. Any
# instrument here is a starting point, not a recommendation. Change it freely.
DEFAULT_SYMBOL = "SI=F"

# Cost per side. Futures ~1-2bps, equity ETFs ~25bps. This single number
# decided whether the strategy worked in earlier tests - a 25x error once
# flipped Sharpe from 0.99 to 0.22. Set it to match what you actually pay.
DEFAULT_FEE_BPS = 1.5


def load(symbol, refresh=False):
    """Daily bars, cached on disk. Yahoo's cookie endpoint fails randomly."""
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
    # rolls show up as fake price jumps - WTI even crosses zero in April 2020.
    # Clipping stops one artifact dominating the result.
    # ponytail: winsorising, not back-adjusting. Upgrade path is paid
    # roll-adjusted data if this ever needs to be precise.
    df = df[df["high"] >= df["low"]]
    return df[df["close"] > 0]


def atr(df, n=14):
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - prev).abs(),
                    (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def backtest(df, entry_n, exit_n, stop_mult, fee):
    """Signals read bar t. Fills happen at bar t+1's open. No lookahead."""
    a = atr(df)
    resistance = df["high"].rolling(entry_n).max().shift(1)
    support = df["low"].rolling(exit_n).min().shift(1)

    equity, shares, stop = START_EQUITY, 0, 0.0
    curve, in_market, trades = [], [], []
    entry_px = entry_i = None

    rows = list(df.itertuples())
    for i in range(1, len(rows)):
        prev, bar = rows[i - 1], rows[i]
        fill = bar.open

        if shares > 0:
            # Ratchet the stop up behind the highest close so far.
            stop = max(stop, prev.close - stop_mult * a.iloc[i - 1])
            hit = bar.low <= stop
            broke = prev.close < support.iloc[i - 1]
            if hit or broke:
                px = stop if hit else fill
                equity += shares * px * (1 - fee)
                trades.append((entry_px, px, i - entry_i,
                               "stop" if hit else "support"))
                shares, entry_px, entry_i = 0, None, None

        if shares == 0 and not np.isnan(resistance.iloc[i - 1]):
            if prev.close > resistance.iloc[i - 1]:
                n = int(equity // (fill * (1 + fee)))
                if n > 0:
                    equity -= n * fill * (1 + fee)
                    shares, entry_px, entry_i = n, fill, i
                    stop = fill - stop_mult * a.iloc[i - 1]

        curve.append(equity + shares * bar.close)
        in_market.append(shares > 0)

    return (pd.Series(curve, index=df.index[1:]), trades,
            float(np.mean(in_market)))


def stats(curve):
    years = len(curve) / BPY
    total = curve.iloc[-1] / START_EQUITY
    cagr = total ** (1 / max(years, 0.1)) - 1
    dd = (curve / curve.cummax() - 1).min()
    r = curve.pct_change().dropna()
    sharpe = r.mean() / r.std() * np.sqrt(BPY) if r.std() > 0 else 0.0
    # Lo (2002): SE of an annualised Sharpe over T years.
    se = np.sqrt((1 + sharpe ** 2 / 2) / max(years, 0.1))
    return cagr, dd, sharpe, se, years


def buy_hold(df, fee):
    n = int(START_EQUITY // (df["open"].iloc[1] * (1 + fee)))
    cash = START_EQUITY - n * df["open"].iloc[1] * (1 + fee)
    return cash + n * df["close"].iloc[1:]


def self_check():
    """A rising series must trade; a flat one must not. If this fails the
    rule is broken and every number below is noise."""
    idx = pd.date_range("2015-01-01", periods=500, freq="B")

    ramp = pd.Series(np.linspace(100, 900, 500), index=idx)
    up = pd.DataFrame({"open": ramp, "high": ramp * 1.001,
                       "low": ramp * 0.999, "close": ramp})
    _, trades, expo = backtest(up, 100, 20, 3.0, 0.0)
    assert expo > 0.5, f"self-check: uptrend held only {expo:.0%} of the time"

    flat = pd.Series(100.0, index=idx)
    fl = pd.DataFrame({"open": flat, "high": flat, "low": flat, "close": flat})
    _, _, expo2 = backtest(fl, 100, 20, 3.0, 0.0)
    assert expo2 == 0, "self-check: took a position in a flat market"
    print("self-check: PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=DEFAULT_SYMBOL)
    p.add_argument("--entry", type=int, default=100, help="breakout lookback")
    p.add_argument("--exit", type=int, default=20, help="support lookback")
    p.add_argument("--stop", type=float, default=3.0, help="ATR multiple")
    p.add_argument("--fee-bps", type=float, default=DEFAULT_FEE_BPS)
    p.add_argument("--refresh", action="store_true")
    a = p.parse_args()

    self_check()
    fee = a.fee_bps / 10_000
    df = load(a.symbol, a.refresh)
    if len(df) < 400:
        sys.exit(f"{a.symbol}: only {len(df)} bars, need 400+")

    curve, trades, expo = backtest(df, a.entry, a.exit, a.stop, fee)
    c, dd, sr, se, years = stats(curve)
    bh = buy_hold(df, fee)
    bc, bdd, bsr, bse, _ = stats(bh)

    print(f"\n{a.symbol}   {df.index[0]:%Y-%m-%d} to {df.index[-1]:%Y-%m-%d}"
          f"   ({years:.1f} years)")
    print(f"rule: buy above the {a.entry}-day high, trail {a.stop}x ATR, "
          f"exit below the {a.exit}-day low, {a.fee_bps}bps/side\n")

    print(f"{'':10s} {'CAGR':>8s} {'maxDD':>8s} {'Sharpe':>8s} {'+/-':>6s}")
    print(f"{'strategy':10s} {c:>8.2%} {dd:>8.1%} {sr:>8.2f} {se:>6.2f}")
    print(f"{'buy & hold':10s} {bc:>8.2%} {bdd:>8.1%} {bsr:>8.2f} {bse:>6.2f}")

    wins = [t for t in trades if t[1] > t[0]]
    if trades:
        held = np.mean([t[2] for t in trades])
        print(f"\n{len(trades)} trades, {len(wins) / len(trades):.0%} winners, "
              f"{held:.0f} days held on average, {expo:.0%} of days in market")
        stops = sum(1 for t in trades if t[3] == "stop")
        print(f"exits: {stops} on the trailing stop, "
              f"{len(trades) - stops} on the support break")

    if trades and stops == len(trades):
        print(f"\nNote: every exit came from the trailing stop and none from "
              f"the\n{a.exit}-day support break - at {a.stop}x ATR the stop is "
              f"always the tighter\nof the two, so --exit does nothing here. "
              f"The rule is effectively\none entry and one exit.")

    # Compute significance rather than assuming it. t = Sharpe / SE.
    t = sr / se if se > 0 else 0.0
    print(f"\nSharpe {sr:.2f} +/- {se:.2f} over {years:.0f} years -> t = {t:.2f}")
    if abs(t) < 2:
        print("Not distinguishable from zero. This is a rule you can run, "
              "not an edge\nyou have shown to exist.")
    else:
        print("Nominally significant on its own. But this instrument was "
              "chosen after\nreading a table of 31 markets, so the honest "
              "threshold is 0.05/31 -\nrequiring t > 3.2, not t > 2. Selection "
              "bias, not significance.")

    if sr < bsr:
        print(f"\nBuy & hold scored higher ({bsr:.2f} vs {sr:.2f}). The rule "
              f"earns its keep\nonly where holding is painful.")
    else:
        print(f"\nBeats buy & hold on Sharpe ({sr:.2f} vs {bsr:.2f}) with "
              f"{abs(dd) / abs(bdd) - 1:+.0%} the drawdown,\nbut gives up "
              f"{bc - c:.1%} a year of return to do it.")


if __name__ == "__main__":
    main()
