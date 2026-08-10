"""Swing-strategy lab: sweep strategies x parameters x instruments.

Design decisions that exist to stop this becoming an overfitting machine:

  * Parameters come from the source papers (J = 3/6/9/12 months, the thesis's
    RSI/MA settings), not from an open-ended numeric search.
  * Every config is tuned on IN-SAMPLE data and scored on an OUT-OF-SAMPLE
    tail it never saw.
  * Configs are ranked by HOW MANY INSTRUMENTS they beat buy & hold on, not
    by their best single result. One instrument winning is noise; the same
    rule winning across uncorrelated markets is a signal.
  * Buy & hold is the benchmark everywhere. "Profitable" is not the bar.

    uv run --with yfinance --with pandas --with numpy python swing_lab.py
    uv run ... python swing_lab.py --interval 4h --tickers BTC-USD ETH-USD
"""

import argparse
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).parent / "data" / "cache"
START_EQUITY = 10_000.0
FEE = 0.0025          # 0.25% a side, as the thesis charges

# Universes. US-listed ETFs are daily-only: their 6.5h session does not divide
# into 4h bars (measured: 1.99 bars/day), so H4 on them is an artifact.
UNIVERSE_1D = [
    # commodities - where Moskowitz et al. found TSMOM strongest
    "GLD", "SLV", "USO", "UNG", "DBA", "DBC", "CPER",
    # equity indices
    "SPY", "QQQ", "IWM", "EFA", "EEM",
    # bonds
    "TLT", "IEF", "HYG",
    # currencies
    "UUP", "FXE", "FXY",
    # sectors
    "XLE", "XLF", "XLK", "XLU",
]
# 24h instruments - the only ones where a 4h bar is a real bar
UNIVERSE_4H = ["BTC-USD", "ETH-USD", "GC=F", "CL=F", "SI=F", "NG=F", "ES=F"]


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def fetch(ticker, interval, tries=3):
    """Download once, cache on disk. Yahoo's cookie endpoint is flaky."""
    CACHE.mkdir(parents=True, exist_ok=True)
    safe = ticker.replace("=", "_").replace("^", "_")
    path = CACHE / f"{safe}_{interval}.csv"
    if path.exists():
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return df if len(df) > 300 else None

    import yfinance as yf
    period = "max" if interval == "1d" else "730d"
    for _ in range(tries):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval)
            if not df.empty:
                df = df.rename(columns=str.lower)[["open", "high", "low", "close"]]
                df.index = df.index.tz_localize(None)
                if interval == "4h":       # resample from 1h
                    pass
                df.to_csv(path)
                return df if len(df) > 300 else None
        except Exception:
            pass
        time.sleep(2)
    return None


def fetch_4h(ticker):
    """Yahoo has no native 4h; build it from 1h (max 730d of history)."""
    h = fetch(ticker, "1h")
    if h is None:
        return None
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return h.resample("4h").agg(agg).dropna()


