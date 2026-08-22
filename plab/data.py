"""Price data: fetch once, cache on disk, align into a panel.

Replaces three separate copies of load() that had drifted apart across
swing.py, mr_regime.py and recheck_costs.py.
"""

import time
from pathlib import Path

import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"

# Liquid US large caps with history back to at least 2005. These are today's
# survivors, which means any absolute return computed on them is optimistic -
# companies that failed are absent. Cross-sectional RANKING is far less
# affected than levels, but the bias is real and stated rather than hidden.
LARGE_CAP = """
AAPL MSFT AMZN GOOGL META NVDA TSLA JPM V JNJ WMT PG MA HD CVX ABBV PFE KO
PEP BAC COST TMO CSCO MRK ACN LLY MCD ADBE ABT CRM NKE TXN DHR NEE WFC ORCL
PM UNP MS RTX LOW INTC UPS QCOM HON BMY AMGN SBUX BLK CAT GS INTU DE AXP
GILD ADI MDLZ ISRG TJX VRTX REGN ZTS SYK PLD MMC CB SO CI DUK BDX ITW MO
AON APD CL ICE FDX NSC EOG SLB PSX MPC VLO OXY HAL DVN KMI WMB OKE T VZ
CMCSA DIS NFLX PYPL EBAY F GM MAR HLT DAL LUV BA LMT NOC GD EMR ETN PH ROK
AME DOV CMI PCAR AMD MU LRCX KLAC AMAT AVGO NXPI ON SWKS MCHP UNH ELV CVS
CNC HUM MCK CAH DGX LH IQV A RMD BSX EW ZBH BAX SPG O PSA EXR AVB EQR MAA
ESS VTR WELL DLR EQIX AMT CCI XOM COP EQT
""".split()

BENCHMARK = "SPY"


def fetch(symbol, interval="1d", refresh=False, tries=3):
    """One symbol, cached. Yahoo's cookie endpoint fails at random."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol.replace('=', '_').replace('^', '_')}_{interval}.csv"

    if path.exists() and not refresh:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        import yfinance as yf
        df = None
        for _ in range(tries):
            try:
                got = yf.Ticker(symbol).history(period="max", interval=interval)
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
            return None

    # Yahoo occasionally emits malformed bars; a high below its low or a
    # non-positive price makes every downstream return meaningless.
    return df[(df["high"] >= df["low"]) & (df["close"] > 0) & (df["open"] > 0)]


def panel(symbols, field="close", min_bars=1200, refresh=False):
    """Align many symbols into one DataFrame indexed by date.

    Symbols with too little history are dropped rather than forward-filled
    from nothing - a stock that did not trade yet must not be rankable.
    """
    cols, dropped = {}, []
    for s in symbols:
        df = fetch(s, refresh=refresh)
        if df is None or len(df) < min_bars:
            dropped.append(s)
            continue
        cols[s] = df[field]
    if not cols:
        raise SystemExit("no usable symbols")
    out = pd.DataFrame(cols).sort_index()

    # A few names carry decades more history than the rest. Left alone,
    # the panel starts in the 1960s and is almost entirely empty, which
    # makes cross-sectional ranks meaningless early on. Start where most
    # of the universe actually exists.
    coverage = out.notna().mean(axis=1)
    usable = coverage[coverage >= 0.8]
    if len(usable):
        out = out.loc[usable.index[0]:]
    return out, dropped


def opens(symbols, **kw):
    """Open prices, for filling at t+1 rather than at the signal bar."""
    return panel(symbols, field="open", **kw)[0]
