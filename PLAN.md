# Plan: combination first, learned cross-section as fallback

Two phases with a pre-registered gate between them. Criteria are fixed
*before* Phase A runs so the decision to pivot is mechanical, not a judgement
call made after seeing results.

## Benchmark (fixed)

SPY, out-of-sample 2020-01-01 -> present, from the runs already committed:

| | value |
|---|---|
| CAGR | 15.71% |
| max drawdown | -33.7% |
| Sharpe | 0.82 |

## Phase A - strategy combination

Hypothesis, from SSRN 4659866: combining low-correlation strategies raises
Sharpe by collapsing drawdown, not by raising return. Supported independently
by our own result that 460/480 configs reduced drawdown.

Components are fixed a priori from the source papers. They are NOT selected
from our earlier sweeps - that would be picking on results we have already
seen.

| component | parameters | source |
|---|---|---|
| TSMOM | J=252, SMA200 filter on, no stop | Moskowitz et al. 12-month |
| Dip | J=63, RSI(14) 35/70, SMA50, 25-bar cap | Sarainmaa 5-week hold |
| Rotation | J=252, top 5, monthly, 1-month gap | Jegadeesh-Titman 12-1 |

Each component runs across the 22-instrument universe, equal-weighted,
daily rebalanced. Blends use fixed rules only - equal weight and
inverse-volatility. No weight optimisation, so there is nothing to overfit.

Evaluated **once** on the holdout.

### Pass criteria - ALL three must hold

1. Blend OOS Sharpe >= **0.95** (SPY 0.82 x 1.15)
2. Blend OOS max drawdown shallower than **-25%** (SPY -33.7%)
3. Blend OOS CAGR >= **8%**

Criterion 3 exists to kill degenerate answers: a blend that sits in cash
scores well on Sharpe and drawdown while earning nothing. A higher-Sharpe,
lower-return result is a legitimate win only if the return is real, because
Sharpe can be levered and cash cannot.

Any single failure -> Phase A fails -> pivot to Phase B automatically.

## Phase B - learned cross-sectional ranker

Triggered only by Phase A failure. Rationale: StockFormer's edge lives in
*cross-sectional selection*, not index timing. VOO has no cross-section, so
the model has to rank a universe.

Deliberate departures from StockFormer:

- **ETF universe, not S&P 500 constituents.** Point-in-time constituent lists
  are not freely available; using today's members would inject survivorship
  bias and manufacture a positive result. ETFs rarely delist, so the universe
  we already have is clean.
- **Gradient boosting before any transformer.** If a GBM cannot rank the
  cross-section, a self-attention model on the same features will not either,
  and it falsifies the idea for a fraction of the cost. Transformer only if
  GBM clears the gate.
- **Walk-forward retraining**, expanding window, predicting the next quarter.

### Pass criteria

Learned ranker must beat BOTH SPY and the equal-weight universe on OOS
Sharpe in **at least 2 of 3** walk-forward folds.

Fail -> stop. Report the negative result rather than continuing to search;
at that point the material in the papers is exhausted and further sweeps
would be manufacturing a number rather than finding one.

## Phase C - is breadth the binding constraint?

Phase B did have ranking skill (fold 3: IC +0.109, t=2.85, p=0.007,
long-short Sharpe 1.03) but not enough of it to survive costs. The
fundamental law of active management says IR ~ IC x sqrt(N). Our IC is
roughly 3x a typical published one; our N is 45x smaller.

Design: measure IC and long-short IR at several universe sizes drawn from
ONE larger universe, same model, same periods. Subsampling isolates the
effect of N - any survivorship bias in the parent universe inflates all
subset sizes equally, so the *scaling relationship* stays valid even though
the levels do not.

### Pre-registered prediction

IR should scale with sqrt(N). Relative to N=25:

| N | predicted IR multiple |
|---|---|
| 50 | 1.41x |
| 100 | 2.00x |
| 200 | 2.83x |

Confirmed if measured IR rises monotonically with N and the N=200 multiple
lands within +/-40% of 2.83x (i.e. 1.7x - 4.0x).

Refuted if IR is flat or non-monotonic in N. That would mean breadth is not
the constraint and the signal itself is too weak, which ends the programme.

### Survivorship

The parent universe is today's large caps, so it is survivorship-biased and
absolute returns are inflated. This is stated rather than corrected: free
point-in-time membership data does not exist. The scaling test is the claim;
the return levels are not.

## Standing rules

- Buy & hold is the benchmark, always.
- Signals read bar t, fills at bar t+1 open.
- 0.25% per side throughout.
- Report the census, never select on the holdout.
