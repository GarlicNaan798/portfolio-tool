"""Show exactly how a stock gets picked, with today's real numbers.

Walks the same path the backtest takes: raw measurement -> comparison to
peers -> blended score -> selection. No new logic; this only makes the
existing mechanism visible.

    uv run --with yfinance --with pandas --with numpy python explain_picks.py
"""

import pandas as pd

from plab import alpha, data

pd.set_option("display.width", 200)

px, _ = data.panel(data.LARGE_CAP)
px = px.dropna(axis=1, thresh=int(len(px) * 0.7)).ffill()
today = px.index[-1]

# --- 1. raw measurements, in their own units -------------------------------
raw = {
    "mom_12_1": alpha.momentum_12_1(px).loc[today],
    "reversal": alpha.reversal_1m(px).loc[today],
    "low_vol": alpha.low_volatility(px).loc[today],
    "trend": alpha.trend(px).loc[today],
}
raw = pd.DataFrame(raw)

# --- 2. same numbers, scored against peers that day (z-score) --------------
z = pd.DataFrame({k: v.loc[today] for k, v in alpha.build(px).items()})

# --- 3. blended into one score, then ranked --------------------------------
score = alpha.combine(alpha.build(px)).loc[today]

print(f"universe {px.shape[1]} stocks, as of {today:%Y-%m-%d}\n")
print("=" * 78)
print("THE FOUR MEASUREMENTS, RAW (each in its own units)")
print("=" * 78)
print("mom_12_1  return over the past year, skipping the last month")
print("reversal  MINUS the last month's return (so a fall scores high)")
print("low_vol   MINUS daily volatility (so a calm stock scores high)")
print("trend     how far above its 200-day average\n")
sample = ["AAPL", "NVDA", "JNJ", "XOM", "KO"]
sample = [s for s in sample if s in raw.index]
print(raw.loc[sample].to_string(float_format=lambda x: f"{x:8.3f}"))

print("\n" + "=" * 78)
print("SAME STOCKS, SCORED AGAINST THE OTHER 140 THAT DAY (z-score)")
print("=" * 78)
print("0 = exactly average.  +1 = one standard deviation better than peers.")
print("This is what makes a $12 stock and a $900 stock comparable.\n")
print(z.loc[sample].to_string(float_format=lambda x: f"{x:8.2f}"))

print("\n" + "=" * 78)
print("BLEND: average the four z-scores, then re-score. Highest 20 get bought")
print("=" * 78)
top = score.nlargest(20)
det = z.loc[top.index].copy()
det["SCORE"] = top
print(det.to_string(float_format=lambda x: f"{x:7.2f}"))

print("\n" + "-" * 78)
bot = score.nsmallest(5)
print("for contrast, the 5 LOWEST-scoring (never bought, never shorted):")
print(z.loc[bot.index].assign(SCORE=bot).to_string(
    float_format=lambda x: f"{x:7.2f}"))
