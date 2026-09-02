"""Prices and macro state. Everything cached; nothing revised after the fact.

Two rules, both from failures in the previous project:

  1. State variables must be REAL TIME. VIX, credit spreads and the term
     spread are published once and never revised, so a backtest using them
     could have been run on the day. Baker-Wurgler sentiment could not - it
     is a full-sample PCA, orthogonalised ex post and revised, so its
     look-ahead sits in the loadings rather than the dates and would not
     have looked wrong.

  2. Instruments must be TRADEABLE. Factor ETFs have real prices and real
     spreads. Published factor series are gross of financing, borrow and
     rebalancing.
"""

import time
from pathlib import Path

import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"

# Tradeable factor exposure. Start dates vary; MTUM is the binding one (2013).
FACTOR_ETFS = {
    "MTUM": "momentum",
    "VLUE": "value",
    "QUAL": "quality",
    "USMV": "low volatility",
}
BENCHMARK = "SPY"          # what you would otherwise hold
CASH = "BIL"               # 1-3 month T-bills, for excess returns

# FRED series. All real-time: published once, never revised.
FRED = {
    "VIXCLS": "vix",              # implied volatility
    "BAA10Y": "credit_spread",    # BAA corporate minus 10y Treasury
    "T10Y2Y": "term_spread",      # 10y minus 2y
}


def fetch_prices(symbol, refresh=False, tries=3):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol}_1d.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)

    import yfinance as yf
    for _ in range(tries):
        try:
            got = yf.Ticker(symbol).history(period="max", interval="1d")
            if not got.empty:
                df = got.rename(columns=str.lower)[["open", "high", "low", "close"]]
                df.index = df.index.tz_localize(None)
                df = df[(df["high"] >= df["low"]) & (df["close"] > 0)]
                df.to_csv(path)
                return df
        except Exception:
            pass
        time.sleep(2)
    return None


def fetch_fred(series, refresh=False, tries=3):
    """FRED CSV endpoint - no API key needed for the public download."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"fred_{series}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]

    import httpx
    url = ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + series)
    for _ in range(tries):
        try:
            r = httpx.get(url, timeout=60, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            df.columns = ["date", series]
            df["date"] = pd.to_datetime(df["date"])
            s = (df.set_index("date")[series]
                 .replace(".", pd.NA).astype(float).dropna())
            s.to_frame().to_csv(path)
            return s
        except Exception:
            pass
        time.sleep(2)
    return None


def load_all(refresh=False):
    """Returns (prices dict, state DataFrame). Prints what was obtained."""
    prices = {}
    for sym in list(FACTOR_ETFS) + [BENCHMARK, CASH]:
        df = fetch_prices(sym, refresh)
        if df is not None and len(df) > 250:
            prices[sym] = df["close"]
            print(f"  {sym:6s} {len(df):>5d} bars  {df.index[0]:%Y-%m} to "
                  f"{df.index[-1]:%Y-%m}")
        else:
            print(f"  {sym:6s} MISSING")

    state = {}
    for series, name in FRED.items():
        s = fetch_fred(series, refresh)
        if s is not None and len(s) > 250:
            state[name] = s
            print(f"  {name:14s} {len(s):>5d} obs  {s.index[0]:%Y-%m} to "
                  f"{s.index[-1]:%Y-%m}")
        else:
            print(f"  {name:14s} MISSING")

    return prices, pd.DataFrame(state).sort_index()
