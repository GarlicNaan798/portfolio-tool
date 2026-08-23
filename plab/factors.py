"""AQR published factor series - for VALIDATION, not for searching.

All three council voices independently warned that reaching for a new data
source after ten failures is "change the input, keep the premise". They are
right, and the guard is what this module is FOR rather than what it contains:

    AQR publishes the answer. If our harness cannot reproduce a published
    factor series from its own inputs, the harness is broken and every
    negative result in this repo is void. If it can, the negatives stand.

That is a positive control on the whole programme, and it is the one use of
this data that is not another search. Searching 100 years x dozens of factors
with a selection process that has picked instruments after seeing tables
eight times would be, in the council's phrase, "an industrial overfitting
machine wearing a published-paper badge".

Data is public, no API key. Source: https://www.aqr.com/Insights/Datasets
Discovered via the ml4t-data library the user supplied.
"""

import io
import time
from pathlib import Path

import pandas as pd

BASE = "https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/"
CACHE = Path(__file__).resolve().parent.parent / "data" / "factors"

DATASETS = {
    # Moskowitz, Ooi & Pedersen (2012) - the series Phase E tried to rebuild
    # from Yahoo futures, with roll artifacts and a 25x cost error.
    "tsmom": "Time-Series-Momentum-Factors-Monthly.xlsx",
    # Asness, Moskowitz & Pedersen (2013) - Phase F reconstructed this badly.
    "vme": "Value-and-Momentum-Everywhere-Factors-Monthly.xlsx",
    # Ilmanen et al. (2021) - 1920 onward. Directly addresses the power
    # ceiling recorded in findings/: 16-26 year samples cannot resolve a
    # Sharpe of 0.4, and this is a century.
    "century": "Century-of-Factor-Premia-Monthly.xlsx",
    "qmj": "Quality-Minus-Junk-Factors-Monthly.xlsx",
    "bab": "Betting-Against-Beta-Equity-Factors-Monthly.xlsx",
}


def _find_header(raw, max_scan=30):
    """Locate the header row by looking for a date-like first column.

    AQR files carry a variable-length disclaimer preamble. ml4t-data hardcodes
    skiprows=17, which is right for some files and wrong for others; detecting
    it is one line more code and does not silently mis-parse.
    """
    for i in range(min(max_scan, len(raw))):
        cell = str(raw.iloc[i, 0]).strip().lower()
        if cell in ("date", "month", "dates"):
            return i
        # or a row whose first cell already parses as a date
        try:
            if pd.notna(raw.iloc[i, 0]) and pd.to_datetime(
                    raw.iloc[i, 0], errors="raise"):
                return max(i - 1, 0)
        except Exception:
            continue
    return 17          # fall back to the library's assumption


def fetch(name, refresh=False, tries=4):
    """Download one AQR dataset, cached on disk. Returns a DataFrame."""
    if name not in DATASETS:
        raise KeyError(f"unknown dataset {name!r}; have {list(DATASETS)}")

    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)

    import httpx
    last = None
    for attempt in range(tries):
        try:
            r = httpx.get(BASE + DATASETS[name], timeout=120,
                          follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            if len(r.content) < 5000:
                raise ValueError(f"suspiciously small response "
                                 f"({len(r.content)} bytes)")
            blob = io.BytesIO(r.content)
            raw = pd.read_excel(blob, sheet_name=0, header=None)
            hdr = _find_header(raw)
            df = pd.read_excel(io.BytesIO(r.content), sheet_name=0, header=hdr)

            first = df.columns[0]
            df = df.rename(columns={first: "date"})
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"]).set_index("date").sort_index()
            df = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
            df.to_parquet(path)
            return df
        except Exception as e:            # DNS here is intermittent
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"could not fetch AQR {name!r} after {tries} tries: {last}")


def available():
    """Which datasets are already cached, so an offline run knows its options."""
    if not CACHE.exists():
        return []
    return sorted(p.stem for p in CACHE.glob("*.parquet"))


def summarise(df, name=""):
    print(f"{name}: {df.shape[0]} rows x {df.shape[1]} cols, "
          f"{df.index[0]:%Y-%m} to {df.index[-1]:%Y-%m} "
          f"({(df.index[-1] - df.index[0]).days / 365.25:.0f} years)")
    print(f"  columns: {list(df.columns)[:8]}"
          f"{' ...' if df.shape[1] > 8 else ''}")


if __name__ == "__main__":
    for key in ("century", "tsmom", "vme"):
        try:
            summarise(fetch(key), key)
        except Exception as e:
            print(f"{key}: FAILED - {e}")
