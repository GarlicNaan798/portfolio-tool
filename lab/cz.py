"""Chen & Zimmermann Open Source Cross-Sectional Asset Pricing.

212 published anomalies with portfolio returns, 1926-2024, plus metadata for
331 signals. Downloaded once, cached as parquet.

Why this dataset and not our own reconstruction: the previous project rebuilt
TSMOM and value by hand and got both partly wrong, and the errors were only
caught by luck. These are the authors' own portfolios, built to each original
paper's methodology, with the alternative screens published alongside.

The alternative screens are the point. Hou/Xue/Zhang (2020) report that 82%
of 452 anomalies fail once microcaps are removed and returns are
value-weighted; Chen & Zimmermann report 98% replication following original
methods. Both are right - the sets below let us measure the gap ourselves
rather than pick a side.
"""

from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data" / "cz"

# Portfolio construction variants. The first is "as published"; the rest
# progressively strip out the small, illiquid names where anomalies are
# strongest and least tradeable.
SETS = {
    "op": "original (as published)",
    "deciles_vw": "value-weighted",
    "ex_nyse_p20_me": "microcaps excluded (below NYSE 20th pct)",
    "ex_price5": "price > $5",
}


def load(name="op", refresh=False):
    """Portfolio returns for one construction variant."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"ports_{name}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)

    import openassetpricing as oap
    df = oap.OpenAP().dl_port(name, "pandas")
    df.to_parquet(path)
    return df


def doc(refresh=False):
    """Signal metadata: authors, year, data type, rebalance period, sample."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "signal_doc.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)

    import openassetpricing as oap
    d = oap.OpenAP().dl_signal_doc("pandas")
    d.to_parquet(path)
    return d


def long_short(df):
    """Just the long-short leg - what every one of these papers reports."""
    return df[df["port"].astype(str).str.upper() == "LS"]


def summarise(df, min_months=60):
    """Per-signal mean, sd, t and annualised return on the long-short leg.

    Returns are in percent per month in this dataset, hence the /100.
    """
    ls = long_short(df)
    g = ls.groupby("signalname")["ret"]
    s = pd.DataFrame({"n": g.size(), "mean": g.mean(), "sd": g.std()})
    s = s[s["n"] >= min_months]
    s["t"] = s["mean"] / s["sd"] * np.sqrt(s["n"])
    s["ann"] = s["mean"] * 12 / 100.0
    s["sharpe"] = s["mean"] / s["sd"] * np.sqrt(12)
    return s.sort_values("t", ascending=False)


def survival(s, thresholds=(1.96, 2.78, 3.0)):
    """What fraction clears each hurdle. 2.78 is HXZ's multiple-test bar."""
    return {f"t>{t}": float((s["t"].abs() > t).mean()) for t in thresholds}
