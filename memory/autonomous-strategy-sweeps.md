---
name: autonomous-strategy-sweeps
description: "User wants multiple strategies swept automatically, with their fixed parameters preserved, rather than approving each run"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1d496a90-24f0-4168-91a2-d02000953e7d
  modified: 2026-08-10T15:52:07.019Z
---

The user wants strategy research run *for* them: take the parameters they have
already specified, vary the strategy variables independently, and backtest many
strategies in one pass — not one config per turn with a check-in between.

**Why:** stated on 2026-08-10 while moving off MT5 — the bottleneck was manual
per-run tuning, and the point of leaving
[[mt5-abandoned-for-python-backtests]] was to stop paying that cost.

**How to apply:** when asked to test an idea, sweep the grid and report the
ranked table, don't ask which single config to try first. Their fixed
parameters are inputs to hold constant, not defaults to re-litigate.
