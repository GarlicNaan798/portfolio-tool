---
name: mt5-abandoned-for-python-backtests
description: MT5 Strategy Tester was dropped as the backtesting engine because iteration was too slow to be worth it
metadata: 
  node_type: memory
  type: project
  originSessionId: 1d496a90-24f0-4168-91a2-d02000953e7d
  modified: 2026-08-10T15:52:02.300Z
---

On 2026-08-10 the user abandoned MetaTrader 5 as the backtesting engine for the
swing strategy work. The MQL5 EA (`mt5/VooSwingH4.mq5`) and the CSV import
scripts still exist, but they are history, not the active path — backtesting now
happens in Python (`swing_lab.py`, `strategy_search.py`) against yfinance data.

**Why:** the MT5 Strategy Tester round-trip — custom symbol import, recompiling
the EA, hunting inputs through the GUI — cost more time per iteration than the
results justified. The user's words: "it's taking too long to be worth it."

**How to apply:** don't propose MT5 backtests, custom-symbol imports, or EA
input sweeps as the way to test an idea. Test in Python. MT5 is only relevant
again if the goal is live execution rather than research. See
[[autonomous-strategy-sweeps]] for how sweeps are expected to run.
