"""Fetch VOO bars from Yahoo and write MT5 custom-symbol import CSVs.

No broker account needed: MT5 imports these under
Symbols -> Create Custom Symbol -> Bars -> Import.

    uv run --with yfinance --with pandas python export_voo.py
"""

import sys
import time

import pandas as pd
import yfinance as yf

# MT5's bar-import layout. VOL and SPREAD stay 0 - Yahoo gives neither.
COLUMNS = "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"


def grab(interval, period, tries=4):
    """Yahoo's cookie endpoint fails intermittently; retry before giving up."""
    for _ in range(tries):
        try:
            df = yf.Ticker("VOO").history(period=period, interval=interval)
            if not df.empty:
                return df
        except Exception:
            pass
        time.sleep(2)
    return None


def write_mt5(df, path):
    df = df[df["High"] >= df["Low"]]  # drop malformed rows before they reach MT5
    lines = [COLUMNS]
    for ts, r in df.iterrows():
        lines.append(
            f"{ts.strftime('%Y.%m.%d')}\t{ts.strftime('%H:%M:%S')}\t"
            f"{r['Open']:.2f}\t{r['High']:.2f}\t{r['Low']:.2f}\t{r['Close']:.2f}\t"
            f"{int(r.get('Volume', 0) or 0)}\t0\t0"
        )
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{path}: {len(df)} bars  {df.index[0]}  ..  {df.index[-1]}")


def main():
    daily = grab("1d", "max")
    if daily is None:
        sys.exit("could not fetch daily VOO data")
    write_mt5(daily, "VOO_D1.csv")

    hourly = grab("60m", "2y")
    if hourly is None:
        print("skipping H4: hourly fetch failed")
        return

    # Session is 09:30-16:00 ET, so anchoring 4H at 09:30 yields two bars a
    # day: a full 09:30-13:30 and a 13:30-16:00 stub. The stub is real, not a
    # bug - VOO's session simply doesn't divide by four.
    agg = {"Open": "first", "High": "max", "Low": "min",
           "Close": "last", "Volume": "sum"}
    h4 = hourly.resample("4h", origin=hourly.index[0].normalize() + pd.Timedelta("9h30m")).agg(agg)
    h4 = h4.dropna(subset=["Open"])
    write_mt5(h4, "VOO_H4.csv")

    per_day = len(h4) / h4.index.normalize().nunique()
    print(f"H4 bars/day = {per_day:.2f}  (a 24h symbol gives 6.00)")
    print(f"-> set MaxBarsInTrade near {round(per_day * 25)} for the papers' ~5-week hold")


if __name__ == "__main__":
    main()