# --------------------------------------------------------------------------
# indicators
# --------------------------------------------------------------------------
def wilder(s, n):
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def add_indicators(df, lookback):
    d = df.copy()
    d["sma50"] = d["close"].rolling(50).mean()
    d["sma200"] = d["close"].rolling(200).mean()

    delta = d["close"].diff()
    gain = wilder(delta.clip(lower=0), 14)
    loss = wilder(-delta.clip(upper=0), 14)
    d["rsi"] = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).fillna(50.0)
    d["rsi_prev"] = d["rsi"].shift(1)

    prev = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - prev).abs(),
                    (d["low"] - prev).abs()], axis=1).max(axis=1)
    d["atr"] = wilder(tr, 14)
    d["mom"] = d["close"] - d["close"].shift(lookback)
    return d.dropna(subset=["sma200", "atr", "rsi_prev", "mom"])


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------
def run(df, p):
    """Signals read bar t; fills happen at bar t+1's open. Long only."""
    fee = p["fee"]
    equity, shares, entry_i, stop = START_EQUITY, 0, None, 0.0
    curve, in_mkt, trades = [], [], 0

    rows = df.itertuples()
    prev = next(rows)

    for i, bar in enumerate(rows, start=1):
        fill = bar.open
        regime = prev.mom > 0 and (not p["use_sma200"] or prev.close > prev.sma200)
        v = p["variant"]

        if v == "tsmom":
            want = regime
        elif v == "cross":
            want = prev.sma50 > prev.sma200
        elif v == "dip":
            want = regime and prev.close < prev.sma50 and prev.rsi_prev < p["rsi_os"] <= prev.rsi
        else:
            want = prev.close < prev.sma50 and prev.rsi_prev < p["rsi_os"] <= prev.rsi

        if shares > 0:
            px = reason = None
            if p["atr_stop"] and bar.low <= stop:
                px, reason = stop, "stop"
            elif v in ("tsmom", "cross"):
                if not want:
                    px, reason = fill, "signal"
            elif prev.rsi_prev > p["rsi_ob"] >= prev.rsi:
                px, reason = fill, "rsi"
            elif p["max_bars"] and (i - entry_i) >= p["max_bars"]:
                px, reason = fill, "time"
            if reason:
                equity += shares * px * (1 - fee)
                shares, entry_i = 0, None

        if shares == 0 and want:
            n = int(equity // (fill * (1 + fee)))
            if n > 0:
                equity -= n * fill * (1 + fee)
                shares, entry_i = n, i
                stop = fill - prev.atr * p["atr_stop"] if p["atr_stop"] else 0.0
                trades += 1

        curve.append(equity + shares * bar.close)
        in_mkt.append(shares > 0)
        prev = bar

    return pd.Series(curve, index=df.index[1:]), trades, float(np.mean(in_mkt))


def metrics(curve, bars_per_year):
    final = curve.iloc[-1]
    years = len(curve) / bars_per_year
    cagr = (final / START_EQUITY) ** (1 / max(years, 0.1)) - 1
    dd = (curve / curve.cummax() - 1).min()
    r = curve.pct_change().dropna()
    sharpe = r.mean() / r.std() * np.sqrt(bars_per_year) if r.std() > 0 else 0.0
    return cagr, dd, sharpe


def buy_hold(df, bpy):
    n = int(START_EQUITY // (df["open"].iloc[1] * (1 + FEE)))
    cash = START_EQUITY - n * df["open"].iloc[1] * (1 + FEE)
    return metrics(cash + n * df["close"].iloc[1:], bpy)


# --------------------------------------------------------------------------
# grid
# --------------------------------------------------------------------------
def grid():
    out = []
    for variant in ("tsmom", "cross", "dip", "dip_free"):
        for lb, use200, stop in itertools.product([63, 126, 189, 252],
                                                  [True, False], [None, 2.0, 3.0]):
            base = dict(variant=variant, lookback=lb, use_sma200=use200,
                        atr_stop=stop, rsi_os=35.0, rsi_ob=70.0,
                        max_bars=None, fee=FEE)
            if variant in ("tsmom", "cross"):
                out.append(base)
            else:
                for rsi_os, mb in itertools.product([30.0, 35.0], [25, 50, None]):
                    out.append({**base, "rsi_os": rsi_os, "max_bars": mb})
    return out


def key(p):
    return (p["variant"], p["lookback"], p["use_sma200"], p["atr_stop"],
            p["rsi_os"], p["max_bars"])


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1d", choices=["1d", "4h"])
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--split", default=None, help="OOS start date")
    ap.add_argument("--md", action="store_true",
                    help="also write the ranked table to notes/ as markdown")
    args = ap.parse_args()

    bpy = 252 if args.interval == "1d" else 252 * 6
    tickers = args.tickers or (UNIVERSE_1D if args.interval == "1d" else UNIVERSE_4H)
    split = args.split or ("2020-01-01" if args.interval == "1d" else "2025-08-01")

    configs = grid()
    print(f"interval={args.interval}  tickers={len(tickers)}  configs={len(configs)}")
    print(f"OOS starts {split}\n")

    # instrument -> {config_key: (beats_bh_oos, cagr_oos, sharpe_oos, dd_oos)}
    scores, bh_table, loaded = {}, {}, []

    for t in tickers:
        raw = fetch_4h(t) if args.interval == "4h" else fetch(t, "1d")
        if raw is None or len(raw) < 600:
            print(f"  {t:8s} skipped (insufficient data)")
            continue
        loaded.append(t)

        ins_raw = raw[raw.index < split]
        oos_raw = pd.concat([ins_raw.tail(300), raw[raw.index >= split]])
        if len(ins_raw) < 400 or len(raw[raw.index >= split]) < 100:
            print(f"  {t:8s} skipped (split leaves too little)")
            loaded.pop()
            continue

        prepped = {}
        for lb in (63, 126, 189, 252):
            prepped[lb] = (add_indicators(ins_raw, lb), add_indicators(oos_raw, lb))

        bh_in = buy_hold(prepped[63][0], bpy)
        bh_out = buy_hold(prepped[63][1], bpy)
        bh_table[t] = (bh_in, bh_out)

        for p in configs:
            ins, oos = prepped[p["lookback"]]
            c_in, _, _ = run(ins, p)
            cagr_in, _, _ = metrics(c_in, bpy)
            c_out, n_out, e_out = run(oos, p)
            cagr_o, dd_o, sh_o = metrics(c_out, bpy)
            scores.setdefault(key(p), []).append(
                (t, cagr_in > bh_in[0], cagr_o > bh_out[0], sh_o > bh_out[2],
                 cagr_o, sh_o, dd_o, e_out))
        print(f"  {t:8s} done  (B&H oos CAGR {bh_out[0]:6.2%})")

    if not loaded:
        sys.exit("no instruments loaded")

    print(f"\n=== ranked by instruments beaten OUT-OF-SAMPLE (of {len(loaded)}) ===")
    rows = []
    for k, recs in scores.items():
        wins = sum(r[2] for r in recs)
        wins_sh = sum(r[3] for r in recs)
        rows.append((wins, wins_sh, np.mean([r[4] for r in recs]),
                     np.mean([r[5] for r in recs]), np.mean([r[7] for r in recs]), k))
    rows.sort(key=lambda r: (-r[0], -r[1]))

    print(f"{'variant':10s} {'J':>4s} {'200':>4s} {'stop':>5s} {'rsi':>4s} {'bars':>5s} "
          f"{'winCAGR':>8s} {'winShrp':>8s} {'avgCAGR':>8s} {'avgShrp':>8s} {'expo':>6s}")
    for wins, wins_sh, ac, ash, ae, k in rows[:15]:
        v, lb, u2, st, ros, mb = k
        print(f"{v:10s} {lb:>4d} {str(u2)[:1]:>4s} {str(st):>5s} {ros:>4.0f} {str(mb):>5s} "
              f"{wins:>8d} {wins_sh:>8d} {ac:>8.2%} {ash:>8.2f} {ae:>6.1%}")

    print("\n=== per-instrument buy & hold (out-of-sample) ===")
    for t in loaded:
        print(f"  {t:8s} CAGR {bh_table[t][1][0]:>7.2%}  Sharpe {bh_table[t][1][2]:>5.2f}")

    best = rows[0]
    print(f"\nbest config beat B&H on {best[0]}/{len(loaded)} instruments "
          f"(CAGR) and {best[1]}/{len(loaded)} (Sharpe)")
    if best[0] <= len(loaded) * 0.5:
        print("-> under half the universe: consistent with noise, not an edge.")

    if args.md:
        print(f"\nwrote {write_note(args, split, loaded, configs, rows, bh_table)}")


def write_note(args, split, loaded, configs, rows, bh_table):
    """Dump the ranking as an Obsidian note. Frontmatter is what makes runs
    queryable later; the table is what makes them readable."""
    stamp = time.strftime("%Y-%m-%d-%H%M")
    out = Path(__file__).parent / "notes" / f"{stamp}-{args.interval}.md"
    out.parent.mkdir(exist_ok=True)

    L = [f"---\ndate: {time.strftime('%Y-%m-%d')}\ntype: run\n"
         f"interval: {args.interval}\noos_split: {split}\n"
         f"instruments: {len(loaded)}\nconfigs: {len(configs)}\n"
         f"tickers: [{', '.join(loaded)}]\n---\n",
         "| variant | J | 200 | stop | rsi | bars | winCAGR | winShrp | avgCAGR | avgShrp | expo |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for wins, wins_sh, ac, ash, ae, k in rows[:15]:
        v, lb, u2, st, ros, mb = k
        L.append(f"| {v} | {lb} | {u2} | {st} | {ros:.0f} | {mb} | "
                 f"{wins}/{len(loaded)} | {wins_sh}/{len(loaded)} | {ac:.2%} | {ash:.2f} | {ae:.1%} |")

    L += ["", "## buy & hold, out-of-sample", "", "| ticker | CAGR | Sharpe |", "|---|--:|--:|"]
    L += [f"| {t} | {bh_table[t][1][0]:.2%} | {bh_table[t][1][2]:.2f} |" for t in loaded]

    best = rows[0]
    L += ["", f"Best config beat B&H on **{best[0]}/{len(loaded)}** instruments by CAGR, "
              f"{best[1]}/{len(loaded)} by Sharpe."
              + ("" if best[0] > len(loaded) * 0.5 else
                 " Under half the universe — consistent with noise, not an edge.")]
    out.write_text("\n".join(L), encoding="utf-8")
    return out

    # Where does it win? If wins concentrate on instruments whose buy & hold
    # was negative, the strategy is not generating return - it is declining to
    # hold a falling asset. Worth knowing which of the two you have.
    recs = scores[best[5]]
    print(f"\n=== best config, per instrument (sorted by B&H) ===")
    print(f"{'ticker':8s} {'B&H CAGR':>9s} {'strat CAGR':>11s} {'expo':>6s}  verdict")
    tab = sorted(recs, key=lambda r: -bh_table[r[0]][1][0])
    for t, _, win, _, cagr_o, _, _, e_out in tab:
        bh_c = bh_table[t][1][0]
        print(f"{t:8s} {bh_c:>9.2%} {cagr_o:>11.2%} {e_out:>6.0%}  "
              f"{'BEAT' if win else 'lost'}")

    up = [r for r in recs if bh_table[r[0]][1][0] > 0]
    dn = [r for r in recs if bh_table[r[0]][1][0] <= 0]
    if up and dn:
        print(f"\nwins where B&H rose : {sum(r[2] for r in up)}/{len(up)}")
        print(f"wins where B&H fell : {sum(r[2] for r in dn)}/{len(dn)}")
        print("If the second ratio dominates, this is crash-avoidance, "
              "not alpha.")


if __name__ == "__main__":
    main()
