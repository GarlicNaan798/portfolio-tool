"""Backtest the paper-derived VOO swing strategy against buy & hold.

Same logic as mt5/VooSwingH4.mq5, on the daily bars already exported to
mt5/VOO_D1.csv:

  regime (Bird/Gao/Yeung, Moskowitz et al. 2012)
      long only while the J-day return is positive and price > SMA200
  entry (Sarainmaa 2024, section 5.1)
      close < SMA50 and RSI(14) crossing back up through the oversold level
  exit
      ATR stop, RSI crossing down through overbought, or a bar-count cap

Signals are computed on bar t's close and filled at bar t+1's open, so no
decision ever uses information it could not have had.

    uv run --with pandas --with numpy python backtest_voo.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

CSV = Path(__file__).parent / "mt5" / "VOO_D1.csv"

# Thesis charges 0.25% a side; it is the difference between beating buy &
# hold and not, so it is reported rather than assumed away.
FEE = 0.0025

MOMENTUM_LOOKBACK = 63     # J = 3 months
MA_PERIOD = 50
RSI_PERIOD = 14
RSI_OVERSOLD = 35.0
RSI_OVERBOUGHT = 70.0
ATR_PERIOD = 14
ATR_STOP_MULT = 2.0
MAX_BARS_IN_TRADE = 25     # ~5 weeks at 1 bar/day
RISK_PCT = 0.01
START_EQUITY = 10_000.0


def wilder(series, period):
    """Wilder's smoothing - what MT5's iRSI/iATR actually use."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def rsi(close, period):
    d = close.diff()
    gain = wilder(d.clip(lower=0), period)
    loss = wilder(-d.clip(upper=0), period)
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def atr(df, period):
    prev = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs(),
    ], axis=1).max(axis=1)
    return wilder(tr, period)


def load():
    if not CSV.exists():
        sys.exit(f"missing {CSV} - run mt5/export_voo.py first")
    df = pd.read_csv(CSV, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], format="%Y.%m.%d")
    return df.set_index("date")[["open", "high", "low", "close"]].sort_index()


def add_indicators(df):
    df = df.copy()
    df["sma50"] = df["close"].rolling(MA_PERIOD).mean()
    df["sma200"] = df["close"].rolling(200).mean()
    df["rsi"] = rsi(df["close"], RSI_PERIOD)
    df["atr"] = atr(df, ATR_PERIOD)
    df["mom"] = df["close"] - df["close"].shift(MOMENTUM_LOOKBACK)
    df["rsi_prev"] = df["rsi"].shift(1)
    return df


def backtest(df, fee=FEE, sizing="risk"):
    """Returns (equity series, trades, exposure).

    sizing="risk" mirrors the EA: 1% of equity per trade against a 2*ATR
    stop, which on one instrument leaves capital mostly idle.
    sizing="full" deploys everything on a signal, so the entry/exit rule can
    be judged against buy & hold without the cash drag doing the talking.
    """
    equity = START_EQUITY
    shares = 0
    entry_i = None
    stop = 0.0
    trades = []
    curve = []
    in_market = []

    rows = df.itertuples()
    prev = next(rows)

    for i, bar in enumerate(rows, start=1):
        fill = bar.open  # decisions made on `prev` close, filled at this open

        if shares > 0:
            held = i - entry_i
            reason = None
            if bar.low <= stop:
                px, reason = stop, "stop"
            elif prev.rsi_prev > RSI_OVERBOUGHT >= prev.rsi:
                px, reason = fill, "rsi"
            elif held >= MAX_BARS_IN_TRADE:
                px, reason = fill, "time"

            if reason:
                equity += shares * px * (1 - fee)
                trades.append({"exit": bar.Index, "px": px, "reason": reason,
                               "shares": shares})
                shares, entry_i = 0, None

        if shares == 0 and not np.isnan(prev.sma200) and not np.isnan(prev.atr):
            bull = prev.mom > 0 and prev.close > prev.sma200
            cross_up = prev.rsi_prev < RSI_OVERSOLD <= prev.rsi
            if bull and cross_up and prev.close < prev.sma50:
                stop_dist = prev.atr * ATR_STOP_MULT
                if stop_dist > 0:
                    affordable = int(equity // (fill * (1 + fee)))  # no leverage
                    if sizing == "full":
                        n = affordable
                    else:
                        n = min(int((equity * RISK_PCT) // stop_dist), affordable)
                    if n > 0:
                        equity -= n * fill * (1 + fee)
                        shares, entry_i, stop = n, i, fill - stop_dist
                        trades.append({"entry": bar.Index, "px": fill, "shares": n})

        curve.append(equity + shares * bar.close)
        in_market.append(shares > 0)
        prev = bar

    exposure = float(np.mean(in_market))
    return pd.Series(curve, index=df.index[1:]), trades, exposure


def stats(curve, label, years):
    total = curve.iloc[-1] / START_EQUITY - 1
    cagr = (curve.iloc[-1] / START_EQUITY) ** (1 / years) - 1
    dd = (curve / curve.cummax() - 1).min()
    rets = curve.pct_change().dropna()
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    print(f"{label:22s} final=${curve.iloc[-1]:>11,.0f}  total={total:>8.1%}  "
          f"CAGR={cagr:>6.2%}  maxDD={dd:>7.1%}  Sharpe={sharpe:>5.2f}")
    return cagr


def buy_hold(df):
    n = int(START_EQUITY // (df["open"].iloc[1] * (1 + FEE)))
    cash = START_EQUITY - n * df["open"].iloc[1] * (1 + FEE)
    return cash + n * df["close"].iloc[1:]


def self_check(df):
    """One runnable check: the strategy must never trade before it could."""
    warm = max(200, MOMENTUM_LOOKBACK)
    sub = add_indicators(df)
    _, tr, _ = backtest(sub)
    entries = [t for t in tr if "entry" in t]
    assert entries, "self-check: expected at least one trade"
    first = entries[0]["entry"]
    assert first > sub.index[warm], f"self-check: traded at {first}, before warm-up"
    # RSI must stay in range or the Wilder smoothing is wrong.
    assert sub["rsi"].dropna().between(0, 100).all(), "self-check: RSI out of range"
    print("self-check: PASS\n")


def main():
    raw = load()
    df = add_indicators(raw).dropna(subset=["sma200", "atr", "rsi_prev"])

    self_check(raw)

    years = (df.index[-1] - df.index[0]).days / 365.25
    print(f"VOO daily  {df.index[0].date()} -> {df.index[-1].date()}  "
          f"({len(df):,} bars, {years:.1f}y)\n")

    runs = [
        ("1% risk, no fees",   0.0, "risk"),
        ("1% risk, 0.25%/side", FEE, "risk"),
        ("full alloc, no fees", 0.0, "full"),
        ("full alloc, 0.25%/side", FEE, "full"),
    ]
    for label, fee, sizing in runs:
        curve, trades, exposure = backtest(df, fee=fee, sizing=sizing)
        n = len([t for t in trades if "entry" in t])
        stats(curve, label, years)
        print(f"{'':22s} {n} trades, {exposure:.1%} of days in market")

    stats(buy_hold(df), "buy & hold", years)
    print(f"{'':22s} 1 trade, 100.0% of days in market")

    _, trades, _ = backtest(df, fee=FEE)
    exits = [t for t in trades if "exit" in t]
    if exits:
        by = pd.Series([t["reason"] for t in exits]).value_counts()
        print("\nexit reasons:", ", ".join(f"{k}={v}" for k, v in by.items()))


if __name__ == "__main__":
    main()
